# conformance cards

Read `../AGENTS.md` first, then `SPEC.md` in full, then your one card. `SPEC.md`, `cases/`, `dict/`, `engines.toml`, and `Makefile` are the lead's; never edit them. `engines.toml` does not exist yet; the lead adds it with the first adapter card. C1 does not read it.

Common rules for every card in this file:

- Python code uses the standard library only (Python 3.15 is installed; `tomllib` and `json` are in it). No third-party packages.
- Tests use `unittest`, live in `runner/test_<module>.py`, and are run by `make check` (`python3 -m unittest discover -s runner -t . -p 'test_*.py'`, with `PYTHONDONTWRITEBYTECODE=1` set by the `Makefile`). Tests write only into `tempfile.TemporaryDirectory()`. They may read fixture files that the card commits under `testdata/`, but never write there at test time. Tests never start a real engine or container; they use the fake adapter in `testdata/`.
- A card whose `Files` line names a path under `testdata/` may create `testdata/` itself if it is missing.
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
    file: str                      # base name of the case or dictionary file, e.g. "04-conversion.toml", "basic.jisyo"
    where: str                     # "-" for the whole file, a case id, "#<n>" (case position), "<case id>#<step number from 1>", or "line <n>" (dictionaries)
    code: str                      # one of the codes in the table below

MODES = ("hiragana", "katakana", "hankaku-katakana", "zenkaku-latin", "ascii")

def tokenize(keys: str) -> tuple[str, ...]: ...
def validate_dict(path: pathlib.Path) -> list[Problem]: ...
def load_cases(cases_dir: pathlib.Path, dict_dir: pathlib.Path) -> tuple[list[Case], list[Problem]]: ...
```

- `tokenize` splits on single spaces and checks every token against SPEC 3.4. It raises `ValueError("keys-token")` for a token that is not in the table, and `ValueError("keys-spacing")` for an empty string, a leading or trailing space, or two spaces in a row. `keys-spacing` is checked first.
- `load_cases` reads every file in `cases_dir` whose name ends in `.toml`, in name order, and returns the cases of all files in file order, then case order within the file. A case with any problem is left out of the list; its problems are in the second value. A file with a `file-name`, `toml-syntax`, `top-key`, or `group-key` problem contributes no cases. Within one file, the file-level problems come first (in the order of the table below), then the problems of each case in case order; within one case, the case-level problems in table order, then the problems of each step in step order, and within one step in table order.
- `validate_dict` checks one dictionary file. `load_cases` does not call it; `validate.py` does.

### Problem codes

Case files:

| Code | `where` | When |
|---|---|---|
| `file-name` | `-` | The name does not match `^[0-9]{2}-[a-z0-9-]+\.toml$`. |
| `toml-syntax` | `-` | `tomllib.load` raises `tomllib.TOMLDecodeError` or `UnicodeDecodeError` (a file that is not UTF-8). No other check runs on the file. |
| `top-key` | `-` | A top-level key other than `group` and `case`, or `case` is missing or is not an array of tables, or it is empty. |
| `group-key` | `-` | `group` is missing, has a key other than `title` and `ref`, misses one of them, or one of them is not a non-empty string. |
| `case-key` | case id, or `#<n>` (the case's position from 1 in its file) when `id` is missing or not a string | A key other than `id`, `dicts`, `user_dict`, `note`, `step`; or `id`, `dicts`, or `step` missing; or a value of the wrong type (`dicts` must be a non-empty array of strings, `user_dict` and `note` strings, `step` a non-empty array of tables). |
| `id-pattern` | case id | `id` does not match `^[a-z0-9]+(\.[a-z0-9-]+)+$`. |
| `id-duplicate` | case id | The id was already used by an earlier case in any file. The first use is not a problem. |
| `dict-missing` | case id | A name in `dicts` or the `user_dict` name has no file `<dict_dir>/<name>.jisyo`. One problem per missing name, `dicts` names first in their order, then `user_dict`. |
| `step-key` | `<id>#<n>` | A step key other than `keys`, `text`, `preedit`, `mode`; or `keys` missing; or a value that is not a string. |
| `step-empty` | `<id>#<n>` | The step has none of `text`, `preedit`, `mode`. |
| `keys-spacing`, `keys-token` | `<id>#<n>` | `tokenize` raised it for the step's `keys`. |
| `mode-value` | `<id>#<n>` | `mode` is not in `MODES`. |

