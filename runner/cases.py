"""Case-file loading and dictionary validation for the conformance runner."""

from __future__ import annotations

import pathlib
import re
import tomllib
from dataclasses import dataclass

MODES = ("hiragana", "katakana", "hankaku-katakana", "zenkaku-latin", "ascii")

_FILE_NAME = re.compile(r"[0-9]{2}-[a-z0-9-]+\.toml")
_ID = re.compile(r"[a-z0-9]+(\.[a-z0-9-]+)+")
_DICT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_ENTRY = re.compile(r"([^ /]+) /(?:[^/;\[\](][^/;\[\]]*/)+")
_BOM = b"\xef\xbb\xbf"
_CODING = ";; -*- mode: fundamental; coding: utf-8 -*-"
_ARI = ";; okuri-ari entries."
_NASI = ";; okuri-nasi entries."
_CASE_KEYS = frozenset(("id", "dicts", "user_dict", "note", "step"))
_STEP_KEYS = frozenset(("keys", "text", "preedit", "mode"))


@dataclass(frozen=True)
class Step:
    keys: tuple[str, ...]
    text: str | None
    preedit: str | None
    mode: str | None


@dataclass(frozen=True)
class Case:
    id: str
    file: str
    group: str
    dicts: tuple[str, ...]
    user_dict: str | None
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Problem:
    file: str
    where: str
    code: str


def tokenize(keys: str) -> tuple[str, ...]:
    tokens = keys.split(" ")
    if any(token == "" for token in tokens):
        raise ValueError("keys-spacing")
    for token in tokens:
        if token in ("SPC", "RET", "BS"):
            continue
        if len(token) == 1 and "!" <= token <= "~":
            continue
        if len(token) == 3 and token.startswith("C-") and "a" <= token[2] <= "z":
            continue
        raise ValueError("keys-token")
    return tuple(tokens)


def _group_problem(group: object) -> bool:
    if not isinstance(group, dict):
        return True
    if any(key not in ("title", "ref") for key in group):
        return True
    title = group.get("title")
    ref = group.get("ref")
    return (
        not isinstance(title, str)
        or not title
        or not isinstance(ref, str)
        or not ref
    )


def _case_key_problem(item: dict) -> bool:
    if any(key not in _CASE_KEYS for key in item):
        return True
    if not isinstance(item.get("id"), str):
        return True
    dicts = item.get("dicts")
    if (
        not isinstance(dicts, list)
        or not dicts
        or not all(isinstance(name, str) for name in dicts)
    ):
        return True
    if "user_dict" in item and not isinstance(item["user_dict"], str):
        return True
    if "note" in item and not isinstance(item["note"], str):
        return True
    steps = item.get("step")
    if (
        not isinstance(steps, list)
        or not steps
        or not all(isinstance(step, dict) for step in steps)
    ):
        return True
    return False


def _step_key_problem(step: dict) -> bool:
    if any(key not in _STEP_KEYS for key in step):
        return True
    if not isinstance(step.get("keys"), str):
        return True
    return any(
        key in step and not isinstance(step[key], str)
        for key in ("text", "preedit", "mode")
    )


def _dictionary_problems(
    names: list[str], dict_dir: pathlib.Path, dict_root: pathlib.Path, file: str, label: str
) -> list[Problem]:
    name_problems: list[Problem] = []
    missing_problems: list[Problem] = []
    for name in names:
        if _DICT_NAME.fullmatch(name) is None:
            name_problems.append(Problem(file, label, "dict-name"))
            continue
        path = dict_dir / f"{name}.jisyo"
        try:
            parent = path.resolve().parent
        except (OSError, RuntimeError):
            parent = None
        if not path.is_file() or parent != dict_root:
            missing_problems.append(Problem(file, label, "dict-missing"))
    return name_problems + missing_problems


