"""prepare -> show -> run -> audit -> bundle; no retry or model download."""
from __future__ import annotations

import argparse
import json
import sys
import unittest
import zipfile
from pathlib import Path

from .contracts import ContractError, read_plan_json, require


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='v061 Gemma K01 direction-choice experiment: 40 calls')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('selftest')
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--baseline-bundle', type=Path, required=True)
    prepare.add_argument('--out', type=Path, required=True)
    show = commands.add_parser('show')
    show.add_argument('--plan', type=Path, required=True)
    run = commands.add_parser('run')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    for name in ('audit', 'bundle'):
        command = commands.add_parser(name)
        command.add_argument('--plan', type=Path, required=True)
        command.add_argument('--run', type=Path, required=True)
        if name == 'bundle':
            command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == 'selftest':
            root = Path(__file__).resolve().parent.parent
            root_text = str(root)
            if root_text in sys.path:
                sys.path.remove(root_text)
            sys.path.insert(0, root_text)
            loaded_tests = sys.modules.get('tests')
            if loaded_tests is not None:
                origin = Path(getattr(loaded_tests, '__file__', '')).resolve()
                if not origin.is_relative_to((root / 'tests').resolve()):
                    for name in [name for name in sys.modules
                                 if name == 'tests' or name.startswith('tests.')]:
                        del sys.modules[name]
            loader = unittest.TestLoader()
            suite = loader.discover(str(root / 'tests'), pattern='test_*.py',
                                    top_level_dir=str(root))
            require(suite.countTestCases() > 0, 'Empty test suite refused')
            return (0 if unittest.TextTestRunner(verbosity=2)
                    .run(suite).wasSuccessful() else 1)
        if args.command in ('prepare', 'show'):
            from .plan import prepare as prepare_plan, validate_plan
            plan = (prepare_plan(args.baseline_bundle, args.out)
                    if args.command == 'prepare'
                    else read_plan_json(args.plan))
            validate_plan(plan)
            print(json.dumps({key: plan[key] for key in (
                'contract', 'plan_sha256', 'model_keys', 'modes', 'variants',
                'schedule_seed', 'boundary_cells', 'max_calls')},
                ensure_ascii=False, indent=2))
            print('Offline plan validation complete; no inference was performed.')
            return 0
        if args.command == 'run':
            from .runner import execute
            report = execute(args.plan, args.out)
        elif args.command == 'audit':
            from .audit import audit_run
            report = audit_run(args.plan, args.run, write_report=True)
        else:
            from .evidence import bundle_run
            report = bundle_run(args.plan, args.run, args.out)
            print('Evidence ZIP:', args.out)
        print(json.dumps({key: report[key] for key in (
            'data_integrity', 'data_complete', 'inference_calls',
            'max_inference_calls', 'failure_stage', 'failure_kind',
            'failure_slot_id', 'run_error')}, ensure_ascii=False, indent=2))
        return 0 if args.command == 'bundle' or report['data_complete'] else 3
    except (ContractError, OSError, ValueError, KeyError, TypeError,
            zipfile.BadZipFile) as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
