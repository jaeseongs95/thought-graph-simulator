"""v0.4 계약/실제 과거 응답 회귀/Mock API 시험. 다운로드/LLM 추론 없음.

Mock 정답은 시험에 한해 기존 결정론적 생성기/고정 입력으로 만든다.
그 결과를 모델 수행 결과로 해석하지 않는다.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock, patch

from local_llm import calibration, calibration_v4, prompts_v4
from local_llm.__main__ import main
from local_llm.client import Reply
from local_llm.common import PACKAGE, ContractError, load_core, read_json, wire_json
from local_llm.datasets_v4 import transfer_problems, structure_size
from local_llm.design import build_plan, reference_depths, all_roles
from local_llm.gate import validate_gate
from local_llm.model_policy import identify_model, resolve_config, ModeError, response_channels
from local_llm.protocol_v2 import PROTOCOL, proof_only_trace
from local_llm.report import build_summary
from local_llm.runner import run, request_body, assess_response
from local_llm.tests.test_v02 import v2_payload


def metadata(kind="instruct", tag="qwen3:4b-instruct"):
    return {"show": {"capabilities": ["completion"] + (["thinking"] if kind == "thinking" else []),
             "model_info": {"general.architecture": "qwen3", "general.finetune": kind.title(),
                            "general.version": "2507", "qwen3.context_length": 262144}},
            "tag": {"name": tag, "digest": "offline-test-digest", "details": {"format": "gguf"}},
            "server": {"version": "offline-test"}, "running_models": {"models": []}}


def config(model="qwen3:4b-instruct", mode="auto", profile="factorized-v4"):
    return {"config_stage": "unresolved", "requested_mode": mode, "protocol": PROTOCOL,
            "model": model, "endpoint": "http://127.0.0.1:11434", "timeout_seconds": 300,
            "prompt_profile": profile,
            "options": {"temperature": None, "top_p": None, "num_ctx": None, "num_predict": None,
                        "top_k": 20, "min_p": 0.0, "repeat_penalty": 1.0, "num_thread": 6, "num_batch": 256}}


class V04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.info = load_core()
        cls.problems = transfer_problems()
        cls.plan = build_plan(cls.core, cls.problems, "smoke", 1, 1729)
        cls.observations = read_json(PACKAGE / "tests/fixtures/v03_pilot_observations.json")

    def payload(self, problem, case):
        """시험 전용 정답. 런타임 프롬프트/모델 결과 보충에 사용하지 않음."""
        if not case.get("task"):
            r = case["role"]
            return v2_payload(self.core.simulate(problem, r["A"] or "instance", r["D_policy"] or "shallow", r["M"] or 0))
        if case["task"] == "proof":
            payload = v2_payload(self.core.simulate(problem, "instance", case["depth_policy"], 0))
            return {"nodes": [{k: v for k, v in n.items() if k != "view"} for n in payload["nodes"]],
                    "selected_final_node_id": payload["selected_final_node_id"]}
        if case["task"] == "schema":
            trace = proof_only_trace(self.core, problem, case["provided_proof"])
            trace["views"] = {n["id"]: self.core._make_view(problem, trace["nodes"], n, "schema") for n in trace["nodes"]}
            converted = v2_payload(trace)
            return {"node_views": [{"node_id": n["node_id"], "view": n["view"]} for n in converted["nodes"]
                if case.get("view_scope") != "final_node_only" or n["node_id"] == trace["final"]]}
        if case["task"] == "review":
            trace, support, goal = calibration._supplied_support(self.core, problem, case["provided_proof"])
            return {"checked_node_ids": [n["id"] for n in trace["nodes"]], "support_valid": support,
                    "goal_match": goal, "proof_and_goal_accepts": support and goal}
        a = case["probe_atom"] == problem["goal"]
        b = a and case["probe_atom"] in problem["facts"]
        return {"answer_only_accepts": a, "proof_and_goal_accepts": b, "gap_detected": a != b}

    def reply(self, problem, case, cfg, thinking=False):
        response = {"model": cfg["model"], "done": True, "done_reason": "stop",
                    "message": {"role": "assistant", "content": wire_json(self.payload(problem, case))},
                    "eval_count": 100, "prompt_eval_count": 500}
        if thinking:
            response["message"]["thinking"] = "오프라인 시험용 채널 표식. 실제 모델 추론 아님."
        return response

    def mock_client(self, plan, cfg, meta, mutator=None):
        client = Mock()
        client.inspect.return_value = copy.deepcopy(meta)
        client.tag.return_value = copy.deepcopy(meta["tag"])
        client.running_model.return_value = copy.deepcopy(meta["tag"])
        ps = {p["id"]: p for p in plan["problems"]}
        values = [self.reply(ps[c["problem_id"]], c, cfg, meta["show"]["model_info"]["general.finetune"] == "Thinking")
                  for c in plan["cases"]]
        if mutator:
            mutator(values)
        client.chat.side_effect = [Reply(v, wire_json(v), 0.1) for v in values]
        return client

    def run_mock(self, plan, out, cfg=None, meta=None, mutator=None, **kwargs):
        cfg, meta = cfg or config(), meta or metadata()
        client = self.mock_client(plan, cfg, meta, mutator)
        with patch("local_llm.runner.OllamaClient", return_value=client), \
             patch("local_llm.runner.environment", return_value={"nvidia_smi": None}), \
             contextlib.redirect_stdout(io.StringIO()):
            result = run(self.core, self.info, plan, cfg, out, **kwargs)
        return result, client

    def test_actual_alias_detected_as_thinking_not_by_tag_name(self):
        actual = read_json(PACKAGE / "tests/fixtures/v03_model_metadata.json")
        self.assertEqual(identify_model(actual)["checkpoint_kind"], "thinking")
        actual["tag"]["name"] = "anything-instruct"
        self.assertEqual(identify_model(actual)["checkpoint_kind"], "thinking")

    def test_thinking_false_configuration_rejected(self):
        with self.assertRaisesRegex(ModeError, "불일치"):
            resolve_config(config(mode="non-thinking"), metadata("thinking"))

    def test_instruct_thinking_configuration_rejected(self):
        with self.assertRaisesRegex(ModeError, "불일치"):
            resolve_config(config(mode="thinking"), metadata())

    def test_auto_chooses_modes_and_separate_budgets(self):
        a = resolve_config(config(), metadata())
        b = resolve_config(config(), metadata("thinking"))
        self.assertIsNone(a["think"])
        self.assertTrue(b["think"])
        self.assertEqual(a["options"]["num_predict"], 4096)
        self.assertEqual(b["options"]["num_predict"], 8192)
        self.assertEqual(b["options"]["num_ctx"], 16384)

    def test_instruct_omits_think_and_thinking_sends_true(self):
        case = self.plan["cases"][0]
        for kind in ("instruct", "thinking"):
            cfg = resolve_config(config(), metadata(kind))
            body = request_body(cfg, case, self.problems[0])
            self.assertEqual("think" in body, kind == "thinking")
            if kind == "thinking": self.assertIs(body["think"], True)

    def test_identity_conflict_unknown_and_missing_capability_rejected(self):
        a = metadata()
        a["show"]["model_info"]["general.license.link"] = "https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507/blob/main/LICENSE"
        b = metadata(); b["show"]["model_info"].pop("general.version")
        c = metadata("thinking"); c["show"]["capabilities"] = ["completion"]
        for meta in (a, b, c):
            with self.subTest(meta=meta), self.assertRaises(ContractError): resolve_config(config(), meta)

    def test_license_body_words_do_not_determine_identity(self):
        m = metadata(); m["show"]["license"] = "Qwen Thinking supports something unrelated"
        self.assertEqual(identify_model(m)["checkpoint_kind"], "instruct")

    def test_overlarge_context_and_zero_thinking_temperature_rejected(self):
        c = config(); c["options"].update(num_ctx=4096, num_predict=4096)
        with self.assertRaises(ContractError): resolve_config(c, metadata())
        c = config(); c["options"]["temperature"] = 0
        with self.assertRaises(ContractError): resolve_config(c, metadata("thinking"))

    def test_modes_checked_before_any_model_call(self):
        client = Mock(); client.inspect.return_value = metadata("thinking")
        with tempfile.TemporaryDirectory() as temp, patch("local_llm.runner.OllamaClient", return_value=client):
            with self.assertRaises(ModeError):
                run(self.core, self.info, self.plan, config(mode="non-thinking"), Path(temp)/"new")
        client.chat.assert_not_called()

    def test_legacy_programmatic_config_cannot_bypass_mode_check(self):
        old = {k: v for k, v in config(mode="non-thinking").items() if k not in {"config_stage", "requested_mode"}}
        old["think"] = False
        client = Mock(); client.inspect.return_value = metadata("thinking")
        with tempfile.TemporaryDirectory() as temp, patch("local_llm.runner.OllamaClient", return_value=client):
            with self.assertRaises(ModeError): run(self.core, self.info, self.plan, old, Path(temp)/"run")
        client.chat.assert_not_called()

    def test_thinking_final_channel_only_is_parsed(self):
        c = self.plan["cases"][0]; p = self.problems[0]
        cfg = resolve_config(config(), metadata("thinking"))
        response = self.reply(p, c, cfg, True)
        response["message"]["thinking"] = '{"fake": true} 이것은 최종 응답이 아님'
        outcome, _ = assess_response(self.core, p, c, reference_depths(p), request_body(cfg,c,p), response, cfg["mode_policy"])
        self.assertEqual(outcome["status"], "accepted")

    def test_missing_thinking_or_empty_final_is_mode_error(self):
        c = self.plan["cases"][0]; p = self.problems[0]
        cfg = resolve_config(config(), metadata("thinking"))
        for mutate in (lambda x: x["message"].pop("thinking"), lambda x: x["message"].update(content="")):
            r = self.reply(p,c,cfg,True); mutate(r)
            outcome,_ = assess_response(self.core,p,c,reference_depths(p),request_body(cfg,c,p),r,cfg["mode_policy"])
            self.assertEqual(outcome["status"], "mode_error")

    def test_length_budget_is_not_a_semantic_failure(self):
        c = self.plan["cases"][0]; p = self.problems[0]
        cfg = resolve_config(config(), metadata("thinking")); r = self.reply(p,c,cfg,False)
        r.update(done_reason="length"); r["message"]["content"] = ""
        outcome,_ = assess_response(self.core,p,c,reference_depths(p),request_body(cfg,c,p),r,cfg["mode_policy"])
        self.assertEqual(outcome["status"], "truncated")

    def test_mode_failure_stops_after_first_call_but_records_remaining(self):
        cfg = config(model="qwen3:4b-thinking")
        def remove(values):
            values[0]["message"].pop("thinking")
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/"run"
            code, client = self.run_mock(self.plan,out,cfg,metadata("thinking",cfg["model"]),remove)
            self.assertEqual(code, 2); self.assertEqual(client.chat.call_count, 1)
            summary = read_json(out/"summary.json")
            self.assertEqual(summary["status_counts"], {"mode_error": 1, "not_started": 5})
            self.assertFalse(summary["execution_completed"])

    def test_transfer_suite_has_distinct_depths_and_full_factorial(self):
        plan = build_plan(self.core,self.problems,"pilot",1,1729)
        self.assertEqual(plan["assigned_calls"],39)
        self.assertEqual([reference_depths(p)["depths"] for p in self.problems], [[2,4],[2,3],[3,4]])
        for p in self.problems:
            self.core.check_problem(p)
            self.assertEqual(sum(c["problem_id"]==p["id"] for c in plan["cases"]),13)
            self.assertGreater(structure_size(p)["atoms"], structure_size(prompts_v4.DEMO_PROBLEM)["atoms"])

    def test_dataset_seed_is_deterministic_and_not_rechosen_per_role(self):
        self.assertEqual(transfer_problems(), transfer_problems())
        self.assertNotEqual(transfer_problems(1), transfer_problems(2))
        self.assertEqual([reference_depths(p)["depths"] for p in transfer_problems(1)],
                         [reference_depths(p)["depths"] for p in transfer_problems(2)])

    def test_all_planned_joint_certificates_are_constructible_offline(self):
        plan = build_plan(self.core,self.problems,"pilot",1,1729)
        cfg = resolve_config(config(),metadata())
        for c in plan["cases"]:
            p = next(p for p in self.problems if p["id"]==c["problem_id"])
            outcome,_ = assess_response(self.core,p,c,reference_depths(p),request_body(cfg,c,p),self.reply(p,c,cfg),cfg["mode_policy"])
            with self.subTest(case=c["role_id"], problem=p["id"]): self.assertEqual(outcome["status"],"accepted")

    def test_reference_generator_never_used_in_new_prompt_assembly(self):
        with patch.object(self.core,"simulate",side_effect=AssertionError("금지")), \
             patch.object(self.core,"_make_view",side_effect=AssertionError("금지")):
            plan = build_plan(self.core,self.problems,"pilot",1,1729)
            cal = calibration_v4.build_calibration_plan(self.core)
            cfg = resolve_config(config(),metadata())
            for pl in (plan,cal):
                for case in pl["cases"]:
                    p = next(p for p in pl["problems"] if p["id"]==case["problem_id"])
                    text = wire_json(request_body(cfg,case,p)["messages"])
                    self.assertNotIn('"expected"',text)
                    self.assertNotIn('"reference_depths"',text)
                    self.assertNotIn('"D_target"',text)

    def test_examples_ablation_changes_only_common_examples(self):
        for role in all_roles():
            a=prompts_v4.messages(self.problems[0],role,"factorized-v4")
            b=prompts_v4.messages(self.problems[0],role,"definitions-v4")
            self.assertEqual(a[1],b[1])
            self.assertEqual(a[0]["content"], b[0]["content"]+prompts_v4.examples())

    def test_schema_and_budget_same_for_all_joint_roles(self):
        cfg=resolve_config(config(),metadata())
        bodies=[request_body(cfg,{"role":r,"seed":1729},self.problems[0]) for r in all_roles()]
        self.assertTrue(all(b["format"]==bodies[0]["format"] for b in bodies))
        self.assertTrue(all(b["options"]==bodies[0]["options"] for b in bodies))
        self.assertTrue(all(b["messages"][0]==bodies[0]["messages"][0] for b in bodies))

    def test_calibration_twentyfour_and_three_truth_patterns(self):
        plan=calibration_v4.build_calibration_plan(self.core)
        self.assertEqual(Counter(c["task"] for c in plan["cases"]),{"proof":6,"schema":6,"review":6,"criterion":6})
        patterns=Counter()
        for c in plan["cases"]:
            p=next(p for p in plan["problems"] if p["id"]==c["problem_id"])
            answer=self.payload(p,c)
            audit=calibration_v4.assess_payload(self.core,p,c,answer)
            self.assertTrue(audit["valid_completion"],(c["role_id"],audit))
            if c["task"]=="criterion": patterns[tuple(answer.values())]+=1
        self.assertEqual(sorted(patterns.values()),[2,2,2])

    def test_final_only_scope_has_no_conflicting_all_nodes_instruction(self):
        plan=calibration_v4.build_calibration_plan(self.core)
        c=next(c for c in plan["cases"] if c.get("view_scope")=="final_node_only")
        p=next(p for p in plan["problems"] if p["id"]==c["problem_id"])
        text=prompts_v4.calibration_messages(p,c,"definitions-v4")[0]["content"]
        self.assertNotIn("모든 노드에 universal_schema view를 작성",text)
        self.assertIn("최종 노드 항목 딱 하나",text)

    def test_extra_views_are_not_silently_removed_in_final_only_scope(self):
        plan=calibration_v4.build_calibration_plan(self.core)
        c=next(c for c in plan["cases"] if c.get("view_scope")=="final_node_only")
        p=next(p for p in plan["problems"] if p["id"]==c["problem_id"])
        answer=self.payload(p,c); answer["node_views"].append(copy.deepcopy(answer["node_views"][0]))
        before=copy.deepcopy(answer)
        self.assertFalse(calibration_v4.assess_payload(self.core,p,c,answer)["valid_completion"])
        self.assertEqual(before,answer)

    def test_claiming_conclusion_as_fact_still_rejected(self):
        plan=calibration_v4.build_calibration_plan(self.core)
        c=next(c for c in plan["cases"] if c.get("view_scope")=="final_node_only")
        p=next(p for p in plan["problems"] if p["id"]==c["problem_id"])
        answer=self.payload(p,c); view=answer["node_views"][0]["view"]
        view["clauses"]=[{"if":[],"then":view["conclusion_var"]}]
        self.assertFalse(calibration_v4.assess_payload(self.core,p,c,answer)["valid_completion"])

    def test_all_twentyfour_mocked_run_and_report(self):
        plan=calibration_v4.build_calibration_plan(self.core)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"cal"
            code,client=self.run_mock(plan,out)
            self.assertEqual(code,0); self.assertEqual(client.chat.call_count,24)
            s=read_json(out/"summary.json")
            self.assertTrue(s["performance_passed"])
            self.assertEqual(len(s["component_diagnostics"]["criterion_expected_patterns"]),3)
            self.assertEqual(len(s["component_diagnostics"]["schema_scope_pairs"]),3)
            self.assertFalse(s["component_diagnostics"]["criterion_constant_output_observed"])

    def test_actual_thirtynine_verdicts_preserved_and_nas_separated(self):
        records=[]; problems={}; cases=[]
        original=copy.deepcopy(self.observations)
        for x in self.observations["cases"]:
            p=x["problem"]; c=x["case"]; b=self.observations["bodies"][x["body_index"]]
            outcome,_=assess_response(self.core,p,c,reference_depths(p),b,x["response"])
            with self.subTest(case=c["case_id"]):
                self.assertEqual(outcome["status"],x["status"])
                self.assertEqual(outcome["audit"]["valid_completion"],x["valid_completion"])
                self.assertEqual(outcome["audit"]["role_adherent"],x["role_adherent"])
            records.append({"case":c,**outcome});problems[p["id"]]=p;cases.append(c)
        plan={"problems":list(problems.values()),"cases":cases,"scope":"historical","warnings":[]}
        summary,rows,_=build_summary(plan,records)
        self.assertEqual(summary["status_counts"],{"accepted":12,"role_mismatch":14,"invalid_trace":13})
        self.assertEqual(summary["valid_completions"],26)
        for axis,values in summary["per_axis_adherence"].items():
            self.assertEqual(values["missing_or_not_assessable"],5)
            self.assertEqual(values["matched"]+values["mismatched"]+values["missing_or_not_assessable"],36)
        self.assertEqual(self.observations,original)

    def test_partial_graph_correctness_does_not_upgrade_failure(self):
        found=False
        for x in self.observations["cases"]:
            outcome,_=assess_response(self.core,x["problem"],x["case"],reference_depths(x["problem"]),
                self.observations["bodies"][x["body_index"]],x["response"])
            raw=outcome["raw_diagnostics"]
            if raw.get("unrelated_node_ids"):
                found=True
                self.assertEqual(outcome["status"],"invalid_trace")
                self.assertTrue(raw["all_local_steps_valid"])
                self.assertIsNotNone(raw["selected_component_depth"])
                self.assertFalse(outcome["audit"]["valid_completion"])
                self.assertEqual(outcome["audit"]["role_matches"],{"A":None,"D":None,"M":None})
        self.assertTrue(found)

    def test_new_smoke_gate_replays_same_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"smoke"
            code,_=self.run_mock(self.plan,out)
            self.assertEqual(code,0)
            cfg=read_json(out/"manifest.json")["frozen"]["config"]
            next_plan=build_plan(self.core,self.problems,"pilot",1,1729)
            self.assertTrue(validate_gate(self.core,out,cfg,next_plan)["passed"])
            cfg["prompt_profile"]="definitions-v4"
            with self.assertRaises(ContractError): validate_gate(self.core,out,cfg,next_plan)

    def test_model_failures_do_not_prevent_next_case_or_readiness(self):
        def change(values):
            v=json.loads(values[0]["message"]["content"])
            v["selected_final_node_id"]="not_a_node"
            values[0]["message"]["content"]=wire_json(v)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"smoke"
            code,client=self.run_mock(self.plan,out,mutator=change)
            self.assertEqual(code,0);self.assertEqual(client.chat.call_count,6)
            cfg=read_json(out/"manifest.json")["frozen"]["config"]
            plan=build_plan(self.core,self.problems,"pilot",1,1729)
            self.assertEqual(validate_gate(self.core,out,cfg,plan)["model_failures_retained"],1)
            with self.assertRaises(ContractError): validate_gate(self.core,out,cfg,plan,"strict")

    def test_changed_live_digest_rejected_before_pilot(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"smoke";self.run_mock(self.plan,out)
            meta=metadata();meta["tag"]["digest"]="different-weights"
            plan=build_plan(self.core,self.problems,"pilot",1,1729)
            client=self.mock_client(plan,config(),meta)
            with patch("local_llm.runner.OllamaClient",return_value=client), \
                 patch("local_llm.runner.environment",return_value={"nvidia_smi":None}), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ContractError,"digest"):
                    run(self.core,self.info,plan,config(),Path(temp)/"pilot",gate=out)
            client.chat.assert_not_called()

    def test_resume_does_not_recall_completed_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"smoke";self.run_mock(self.plan,out)
            code,client=self.run_mock(self.plan,out,resume=True)
            self.assertEqual(code,0);client.chat.assert_not_called()

    def test_changed_context_cannot_resume_same_result_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"smoke";self.run_mock(self.plan,out)
            cfg=config();cfg["options"]["num_ctx"]=16384
            with self.assertRaises(ContractError):self.run_mock(self.plan,out,cfg,resume=True)

    def test_cli_plan_and_selfcheck_have_no_network(self):
        with patch("local_llm.__main__.OllamaClient",side_effect=AssertionError("네트워크 금지")), \
             patch("local_llm.runner.OllamaClient",side_effect=AssertionError("네트워크 금지")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["plan","--profile","pilot"]),0)
            self.assertEqual(main(["selfcheck"]),0)
        self.assertIn('"assigned_calls": 39',output.getvalue())

    def test_cli_doctor_only_reads_metadata(self):
        client=Mock();client.inspect.return_value=metadata()
        with patch("local_llm.__main__.OllamaClient",return_value=client), \
             patch("local_llm.__main__.environment",return_value={"nvidia_smi":None}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["doctor"]),0)
        client.chat.assert_not_called()
        self.assertIn('"checkpoint_kind": "instruct"',output.getvalue())

    def test_cli_run_defaults_reach_checked_v4_path(self):
        client=self.mock_client(self.plan,config(),metadata())
        with tempfile.TemporaryDirectory() as temp, \
             patch("local_llm.runner.OllamaClient",return_value=client), \
             patch("local_llm.runner.environment",return_value={"nvidia_smi":None}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["run","--profile","smoke","--out",str(Path(temp)/"run")]),0)
        self.assertEqual(client.chat.call_count,6)
        for args in client.chat.call_args_list:
            body=args.args[0]
            self.assertEqual(body["model"],"qwen3:4b-instruct")
            self.assertNotIn("think",body)


if __name__ == "__main__":
    unittest.main()