Dictionary files (`validate_dict`). The checks run in the order of this table. Problems are returned in that order; `dict-entry` and `dict-sort` problems together in line order. Lines count from 1.

| Code | `where` | When |
|---|---|---|
| `dict-encoding` | `-` | The bytes are not valid UTF-8, or start with a BOM. No other check runs. |
| `dict-line-end` | `-` | The file contains `\r`, or does not end with `\n`. One problem at most. No other check runs. |
| `dict-coding-line` | `line 1` | Line 1 is not exactly `;; -*- mode: fundamental; coding: utf-8 -*-`. The other checks still run. |
| `dict-markers` | `-` | The lines `;; okuri-ari entries.` and `;; okuri-nasi entries.` do not each appear exactly once, in that order. No `dict-entry` or `dict-sort` check runs. |
| `dict-entry` | `line <n>` | Between line 2 and the okuri-ari marker, a line that does not start with `;`. After the okuri-ari marker, any line other than the okuri-nasi marker that is not `<midashi> /<cand>/<cand>/.../`: the midashi is non-empty and has no space or `/`, then one space, then `/`, then one or more non-empty candidates each followed by `/`, where no candidate contains `;`, `[`, or `]` or starts with `(`. A comment line after the okuri-ari marker is therefore a `dict-entry` problem. |
| `dict-sort` | `line <n>` of the later line | Among the lines without a `dict-entry` problem, an okuri-ari midashi that is not strictly smaller (by code point) than the previous okuri-ari midashi, or an okuri-nasi midashi that is not strictly larger than the previous okuri-nasi midashi. Lines with a `dict-entry` problem are skipped in this comparison. |

### `runner/validate.py`

- Run as `python3 -m runner.validate [--cases DIR] [--dicts DIR]` from the repository root. Defaults: `cases` and `dict` next to the `runner` directory (resolved from `__file__`, not from the current directory).
- Calls `load_cases`, then `validate_dict` on every `*.jisyo` in the dict directory in name order.
- Prints each problem to stdout as `<file>: <where>: <code>`, one per line, case-file problems first, then dictionary problems, and exits 1 if there is any.
- Otherwise prints exactly `OK <c> cases in <f> files, <d> dictionaries` to stdout and exits 0. `<c>` is the number of cases loaded, `<f>` the number of `*.toml` files read, `<d>` the number of `*.jisyo` files checked.

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
| `test_validate_dict_coding_line` | The SPEC 4 example with line 1 changed to `;; coding: utf-8` gives exactly `[(<name>, "line 1", "dict-coding-line")]`. |
| `test_validate_dict_markers` | The SPEC 4 example without the okuri-nasi marker gives exactly `[(<name>, "-", "dict-markers")]`. |
| `test_dict_missing_order` | `dicts = ["x", "basic", "y"]` and `user_dict = "z"` with only `basic.jisyo` present give `dict-missing` three times for that case id. |
| `test_top_key_problem` | A file with an extra top-level key `foo` gives `top-key` and no cases. |
| `test_non_utf8_case_file` | A case file holding the byte `0xff` gives exactly `toml-syntax`. |
| `test_validate_dict_encoding` | A file starting with a UTF-8 BOM gives exactly `[(<name>, "-", "dict-encoding")]`. |
| `test_validate_dict_line_end` | The SPEC 4 example with CRLF line ends gives exactly `[(<name>, "-", "dict-line-end")]`; the example without its final `\n` gives the same. |
| `test_validate_dict_sort` | Two files. One has okuri-nasi `きょ` then `かんじ`: exactly one `dict-sort` at the `かんじ` line. The other has okuri-ari `うごk` then `もt`: exactly one `dict-sort` at the `もt` line. |
| `test_validate_dict_entry` | One file whose okuri-nasi section is `かんじ 漢字`, `かんじ /漢字;注/`, `こめ /(concat "a")/`, `;; comment`, `さ /差/`: exactly four `dict-entry` problems, at those four lines in order, and no `dict-sort`. |
| `test_validate_cli_ok` | Running `python3 -m runner.validate --cases <tmp> --dicts <tmp>` on valid fixtures prints `OK 2 cases in 1 files, 1 dictionaries` and exits 0. |
| `test_validate_cli_problems` | On a fixture with one `mode-value` problem it prints `<file>: <id>#1: mode-value` and exits 1. |
| `test_repository_cases_are_valid` | `load_cases` on the repository's own `cases/` and `dict/` returns no problems and at least 80 cases, and `validate_dict` returns no problems for every `dict/*.jisyo`. |

