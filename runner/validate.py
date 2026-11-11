"""Command-line validator for conformance case files and dictionaries."""

from __future__ import annotations

import argparse
import pathlib
import sys

from runner import cases


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def _parser() -> argparse.ArgumentParser:
    root = pathlib.Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(prog="python3 -m runner.validate")
    parser.add_argument("--cases", type=pathlib.Path, default=root / "cases")
    parser.add_argument("--dicts", type=pathlib.Path, default=root / "dict")
    parser.add_argument("--min-cases", type=_non_negative_int, default=0)
    return parser


def _files(directory: pathlib.Path, suffix: str) -> list[pathlib.Path]:
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.name.endswith(suffix)
        ),
        key=lambda path: path.name,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    loaded, problems = cases.load_cases(args.cases, args.dicts)
    dict_files = _files(args.dicts, ".jisyo")
    for path in dict_files:
        problems.extend(cases.validate_dict(path))

    if problems:
        for problem in problems:
            print(f"{problem.file}: {problem.where}: {problem.code}")
        return 1
    if len(loaded) < args.min_cases:
        print("cases: -: case-count")
        return 1

    case_files = _files(args.cases, ".toml")
    print(
        f"OK {len(loaded)} cases in {len(case_files)} files, "
        f"{len(dict_files)} dictionaries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
