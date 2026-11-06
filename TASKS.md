# conformance cards

Read `../AGENTS.md` first, then `SPEC.md` in full, then your one card. `SPEC.md`, `cases/`, `dict/`, `engines.toml`, and `Makefile` are the lead's; never edit them.

Common rules for every card in this file:

- Python code uses the standard library only (Python 3.15 is installed; `tomllib` and `json` are in it). No third-party packages.
- Tests use `unittest`, live in `runner/test_<module>.py`, and are run by `make check` (`python3 -m unittest discover -s runner -t . -p 'test_*.py'`). Tests write only into `tempfile.TemporaryDirectory()`. Tests never start a real engine or container; they use the fake adapter in `testdata/`.
- `runner/` is a package: `runner/__init__.py` exists and is empty. Import modules as `from runner import cases`.
- Messages that a tool prints name files, case ids, step numbers, and problem codes only. They never print the text of a case's `keys`, `text`, or `preedit`, or a dictionary line, except where a rule below says so.

## C1. Case and dictionary validator

- Needs: none.
- Spec: `SPEC.md` sections 3 and 4; ADR `../docs/adr/0003-conformance-case-format.md`.
- Files: `runner/__init__.py`, `runner/cases.py`, `runner/validate.py`, `runner/test_cases.py`, `testdata/validate/` (any files under it).

### Data shape (`runner/cases.py`)

```python
@dataclass(frozen=True)
class Step:
    keys: tuple[str, ...]          # tokens, SPEC 3.4
    text: str | None               # None when the step leaves it out
    preedit: str | None
    mode: str | None

@dataclass(frozen=True)
class Case:
    id: str
    file: str                      # case file name, e.g. "04-conversion.toml"
    group: str                     # [group].title of its file
    dicts: tuple[str, ...]         # dictionary names, search order
    user_dict: str | None
    steps: tuple[Step, ...]

@dataclass(frozen=True)
class Problem:
    file: str                      # file name relative to the directory given (case or dict file)
    where: str                     # "-" for the whole file, a case id, or "<case id>#<step number from 1>"
    code: str                      # one of the codes in the table below

MODES = ("hiragana", "katakana", "hankaku-katakana", "zenkaku-latin", "ascii")

def tokenize(keys: str) -> tuple[str, ...]: ...
def validate_dict(path: pathlib.Path) -> list[Problem]: ...
def load_cases(cases_dir: pathlib.Path, dict_dir: pathlib.Path) -> tuple[list[Case], list[Problem]]: ...
```

- `tokenize` splits on single spaces and checks every token against SPEC 3.4. It raises `ValueError("keys-token")` for a token that is not in the table, and `ValueError("keys-spacing")` for an empty string, a leading or trailing space, or two spaces in a row. `keys-spacing` is checked first.
- `load_cases` reads every file in `cases_dir` whose name ends in `.toml`, in name order, and returns the cases of all files in file order, then case order within the file. A case with any problem is left out of the list; its problems are in the second value. A file with a problem in `[group]` or in its name contributes no cases. Problems are returned in file order, then in the order the checks below are listed, then in case and step order.
- `validate_dict` checks one dictionary file. `load_cases` does not call it; `validate.py` does.

### Problem codes

Case files:

