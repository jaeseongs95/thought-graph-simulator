from __future__ import annotations
import contextlib
import io
import shutil
import unittest
from pathlib import Path
from paired_probe_v048.audit import audit_run
from paired_probe_v048.contracts import ContractError, read_json, wire, strict_json, digest, sha, write_json
from paired_probe_v048.runner import execute
from tests_v048.fixtures import experiment


def events_of(out):
    return [strict_json(line) for line in (out/"events.jsonl").read_bytes().splitlines()]


def reseal(out,events):
    tip=read_json(out/"plan.snapshot.json")["plan_sha256"]
    for e in events:
        e["previous_hash"]=tip;e.pop("event_hash",None);e["event_hash"]=digest(e);tip=e["event_hash"]
    (out/"events.jsonl").write_bytes(b"".join(wire(e)+b"\n" for e in events))
    status=read_json(out/"status.json");status["event_tip"]=tip;write_json(out/"status.json",status)


class IntegrationTests(unittest.TestCase):
    def test_complete_single_new_seed_96_calls(self):
        with experiment() as (_,state,_,_,_,r):
            self.assertTrue(r["data_complete"]);self.assertTrue(r["comparative_analysis_ready"])
            self.assertEqual(len(state.requests),96);self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"],24)
    def test_default_scale_960_actual_fake_http_calls(self):
        from paired_probe_v048.plan import default_seeds
        with experiment("original_false",seeds=default_seeds([1729])) as (_,state,_,_,_,r):
            self.assertEqual(len(state.requests),960);self.assertEqual(r["inference_calls"],960)
            self.assertEqual(r["matching_v047_seeds"],10)
            self.assertEqual(r["arms"]["original"]["final_correct"],180)
            self.assertEqual(r["arms"]["commuted"]["final_correct"],240)
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"],240)
    def test_original_false_is_valid_failure_data(self):
        with experiment("original_false") as (_,_,_,_,_,r):
            self.assertTrue(r["comparative_analysis_ready"])
            self.assertEqual(r["arms"]["original"]["positive_correct"],0)
            self.assertEqual(r["arms"]["original"]["final_accuracy"],0.75)
            self.assertEqual(r["matching_v047_seeds"],1)
    def test_all_success_does_not_fabricate_improvement(self):
        with experiment() as (_,_,_,_,_,r):
            self.assertEqual(r["paired_final_outcomes"]["commuted-original"]["final_accuracy_delta"],0)
            self.assertEqual(r["matching_v047_seeds"],0)
    def test_per_seed_not_hidden_by_pooling(self):
        with experiment("seed_sensitive",seeds=[101,202]) as (_,_,_,_,_,r):
            pair=r["paired_final_outcomes"]["commuted-original"]
            self.assertEqual([p["final_accuracy_delta"] for p in pair["per_seed"]],[0,0.25])
            self.assertEqual(pair["seed_wins"],1);self.assertEqual(pair["seed_ties"],1)
            self.assertIsNone(pair["inferential_p_value"]);self.assertIsNone(pair["confidence_interval"])
    def test_best_direct_comparator_is_retained(self):
        with experiment("original_false") as (_,_,_,_,_,r):
            pair=r["paired_final_outcomes"]["pipeline-commuted"]
            self.assertEqual(pair["final_accuracy_delta"],0)
    def test_wrong_not_forwarded_unchanged(self):
        with experiment("wrong_not") as (_,state,_,_,_,r):
            self.assertEqual(r["arms"]["pipeline"]["strict_trace_correct"],0)
            self.assertEqual(r["arms"]["pipeline"]["final_correct"],12)
            for i,body in enumerate(state.requests):
                values=strict_json(body["messages"][1]["content"][7:])
                if values["expression"]=="(NOT b)":
                    child=strict_json(state.requests[i+1]["messages"][1]["content"][7:])
                    self.assertIs(child["b"],values["b"])
    def test_invalid_not_blocks_only_child(self):
        with experiment("invalid_not") as (_,state,_,_,_,r):
            self.assertEqual(len(state.requests),72)
            self.assertEqual(r["recorded_slots"],96);self.assertTrue(r["data_complete"])
            self.assertEqual(r["call_status_counts"]["blocked"],24)
    def test_http_failure_stops_without_retry(self):
        with experiment("http_error") as (_,state,_,_,_,r):
            self.assertEqual(len(state.requests),1);self.assertFalse(r["data_complete"])
            self.assertIsNone(r["paired_final_outcomes"]["commuted-original"]["final_accuracy_delta"])
            self.assertGreater(r["paired_final_outcomes"]["commuted-original"]["unobserved_pairs"],0)
    def test_unexecuted_trials_are_not_boolean_failures(self):
        with experiment("http_error") as (_,_,_,_,_,r):
            unobserved=[x for x in r["trials"] if not x["observed"]]
            self.assertTrue(unobserved);self.assertTrue(all(x["final_correct"] is None for x in unobserved))
    def test_wrong_response_model_is_infrastructure_error(self):
        with experiment("wrong_model") as (_,state,_,_,_,r):
            self.assertEqual(len(state.requests),1);self.assertFalse(r["comparative_analysis_ready"])
            self.assertEqual(r["call_status_counts"]["response_identity_error"],1)
    def test_runtime_identity_checked_each_round(self):
        with experiment() as (_,_,_,p,out,_):
            status=read_json(out/"status.json")
            self.assertEqual(len(status["identity_checkpoints"]),p["cycles"]+1)
    def test_identity_error_before_run_keeps_summary(self):
        with experiment("before_identity_error") as (_,state,_,_,out,r):
            self.assertEqual(len(state.requests),0);self.assertFalse(r["data_complete"])
            self.assertTrue(r["identity_errors"]);self.assertTrue((out/"summary.ko.md").is_file())
    def test_midrun_identity_error_preserved(self):
        with experiment("runtime_drift") as (_,state,_,_,out,r):
            self.assertEqual(len(state.requests),16)
            self.assertFalse(r["comparative_analysis_ready"]);self.assertTrue(r["identity_errors"])
    def test_missing_usage_not_zero(self):
        with experiment("missing_usage") as (_,_,_,_,_,r):
            c=r["arms"]["original"]["costs"]["prompt_eval_count"]
            self.assertIsNone(c["total"]);self.assertEqual(c["observed_calls"],0)
    def test_pipeline_cost_sums_two_calls(self):
        with experiment() as (_,_,_,_,_,r):
            c=r["arms"]["pipeline"]["costs"];o=r["arms"]["original"]["costs"]
            self.assertEqual(c["eval_count"]["total"],2*o["eval_count"]["total"])
            self.assertEqual(c["complete_path_server_total_minus_load_ns"]["median"],2000000)
    def test_identical_seed_repeats_are_descriptive(self):
        with experiment("original_false") as (_,_,_,_,_,r):
            self.assertEqual(r["unstable_request_groups"],0)
            self.assertEqual(r["repeated_request_groups"],16)
            self.assertTrue(all(x["recorded_calls"]==6 for x in r["request_repeats"]))
    def test_nondeterministic_repeats_are_flagged(self):
        with experiment("repeat_unstable") as (_,_,_,_,_,r):
            self.assertEqual(r["unstable_request_groups"],1)
    def test_truncated_responses_are_invalid_not_corrected(self):
        with experiment("truncated") as (_,_,_,_,_,r):
            self.assertTrue(r["data_complete"]);self.assertEqual(r["arms"]["original"]["valid_final_values"],0)
    def test_fake_data_never_claims_live_inference(self):
        with experiment() as (_,_,_,_,_,r):
            self.assertEqual(r["evidence_kind"],"synthetic_fixture");self.assertFalse(r["new_model_inference"])
    def test_audit_offline_no_new_requests(self):
        with experiment() as (_,state,p,_,out,r):
            count=len(state.requests);again=audit_run(p,out)
            self.assertEqual(again,r);self.assertEqual(count,len(state.requests))
    def test_run_does_not_overwrite(self):
        with experiment() as (_,state,p,_,out,_):
            count=len(state.requests)
            with self.assertRaises(ContractError): execute(p,out)
            self.assertEqual(count,len(state.requests))
    def test_outputs_csv_and_seed_json(self):
        with experiment() as (_,_,_,_,out,_):
            for name in ("calls.csv","seeds.csv","seed_results.json","trials.csv","request_repeats.csv"):
                self.assertTrue((out/name).stat().st_size>0)
    def test_tamper_derived_summary_is_ignored(self):
        with experiment("original_false") as (_,_,p,_,out,_):
            write_json(out/"summary.json",{"all_pass":True})
            r=audit_run(p,out)
            self.assertEqual(r["arms"]["original"]["final_correct"],18)
    def test_response_tamper_detected(self):
        with experiment() as (_,_,p,_,out,_):
            path=next((out/"calls").rglob("response.raw.json"));path.write_bytes(b"{}")
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_resealed_seed_change_detected(self):
        with experiment() as (_,_,p,_,out,_):
            events=events_of(out);e=events[0]
            path=out/"calls"/e["slot"]["id"]/"request.wire.json"
            request=read_json(path);request["options"]["seed"]=999;path.write_bytes(wire(request))
            e["request_sha256"]=sha(path.read_bytes());reseal(out,events)
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_resealed_parent_link_change_detected(self):
        with experiment() as (_,_,p,_,out,_):
            events=events_of(out);e=next(e for e in events if e["slot"]["stage"]=="and")
            e["parent"]["response_sha256"]="0"*64;reseal(out,events)
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_deleting_failed_event_detected(self):
        with experiment("original_false") as (_,_,p,_,out,_):
            events=events_of(out);events.pop();reseal(out,events)
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_reordering_events_detected(self):
        with experiment() as (_,_,p,_,out,_):
            events=events_of(out);events[0],events[1]=events[1],events[0];reseal(out,events)
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_removed_identity_checkpoint_detected(self):
        with experiment() as (_,_,p,_,out,_):
            (out/"runtime.round_001.json").unlink()
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_source_snapshot_tamper_detected(self):
        with experiment() as (_,_,p,_,out,_):
            (out/"source_snapshot"/"paired_probe_v048"/"runner.py").write_text("# changed\n")
            with self.assertRaises(ContractError): audit_run(p,out)
    def test_hidden_call_folder_detected(self):
        with experiment() as (_,_,p,_,out,_):
            (out/"calls"/"extra_call").mkdir()
            with self.assertRaises(ContractError): audit_run(p,out)