def load_cases(
    cases_dir: pathlib.Path, dict_dir: pathlib.Path
) -> tuple[list[Case], list[Problem]]:
    loaded: list[Case] = []
    problems: list[Problem] = []
    reserved: set[str] = set()
    dict_root = dict_dir.resolve()
    files = sorted(
        (
            path
            for path in cases_dir.iterdir()
            if path.is_file() and path.name.endswith(".toml")
        ),
        key=lambda path: path.name,
    )
    for path in files:
        file = path.name
        if _FILE_NAME.fullmatch(file) is None:
            problems.append(Problem(file, "-", "file-name"))
            continue
        try:
            with path.open("rb") as stream:
                if stream.read(len(_BOM)) == _BOM:
                    raise tomllib.TOMLDecodeError(msg="BOM", doc="", pos=0)
                stream.seek(0)
                document = tomllib.load(stream)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            problems.append(Problem(file, "-", "toml-syntax"))
            continue

        case_items = document.get("case")
        top_problem = (
            any(key not in ("group", "case") for key in document)
            or not isinstance(case_items, list)
            or not case_items
            or any(not isinstance(item, dict) for item in case_items)
        )
        group = document.get("group")
        group_problem = _group_problem(group)
        if top_problem:
            problems.append(Problem(file, "-", "top-key"))
        if group_problem:
            problems.append(Problem(file, "-", "group-key"))
        if top_problem or group_problem:
            continue

        group_title = group["title"]
        for index, item in enumerate(case_items, 1):
            label = item["id"] if isinstance(item.get("id"), str) else f"#{index}"
            case_problems: list[Problem] = []
            if _case_key_problem(item):
                case_problems.append(Problem(file, label, "case-key"))

            case_id = item.get("id")
            if isinstance(case_id, str):
                if _ID.fullmatch(case_id) is None:
                    case_problems.append(Problem(file, label, "id-pattern"))
                if case_id in reserved:
                    case_problems.append(Problem(file, label, "id-duplicate"))
                else:
                    reserved.add(case_id)

            names: list[str] = []
            dicts = item.get("dicts")
            if (
                isinstance(dicts, list)
                and dicts
                and all(isinstance(name, str) for name in dicts)
            ):
                names.extend(dicts)
            user_dict = item.get("user_dict")
            if isinstance(user_dict, str):
                names.append(user_dict)
            case_problems.extend(
                _dictionary_problems(names, dict_dir, dict_root, file, label)
            )

            step_values: list[Step] = []
            steps = item.get("step")
            if (
                isinstance(steps, list)
                and steps
                and all(isinstance(step, dict) for step in steps)
            ):
                for step_index, step in enumerate(steps, 1):
                    where = f"{label}#{step_index}"
                    step_problems: list[Problem] = []
                    if _step_key_problem(step):
                        step_problems.append(Problem(file, where, "step-key"))
                    if not any(
                        key in step for key in ("text", "preedit", "mode")
                    ):
                        step_problems.append(Problem(file, where, "step-empty"))

                    tokens: tuple[str, ...] = ()
                    keys = step.get("keys")
                    if isinstance(keys, str):
                        try:
                            tokens = tokenize(keys)
                        except ValueError as error:
                            code = str(error)
                            if code not in ("keys-spacing", "keys-token"):
                                raise
                            step_problems.append(Problem(file, where, code))

                    mode = step.get("mode")
                    if isinstance(mode, str) and mode not in MODES:
                        step_problems.append(Problem(file, where, "mode-value"))

                    case_problems.extend(step_problems)
                    if not step_problems:
                        step_values.append(
                            Step(
                                keys=tokens,
                                text=step.get("text"),
                                preedit=step.get("preedit"),
                                mode=step.get("mode"),
                            )
                        )

            if not case_problems:
                loaded.append(
                    Case(
                        id=case_id,
                        file=file,
                        group=group_title,
                        dicts=tuple(item["dicts"]),
                        user_dict=item.get("user_dict"),
                        steps=tuple(step_values),
                    )
                )
            problems.extend(case_problems)

    return loaded, problems


def validate_dict(path: pathlib.Path) -> list[Problem]:
    file = path.name
    data = path.read_bytes()
    if data.startswith(_BOM):
        return [Problem(file, "-", "dict-encoding")]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [Problem(file, "-", "dict-encoding")]
    if "\r" in text or not text.endswith("\n"):
        return [Problem(file, "-", "dict-line-end")]

    lines = text.split("\n")[:-1]
    problems: list[Problem] = []
    if lines[0] != _CODING:
        problems.append(Problem(file, "line 1", "dict-coding-line"))

    ari_lines = [
        number for number, line in enumerate(lines, 1) if line == _ARI
    ]
    nasi_lines = [
        number for number, line in enumerate(lines, 1) if line == _NASI
    ]
    if (
        len(ari_lines) != 1
        or len(nasi_lines) != 1
        or ari_lines[0] > nasi_lines[0]
    ):
        problems.append(Problem(file, "-", "dict-markers"))
        return problems

    ari_line = ari_lines[0]
    nasi_line = nasi_lines[0]
    previous: dict[str, str] = {}
    for number in range(2, len(lines) + 1):
        if number in (ari_line, nasi_line):
            continue
        line = lines[number - 1]
        if number < ari_line:
            if not line.startswith(";"):
                problems.append(Problem(file, f"line {number}", "dict-entry"))
            continue
        match = _ENTRY.fullmatch(line)
        if match is None:
            problems.append(Problem(file, f"line {number}", "dict-entry"))
            continue
        midashi = match.group(1)
        section = "ari" if number < nasi_line else "nasi"
        last = previous.get(section)
        if last is not None:
            if (section == "ari" and midashi >= last) or (
                section == "nasi" and midashi <= last
            ):
                problems.append(Problem(file, f"line {number}", "dict-sort"))
        previous[section] = midashi
    return problems