| Code | `where` | When |
|---|---|---|
| `file-name` | `-` | The name does not match `^[0-9]{2}-[a-z0-9-]+\.toml$`. |
| `toml-syntax` | `-` | `tomllib` cannot parse the file. No other check runs on the file. |
| `top-key` | `-` | A top-level key other than `group` and `case`, or `case` is missing or is not an array of tables, or it is empty. |
| `group-key` | `-` | `group` is missing, has a key other than `title` and `ref`, misses one of them, or one of them is not a non-empty string. |
| `case-key` | case id, or `#<n>` (the case's position from 1 in its file) when `id` is missing or not a string | A key other than `id`, `dicts`, `user_dict`, `note`, `step`; or `id`, `dicts`, or `step` missing; or a value of the wrong type (`dicts` must be a non-empty array of strings, `user_dict` and `note` strings, `step` a non-empty array of tables). |
| `id-pattern` | case id | `id` does not match `^[a-z0-9]+(\.[a-z0-9-]+)+$`. |
| `id-duplicate` | case id | The id was already used by an earlier case in any file. The first use is not a problem. |
| `dict-missing` | case id | A name in `dicts` or the `user_dict` name has no file `<dict_dir>/<name>.jisyo`. |
| `step-key` | `<id>#<n>` | A step key other than `keys`, `text`, `preedit`, `mode`; or `keys` missing; or a value that is not a string. |
| `step-empty` | `<id>#<n>` | The step has none of `text`, `preedit`, `mode`. |
| `keys-spacing`, `keys-token` | `<id>#<n>` | `tokenize` raised it for the step's `keys`. |
| `mode-value` | `<id>#<n>` | `mode` is not in `MODES`. |

Dictionary files (`validate_dict`, `where` is `-` for the whole file or `line <n>` counting from 1):

| Code | When |
|---|---|
| `dict-encoding` | The bytes are not valid UTF-8, or start with a BOM. No other check runs. |
| `dict-line-end` | The file contains `\r`, or does not end with `\n`. `where` is `-`. |
| `dict-coding-line` | Line 1 is not exactly `;; -*- mode: fundamental; coding: utf-8 -*-`. |
| `dict-markers` | The lines `;; okuri-ari entries.` and `;; okuri-nasi entries.` do not each appear exactly once, in that order. No sort or entry check runs. |
| `dict-entry` | A line between the markers, or after the second one, is not `<midashi> /<cand>/<cand>/.../`: the midashi is non-empty and has no space or `/`, then one space, then `/`, then one or more non-empty candidates each followed by `/`, and no candidate contains `;`, `[`, or `]`. Lines 2 up to the first marker other than comments (starting with `;`) are also `dict-entry`. |
| `dict-sort` | An okuri-ari midashi is not strictly smaller (by code point) than the one before it, or an okuri-nasi midashi is not strictly larger than the one before it. `where` is the later line. |

### `runner/validate.py`

- Run as `python3 -m runner.validate [--cases DIR] [--dicts DIR]` from the repository root. Defaults: `cases` and `dict` next to the `runner` directory (resolved from `__file__`, not from the current directory).
- Calls `load_cases`, then `validate_dict` on every `*.jisyo` in the dict directory in name order.
- Prints each problem as `<file>: <where>: <code>`, one per line, case-file problems first, then dictionary problems, and exits 1 if there is any.
- Otherwise prints exactly `OK <c> cases in <f> files, <d> dictionaries` and exits 0.

### Tests (`runner/test_cases.py`)

Write the fixture files each test needs into a temporary directory, or under `testdata/validate/`. Every test that expects problems asserts the full list of `(file, where, code)` triples, in order.

| Test | Assert |
|---|---|
| `test_tokenize_simple` | `tokenize("K a n j i SPC")` is `("K","a","n","j","i","SPC")`. |
| `test_tokenize_named_and_control` | `tokenize("RET BS C-j C-g ; /")` returns the six tokens. |
| `test_tokenize_rejects_bad_token` | `"C-J"`, `"TAB"`, `"ab"`, `"C-"` and `"あ"` each raise `ValueError("keys-token")` (check `str(e)`). |
| `test_tokenize_rejects_spacing` | `""`, `" a"`, `"a "`, `"a  b"` each raise `ValueError("keys-spacing")`. |
| `test_load_valid_file` | A file with two cases, one with two steps, loads to two `Case` values with the exact fields, `None` for left-out observations, and no problems. |
| `test_load_orders_files_by_name` | `02-b.toml` and `01-a.toml` load with the cases of `01-a.toml` first. |
| `test_file_name_problem` | A file named `1-a.toml` gives `[("1-a.toml","-","file-name")]` and no cases. |
| `test_toml_syntax_problem` | An unparsable file gives only `toml-syntax`. |
| `test_group_key_problem` | Missing `ref` gives `group-key` and no cases from that file. |
| `test_case_key_problem` | A case with an extra key `foo` gives `case-key` with its id; a case without `id` (the second in its file) gives `case-key` at `#2`. |
| `test_id_pattern_problem` | Id `Bad.Id` gives `id-pattern`. |
| `test_id_duplicate_problem` | The same id in two files gives one `id-duplicate`, on the second file. The first case is loaded. |
| `test_dict_missing_problem` | `dicts = ["nope"]` gives `dict-missing`; so does `user_dict = "nope"`. |
| `test_step_problems` | One case with steps: an extra key (`step-key` at `id#1`), no observation (`step-empty` at `id#2`), `keys = "a  b"` (`keys-spacing` at `id#3`), `mode = "kana"` (`mode-value` at `id#4`), in that order. |
| `test_validate_dict_ok` | A copy of the SPEC 4 example gives no problems. |
| `test_validate_dict_encoding` | A file starting with a UTF-8 BOM gives only `dict-encoding`. |
| `test_validate_dict_line_end` | CRLF line ends give `dict-line-end` at `-`. |
| `test_validate_dict_sort` | Okuri-nasi `かんじ` after `きょ` gives `dict-sort` at the `かんじ` line; okuri-ari `うごk` before `もt` gives `dict-sort` at the `もt` line. |
| `test_validate_dict_entry` | `かんじ 漢字` and `かんじ /漢字;注/` each give `dict-entry` at their line. |
| `test_validate_cli_ok` | Running `python3 -m runner.validate --cases <tmp> --dicts <tmp>` on valid fixtures prints `OK 2 cases in 1 files, 1 dictionaries` and exits 0. |
| `test_validate_cli_problems` | On a fixture with one `mode-value` problem it prints `<file>: <id>#1: mode-value` and exits 1. |
| `test_repository_cases_are_valid` | `load_cases` on the repository's own `cases/` and `dict/` returns no problems and at least 80 cases, and `validate_dict` returns no problems for every `dict/*.jisyo`. |

Must fail without: `id-duplicate` check → `test_id_duplicate_problem`; the sort check → `test_validate_dict_sort`.

- Done: `make check` exits 0.

## C2. Runner and pass table

- Needs: C1.
- Spec: `SPEC.md` sections 2, 5, 6, 7; ADR `../docs/adr/0003-conformance-case-format.md`.
- Files: `runner/run.py`, `runner/adapter.py`, `runner/test_run.py`, `testdata/fake_adapter.py`, `testdata/run/` (any files under it).

Written after the C1 land. Not ready.
