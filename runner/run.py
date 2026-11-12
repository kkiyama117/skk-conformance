"""Conformance runner: drive engines through adapters and print a pass table."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import tomllib

from runner import adapter, cases

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_USER_MARKERS = ";; okuri-ari entries.\n;; okuri-nasi entries.\n"
_ENGINE_KEYS = frozenset(("command", "build", "available"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m runner.run")
    parser.add_argument("--engines", type=pathlib.Path, default=_ROOT / "engines.toml")
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--cases", type=pathlib.Path, default=_ROOT / "cases")
    parser.add_argument("--dicts", type=pathlib.Path, default=_ROOT / "dict")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--logs", type=pathlib.Path, default=_ROOT / "build" / "logs")
    return parser


def _read_engines(path: pathlib.Path):
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None, ("-", "engines-key")
    if not isinstance(document, dict):
        return None, ("-", "engines-key")
    if any(key != "engine" for key in document):
        return None, ("-", "engines-key")
    engines = document.get("engine", {})
    if not isinstance(engines, dict):
        return None, ("-", "engines-key")
    for name, table in engines.items():
        if not name or not isinstance(table, dict):
            return None, ("-" if not name else name, "engines-key")
        if any(key not in _ENGINE_KEYS for key in table):
            return None, (name, "engines-key")
        command = table.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) for item in command)
        ):
            return None, (name, "engines-key")
        for key in ("build", "available"):
            if key in table and (
                not isinstance(table[key], list)
                or not all(isinstance(item, str) for item in table[key])
            ):
                return None, (name, "engines-key")
    return engines, None


def _run_helper(
    argv: list[str], cwd: pathlib.Path, log_path: pathlib.Path | None = None
) -> bool:
    if not argv:
        return False
    try:
        if log_path is None:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            with log_path.open("ab") as log:
                completed = subprocess.run(
                    argv,
                    cwd=cwd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
    except OSError:
        return False
    return completed.returncode == 0


def _hello(obj: adapter.Adapter, name: str) -> str | None:
    try:
        answer = obj.start()
    except (adapter.AdapterTimeout, adapter.AdapterBroken, OSError):
        obj.close()
        return None
    if (
        answer.get("type") != "hello"
        or type(answer.get("protocol")) is not int
        or answer.get("protocol") != 1
        or answer.get("engine") != name
    ):
        obj.close()
        return None
    version = answer.get("version")
    return version if isinstance(version, str) else "unknown"


def _write_user_dict(
    path: pathlib.Path, user_dict: str | None, dict_dir: pathlib.Path
) -> None:
    if user_dict is None:
        path.write_bytes(_USER_MARKERS.encode("utf-8"))
    else:
        path.write_bytes((dict_dir / f"{user_dict}.jisyo").read_bytes())


def _case_request(case: cases.Case, dict_dir: pathlib.Path, user_dict: pathlib.Path):
    return {
        "type": "case",
        "id": case.id,
        "dicts": [
            {"path": str((dict_dir / f"{name}.jisyo").resolve()), "encoding": "utf-8"}
            for name in case.dicts
        ],
        "user_dict": {"path": str(user_dict), "encoding": "utf-8"},
        "steps": [{"keys": list(step.keys)} for step in case.steps],
    }


def _malformed() -> tuple[dict, bool]:
    return {"status": "error", "code": "malformed"}, True


def _classify(case: cases.Case, answer: dict) -> tuple[dict, bool]:
    if "error" in answer and answer.get("type") == "result" and answer.get("id") == case.id:
        error = answer["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if not isinstance(code, str):
            return _malformed()
        return {"status": "error", "code": code}, False
    if answer.get("type") != "result" or answer.get("id") != case.id:
        return _malformed()
    steps = answer.get("steps")
    if not isinstance(steps, list) or len(steps) != len(case.steps):
        return _malformed()
    for item in steps:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) for key in ("text", "preedit", "mode")
        ):
            return _malformed()
    for number, (step, item) in enumerate(zip(case.steps, steps), 1):
        for field in ("text", "preedit", "mode"):
            expected = getattr(step, field)
            if expected is not None and expected != item[field]:
                return {
                    "status": "fail",
                    "step": number,
                    "field": field,
                    "expected": expected,
                    "actual": item[field],
                }, False
    return {"status": "pass"}, False


def _run_case(
    obj: adapter.Adapter,
    case: cases.Case,
    dict_dir: pathlib.Path,
    timeout: float,
) -> tuple[dict, bool]:
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        user_dict = root / "user.jisyo"
        _write_user_dict(user_dict, case.user_dict, dict_dir)
        request = _case_request(case, dict_dir, user_dict)
        try:
            answer = obj.request(request, timeout)
        except adapter.AdapterTimeout:
            return {"status": "timeout"}, True
        except adapter.AdapterBroken:
            return {"status": "error", "code": "broken"}, True
    return _classify(case, answer)


def _run_engine(
    name: str,
    config: dict,
    cwd: pathlib.Path,
    loaded: list[cases.Case],
    dict_dir: pathlib.Path,
    timeout: float,
    logs: pathlib.Path,
):
    if "available" in config and not _run_helper(config["available"], cwd):
        return {"mark": "n/a", "results": {}}
    if "build" in config and not _run_helper(
        config["build"], cwd, logs / f"{name}.build.log"
    ):
        return {"mark": "build-failed", "results": {}}

    obj = adapter.Adapter(config["command"], cwd, logs / f"{name}.stderr.log")
    version = _hello(obj, name)
    if version is None:
        return {"mark": "hello-failed", "results": {}}

    results: dict[str, dict] = {}
    try:
        index = 0
        while index < len(loaded):
            case = loaded[index]
            record, restart = _run_case(obj, case, dict_dir, timeout)
            results[case.id] = record
            index += 1
            if not restart or index >= len(loaded):
                continue
            obj.kill()
            if _hello(obj, name) is None:
                for later in loaded[index:]:
                    results[later.id] = {"status": "error", "code": "broken"}
                break
    finally:
        obj.close()
    return {"mark": "ran", "version": version, "results": results}


def _group_rows(loaded: list[cases.Case]):
    order: list[str] = []
    groups: dict[str, tuple[str, list[cases.Case]]] = {}
    for case in loaded:
        if case.file not in groups:
            groups[case.file] = (case.group, [])
            order.append(case.file)
        groups[case.file][1].append(case)
    return [(groups[file][0], groups[file][1]) for file in order]


def _cell(run_result: dict, file_cases: list[cases.Case]) -> str:
    if run_result["mark"] != "ran":
        return run_result["mark"]
    passed = sum(
        1
        for case in file_cases
        if run_result["results"][case.id]["status"] == "pass"
    )
    return f"{passed}/{len(file_cases)}"


def _print_table(
    loaded: list[cases.Case], names: list[str], runs: dict[str, dict]
) -> None:
    labels = []
    for name in names:
        run_result = runs[name]
        if run_result["mark"] == "ran":
            labels.append(f"{name} {run_result['version']}")
        else:
            labels.append(name)
    print("| group | " + " | ".join(labels) + " |")
    print("|" + "---|" * (len(labels) + 1))
    for group, file_cases in _group_rows(loaded):
        cells = [_cell(runs[name], file_cases) for name in names]
        print("| " + group + " | " + " | ".join(cells) + " |")
    totals = []
    for name in names:
        run_result = runs[name]
        if run_result["mark"] != "ran":
            totals.append(run_result["mark"])
            continue
        passed = sum(
            1
            for case in loaded
            if run_result["results"][case.id]["status"] == "pass"
        )
        totals.append(f"{passed}/{len(loaded)}")
    print("| total | " + " | ".join(totals) + " |")


def _print_details(
    loaded: list[cases.Case], names: list[str], runs: dict[str, dict]
) -> None:
    for name in names:
        run_result = runs[name]
        if run_result["mark"] != "ran":
            continue
        print(f"## {name}")
        for case in loaded:
            record = run_result["results"][case.id]
            if record["status"] == "pass":
                continue
            if record["status"] == "fail":
                print(
                    f"- {case.id}: fail step {record['step']} "
                    f"{record['field']} "
                    f"expected {json.dumps(record['expected'], ensure_ascii=False)} "
                    f"got {json.dumps(record['actual'], ensure_ascii=False)}"
                )
            elif record["status"] == "error":
                print(f"- {case.id}: error {record['code']}")
            else:
                print(f"- {case.id}: timeout")


def _json_object(
    loaded: list[cases.Case],
    names: list[str],
    runs: dict[str, dict],
    details: bool,
) -> dict:
    engines = {}
    for name in names:
        run_result = runs[name]
        entry: dict = {"mark": run_result["mark"]}
        if run_result["mark"] == "ran":
            entry["version"] = run_result["version"]
        case_results = {}
        for case in loaded:
            record = run_result["results"].get(case.id)
            if record is None:
                continue
            item = {"status": record["status"]}
            if record["status"] == "fail":
                item["step"] = record["step"]
                item["field"] = record["field"]
                if details:
                    item["expected"] = record["expected"]
                    item["actual"] = record["actual"]
            elif record["status"] == "error":
                item["code"] = record["code"]
            case_results[case.id] = item
        entry["cases"] = case_results
        engines[name] = entry
    return {"protocol": 1, "engines": engines}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    loaded, problems = cases.load_cases(args.cases, args.dicts)
    if problems:
        for problem in problems:
            print(f"{problem.file}: {problem.where}: {problem.code}")
        return 2

    engines_path = args.engines.resolve()
    engines, problem = _read_engines(engines_path)
    if problem is not None:
        print(f"engines: {problem[0]}: {problem[1]}")
        return 2

    if args.engine:
        for name in args.engine:
            if name not in engines:
                parser.print_usage(sys.stderr)
                print(
                    f"{parser.prog}: error: unknown engine: {name}",
                    file=sys.stderr,
                )
                return 2
        names = list(args.engine)
    else:
        names = list(engines)

    logs = args.logs
    logs.mkdir(parents=True, exist_ok=True)
    cwd = engines_path.parent
    runs = {
        name: _run_engine(
            name,
            engines[name],
            cwd,
            loaded,
            args.dicts,
            args.timeout,
            logs,
        )
        for name in names
    }

    _print_table(loaded, names, runs)
    if args.details:
        _print_details(loaded, names, runs)
    if args.json is not None:
        document = _json_object(loaded, names, runs, args.details)
        args.json.write_text(
            json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