Must fail without: `id-duplicate` check → `test_id_duplicate_problem`; the sort check → `test_validate_dict_sort`.

- Done: `make check` exits 0.

## C2. Runner and pass table

- Needs: C1.
- Spec: `SPEC.md` sections 2, 5, 6, 7; ADR `../docs/adr/0003-conformance-case-format.md`.
- Files: `runner/run.py`, `runner/adapter.py`, `runner/test_run.py`, `testdata/fake_adapter.py`, `testdata/run/` (any files under it).

### `runner/adapter.py`

```python
class AdapterTimeout(Exception): ...
class AdapterBroken(Exception): ...   # exited, closed stdout, or wrote a line that is not one JSON object

class Adapter:
    def __init__(self, argv: list[str], cwd: pathlib.Path, stderr_path: pathlib.Path): ...
    def start(self) -> dict: ...                       # starts the process, sends hello, returns the hello answer
    def request(self, obj: dict, timeout: float) -> dict: ...
    def close(self) -> int: ...                        # closes stdin, waits up to 5 s, kills if needed, returns the exit status
    def kill(self) -> None: ...
```

- The process runs with `cwd`, stdin and stdout as pipes in UTF-8, and stderr appended to `stderr_path`.
- `request` writes `json.dumps(obj, ensure_ascii=False)` plus `\n`, flushes, and waits for one line on stdout. No full line within `timeout` seconds raises `AdapterTimeout`. End of stdout, or a line that `json.loads` rejects or that is not an object, raises `AdapterBroken`. Use a reader thread and a `queue.Queue`, or `selectors`; either is fine.
- `start` sends `{"type": "hello", "protocol": 1}` with a 30 s timeout and returns the answer as is.

### `runner/run.py`

Run as `python3 -m runner.run [--engines FILE] [--engine NAME]... [--cases DIR] [--dicts DIR] [--timeout SEC] [--json PATH] [--details] [--logs DIR]` from the repository root.

| Option | Default |
|---|---|
| `--engines` | `engines.toml` next to `runner/` |
| `--engine` | every engine in the file, in file order. Given once or more, only those, in the order given. An unknown name is a usage error. |
| `--cases`, `--dicts` | as in `runner.validate` |
| `--timeout` | `20` seconds per case |
| `--json` | none |
| `--logs` | `build/logs` next to `runner/` (created if missing) |

Steps:

1. `load_cases`. If there are problems, print them as `runner.validate` does and exit 2.
2. Read the engines file with `tomllib`. Each `[engine.<name>]` table may have only `command` (required, non-empty array of strings), `build`, and `available` (arrays of strings). Anything else, or a file that does not parse, prints `engines: <name or -> : engines-key` and exits 2.
3. For each selected engine, in order:
   1. If `available` is given, run it with `cwd` = the engines file's directory, stdout and stderr discarded. A nonzero exit marks the engine `n/a`; skip to the next engine.
   2. If `build` is given, run it the same way, with its output appended to `<logs>/<name>.build.log`. A nonzero exit marks the engine `build-failed`; skip to the next engine.
   3. Start an `Adapter` with `command`, `cwd` = the engines file's directory, and `stderr_path` = `<logs>/<name>.stderr.log`. The hello answer must have `type` `"hello"`, `protocol` `1`, and `engine` equal to `<name>`; otherwise mark the engine `hello-failed` and skip it. Keep `version` (a string; `"unknown"` if missing).
   4. For each case, in `load_cases` order: make a new `tempfile.TemporaryDirectory()`; write `user.jisyo` in it, either the two marker lines of SPEC section 4 (`";; okuri-ari entries.\n;; okuri-nasi entries.\n"`) or a byte copy of `dict/<user_dict>.jisyo`; send the request of SPEC 5.2 with `dicts` as absolute paths of `dict/<name>.jisyo` and `"encoding": "utf-8"`; classify the answer (below); remove the directory.
   5. After the last case, `close()` the adapter.
4. Print the table (below) to stdout. With `--details`, print the details after it. With `--json`, write the JSON file.
5. Exit 0, even when cases fail or engines are `n/a`.

Classifying one answer:

| Status | When |
|---|---|
| `pass` | `type` is `"result"`, `id` equals the case id, `steps` is a list as long as the case's steps, each item has string `text`, `preedit`, and `mode`, and every observation the case gives equals the item's value. |
| `fail` | The answer is well formed as above but an observation differs. Record the first differing step (from 1) and field, checking steps in order and, within a step, `text`, then `preedit`, then `mode`. |
| `error` | The answer has `error` (record its `code`), or is malformed (wrong `type`, wrong `id`, wrong `steps` length, missing or non-string field; record code `malformed`), or the adapter raised `AdapterBroken` (record code `broken`). |
| `timeout` | The adapter raised `AdapterTimeout`. |

After `malformed`, `broken`, or `timeout`, kill the adapter and start it again (with hello) before the next case. If the restart fails, every remaining case of that engine is `error` with code `broken`.

The table, exactly (one row per case file in load order, labelled with its `[group].title`; one column per selected engine, labelled `<name> <version>`, or `<name>` when the engine did not reach hello):

```
| group | libskk 1.1.1 | ddskk 17.2 |
|---|---|---|
| 入力モード | 12/12 | n/a |
| total | 81/81 | n/a |
```

A cell is `<passed>/<total>` for that file, or the engine's mark (`n/a`, `build-failed`, `hello-failed`) in every row. `total` sums all files.

Details (`--details`): for each engine that ran, a line `## <name>`, then one line per case that did not pass, in case order: `- <id>: fail step <n> <field> expected <json> got <json>` (the two values as `json.dumps(..., ensure_ascii=False)`; this is the one place the runner prints case text), `- <id>: error <code>`, or `- <id>: timeout`.

JSON (`--json`):

```json
{"protocol": 1,
 "engines": {"libskk": {"mark": "ran", "version": "1.1.1",
                        "cases": {"conv.first-candidate": {"status": "pass"},
                                  "conv.next-candidate": {"status": "fail", "step": 1, "field": "preedit", "expected": "▼幹事", "actual": "▼漢字"},
                                  "abbrev.cq-to-zenkaku": {"status": "error", "code": "unsupported-key"}}}}}
```

`mark` is `ran`, `n/a`, `build-failed`, or `hello-failed`; an engine that did not run has no `version` and an empty `cases`. Engines appear in run order, cases in case order. Write with `ensure_ascii=False`, `indent=1`.

### `testdata/fake_adapter.py`

A Python script, `python3 testdata/fake_adapter.py <script.json>`. The script file is an object with:

- `"engine"`, `"version"`: the hello answer's values. `"protocol"` (optional, default 1).
- `"record"` (optional): a path; the fake appends every request line it reads to it, as read.
- `"cases"`: an object from case id to one behavior:
  - `{"steps": [...]}`: answer `type` result with these steps.
  - `{"error": {...}}`: answer with this error.
  - `{"raw": "<line>"}`: write this line as is.
  - `{"sleep": <seconds>}`: sleep, then answer with an empty `steps` list.
  - `{"exit": <status>}`: exit at once with this status.
  - `{"user_dict_text": true}`: answer one step whose `text` is the whole user dictionary file read as UTF-8, `preedit` `""`, `mode` `"hiragana"`.
  - `{"append_user_dict": "<line>"}`: append the line plus `\n` to the user dictionary, then answer one step as `user_dict_text` does.
- A case id not in `"cases"` answers `error` `engine-error`.
- On end of stdin, exit 0.

### Tests (`runner/test_run.py`)

Each test writes its own case files, dictionaries, engines file, and fake script into a temporary directory and calls `run.main([...])` (define `main(argv: list[str]) -> int` in `runner/run.py`; it prints to `sys.stdout`) or runs `python3 -m runner.run`. Use `--timeout 1` unless the test says otherwise.

| Test | Assert |
|---|---|
| `test_pass_and_fail_counts` | Three cases, the fake answers two correctly and one wrong: the table's row is `2/3` and `total` is `2/3`. |
| `test_fail_records_first_difference` | A two-step case whose step 1 `mode` and step 2 `text` differ: JSON has `step` 1, `field` `mode`. |
| `test_unchecked_fields_are_ignored` | A step that gives only `text`; the fake returns a different `preedit`: the case passes. |
| `test_error_answer` | The fake answers `unsupported-key`: status `error`, code `unsupported-key`; the next case still runs. |
| `test_malformed_answer_restarts_adapter` | `raw` `not json` for case 1; case 2 passes; `record` shows two hello lines. |
| `test_wrong_steps_length_is_malformed` | The fake answers one step for a two-step case: `error` `malformed`. |
| `test_timeout_restarts_adapter` | `sleep` 3 with `--timeout 1`: status `timeout`; the next case passes. |
| `test_crash_restarts_adapter` | `exit` 3 for case 1: `error` `broken`; case 2 passes. |
| `test_unavailable_engine` | `available = ["false"]`: every row is `n/a`, the fake's `record` file is never created. |
| `test_build_failed_engine` | `build = ["false"]`: every row is `build-failed`. |
| `test_hello_mismatch` | The fake's `engine` differs from the table name: `hello-failed`, no case requests recorded. |
| `test_request_shape` | `record` holds, after hello, exactly the SPEC 5.2 request for a case with `dicts = ["a", "b"]`: absolute paths in that order, `encoding` `utf-8`, `user_dict.path` ending in `user.jisyo`, and `keys` split into tokens. |
| `test_user_dict_starts_with_markers` | `user_dict_text`: the step's `text` is `";; okuri-ari entries.\n;; okuri-nasi entries.\n"` and the case expecting that passes. |
| `test_user_dict_copied_from_dict` | A case with `user_dict = "u"`: the `text` equals the bytes of `dict/u.jisyo`. |
| `test_user_dict_is_fresh_per_case` | Two cases with `append_user_dict`: the second case's `text` holds only its own line after the markers. |
| `test_table_format` | Two files, two engines (one `n/a`): stdout is exactly the expected table string, columns labelled `<name> <version>` and `<name>`. |
| `test_details_lines` | One fail, one error, one timeout: the details lines are exactly as specified. |
| `test_json_output` | The JSON file parses and equals the expected object for one pass and one fail. |
| `test_case_problems_exit_2` | A case file with a `mode-value` problem: exit status 2 and the problem line on stdout. |
| `test_engine_selection_order` | `--engine b --engine a`: the columns are `b` then `a`. Unknown `--engine c` exits 2. |
| `test_adapter_closed_at_end` | After the run, the fake process has exited with status 0 (record a marker line on exit in the fake, or check `close()` returns 0). |

Must fail without: the comparison of observations → `test_pass_and_fail_counts`; the restart after a timeout → `test_timeout_restarts_adapter`; the fresh user dictionary per case → `test_user_dict_is_fresh_per_case`.

- Done: `make check` exits 0.
