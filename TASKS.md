# conformance cards

Read `../AGENTS.md` first, then `SPEC.md` in full, then your one card. `SPEC.md`, `cases/`, `dict/`, `engines.toml`, and `Makefile` are the lead's; never edit them. `engines.toml` does not exist yet; the lead adds it with the first adapter card. C1 does not read it.

Common rules for every card in this file:

- Python code uses the standard library only (Python 3.15 is installed; `tomllib` and `json` are in it). No third-party packages.
- Tests use `unittest`, live in `runner/test_<module>.py`, and are run by `make check` (`python3 -m unittest discover -s runner -t . -p 'test_*.py'`, with `PYTHONDONTWRITEBYTECODE=1` set by the `Makefile`). Tests write only into `tempfile.TemporaryDirectory()`. They may read fixture files that the card commits under `testdata/`, but never write there at test time. Tests never start a real engine or container; they use the fake adapter in `testdata/`.
- A card whose `Files` line names a path under `testdata/` may create `testdata/` itself if it is missing.
- C1 creates the `runner/` package and its empty `runner/__init__.py`; neither exists before C1. Later cards use that package. Import modules as `from runner import cases`.
- Messages that a tool prints name files, case ids, step numbers, and problem codes only. They never print the text of a case's `keys`, `text`, or `preedit`, or a dictionary line, except where a rule below says so.

## C1. Case and dictionary validator

Status: done

- Needs: none.
- Spec: `SPEC.md` sections 3 and 4; ADR `../docs/adr/0003-conformance-case-format.md`.
- Files: `runner/__init__.py`, `runner/cases.py`, `runner/validate.py`, `runner/test_cases.py`, `runner/test_validate.py`, `testdata/validate/` (any files under it).

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
    where: str                     # "-", a case label, "<case label>#<step number from 1>", or "line <n>"; see rules below
    code: str                      # one of the codes in the table below

MODES = ("hiragana", "katakana", "hankaku-katakana", "zenkaku-latin", "ascii")

def tokenize(keys: str) -> tuple[str, ...]: ...
def validate_dict(path: pathlib.Path) -> list[Problem]: ...
def load_cases(cases_dir: pathlib.Path, dict_dir: pathlib.Path) -> tuple[list[Case], list[Problem]]: ...
```

- `tokenize` splits on single spaces and checks every token against SPEC 3.4. It raises `ValueError("keys-token")` for a token that is not in the table, and `ValueError("keys-spacing")` for an empty string, a leading or trailing space, or two spaces in a row. `keys-spacing` is checked first.
- `load_cases` considers every regular file in `cases_dir` whose name ends in `.toml`, in name order. Both returned lists follow that file order, then case order within each file. A case with any problem contributes no `Case` value.
- Check `file-name` first. On that problem, do not open or parse the file and return only `file-name` for it. Otherwise load it with `tomllib.load` from a binary file. On `toml-syntax`, return only that problem for the file. Otherwise check both `top-key` and `group-key`, in that order. If either occurs, do not inspect cases or reserve their ids. Such a file contributes no cases.
- In a file that passes those checks, inspect every case. Its label is its `id` when that value is a string, even an invalid-pattern string; otherwise the label is `#<n>`, its 1-based case position in the file. All case-level problems use that label. All step problems use `<label>#<step position from 1>`, so a missing id in case 2, step 1 uses `#2#1`.
- Within each case, return case-level problems in table order, then step problems in step order and table order within each step. Emit each code at most once per file, case, or step at its stated level, except dictionary-name checks: `dict-name` and `dict-missing` each emit once per offending occurrence, including repeated names. For each code, visit `dicts` in array order, then `user_dict`. Multiple unknown keys still give one `case-key` or `step-key`.
- A `case-key` or `step-key` does not suppress independent checks. Check id pattern and duplicate only for a string id. Every string id reserves its first occurrence, even when its case has another problem or the id has an invalid pattern; later occurrences give `id-duplicate`. Inspect dictionary names from `dicts` only when it is a non-empty array of strings, and inspect `user_dict` only when it is a string. Inspect steps only when `step` is a non-empty array of tables. For each step, tokenize only string `keys`; check `mode-value` only for a string `mode`. `step-empty` checks presence of observation keys, not their types.
- `validate_dict` checks one dictionary file. `load_cases` does not call it or read dictionary bytes; `validate.py` does. Before any dictionary path check in `load_cases`, check the name against SPEC 3.2. For an invalid name, emit `dict-name` and do not construct or inspect its path. For a valid name, require `<dict_dir>/<name>.jisyo` to be a regular file whose resolved parent equals `dict_dir.resolve()`; otherwise emit `dict-missing`. Do not open a file outside that directory.

### Problem codes

Case files:

| Code | `where` | When |
|---|---|---|
| `file-name` | `-` | The name does not match `^[0-9]{2}-[a-z0-9-]+\.toml$`. Stop this file before opening it. |
| `toml-syntax` | `-` | `tomllib.load` raises `tomllib.TOMLDecodeError` or `UnicodeDecodeError`, including invalid UTF-8 or a UTF-8 BOM. Stop this file. |
| `top-key` | `-` | A top-level key other than `group` and `case`, or `case` is missing, is not a non-empty array, or contains a non-table item. |
| `group-key` | `-` | `group` is missing, is not a table, has a key other than `title` and `ref`, misses one of them, or one of them is not a non-empty string. Non-empty means length greater than zero without whitespace trimming, as in SPEC 3.1. |
| `case-key` | case label | A key other than `id`, `dicts`, `user_dict`, `note`, `step`; or `id`, `dicts`, or `step` missing; or a value of the wrong type (`id`, `user_dict`, and `note` must be strings, `dicts` a non-empty array of strings, `step` a non-empty array of tables). |
| `id-pattern` | case label | A string `id` does not match `^[a-z0-9]+(\.[a-z0-9-]+)+$`. |
| `id-duplicate` | case label | A string id has an earlier occurrence reserved by the rules above. The first occurrence is not a duplicate. |
| `dict-name` | case label | A dictionary name fails SPEC 3.2's pattern. Do not check a path for that occurrence. |
| `dict-missing` | case label | A valid dictionary name does not resolve to a regular file directly inside the resolved dictionary directory. |
| `step-key` | `<label>#<n>` | A step key other than `keys`, `text`, `preedit`, `mode`; or `keys` missing; or a value that is not a string. |
| `step-empty` | `<label>#<n>` | The step has none of `text`, `preedit`, `mode`. |
| `keys-spacing`, `keys-token` | `<label>#<n>` | `tokenize` raised it for string `keys`. These are alternatives, with spacing checked first. |
| `mode-value` | `<label>#<n>` | A string `mode` is not in `MODES`. |

Dictionary files (`validate_dict`). Lines count from 1. Check `dict-encoding`, `dict-line-end`, `dict-coding-line`, and `dict-markers` in that order, with the early stops stated in their rows. Return any of these problems before entry-level problems. If the markers are valid, inspect the remaining lines in ascending line-number order and interleave `dict-entry` and `dict-sort` problems in that same order. Do not group all `dict-entry` problems before `dict-sort`. A line with `dict-entry` is not checked for `dict-sort` and does not update the previous valid midashi. Every syntactically valid entry updates the previous midashi for its section, even if it has a `dict-sort` problem. Thus one line cannot emit both codes.

| Code | `where` | When |
|---|---|---|
| `dict-encoding` | `-` | The bytes are not valid UTF-8, or start with a BOM. No other check runs. |
| `dict-line-end` | `-` | The file contains `\r`, or does not end with `\n`. One problem at most. No other check runs. |
| `dict-coding-line` | `line 1` | Line 1 is not exactly `;; -*- mode: fundamental; coding: utf-8 -*-`. The other checks still run. |
| `dict-markers` | `-` | The lines `;; okuri-ari entries.` and `;; okuri-nasi entries.` do not each appear exactly once, in that order. No `dict-entry` or `dict-sort` check runs. |
| `dict-entry` | `line <n>` | From line 2 inclusive to the line before the okuri-ari marker inclusive, a line that does not start with `;`. This range is empty when the marker is on line 1 or line 2. A marker on line 1 still causes `dict-coding-line`, but does not itself cause `dict-entry`. The marker itself is excluded. After the okuri-ari marker, any line other than the okuri-nasi marker that is not `<midashi> /<cand>/<cand>/.../`: the midashi is non-empty and has no space or `/`, then one space, then `/`, then one or more non-empty candidates each followed by `/`, where no candidate contains `;`, `[`, or `]` or starts with `(`. A comment line after the okuri-ari marker is therefore a `dict-entry` problem. |
| `dict-sort` | `line <n>` of the later line | Among the lines without a `dict-entry` problem, an okuri-ari midashi that is not strictly smaller (by code point) than the previous okuri-ari midashi, or an okuri-nasi midashi that is not strictly larger than the previous okuri-nasi midashi. Lines with a `dict-entry` problem are skipped in this comparison. |

### `runner/validate.py`

- Run as `python3 -m runner.validate [--cases DIR] [--dicts DIR] [--min-cases N]` from the repository root. Defaults: `cases` and `dict` next to the `runner` directory (resolved from `__file__`, not from the current directory); `--min-cases` defaults to `0`. Parse N as an integer; a negative value or a value that is not an integer is an argparse usage error with exit 2.
- Calls `load_cases`, then `validate_dict` on every `*.jisyo` in the dict directory in name order.
- Prints each problem to stdout as `<file>: <where>: <code>`, one per line, case-file problems first, then dictionary problems, and exits 1 if there is any. Do not check the count floor in this branch.
- With no problems, if the number of loaded cases is less than N, print exactly `cases: -: case-count` plus a newline to stdout and exit 1. This CLI-only problem is not returned by `load_cases`. Do not also print an OK line.
- Otherwise prints exactly `OK <c> cases in <f> files, <d> dictionaries` plus a newline to stdout and exits 0. `<c>` is the number of cases loaded, `<f>` the number of `*.toml` files read, `<d>` the number of `*.jisyo` files checked.
- The lead-owned Makefile runs `python3 -m runner.validate --min-cases 81` in `make validate`, which `make check` includes. The floor equals the current v1 case count, so a decrease from 81 to 80 must fail. It is a minimum, not an exact-count check: adding cases remains allowed. Deliberately removing a case requires the lead to review the coverage and change this floor explicitly. Unittests do not read lead-owned cases. The worker implements the option but never edits Makefile. The gate writes no git state.

### Tests (`runner/test_cases.py` and `runner/test_validate.py`)

Put every test whose name starts with `test_validate_cli_` in `runner/test_validate.py`. Put every other test below in `runner/test_cases.py`.

At test time, write all fixtures into `tempfile.TemporaryDirectory()`. Static synthetic fixtures may be committed under `testdata/validate/` during implementation and read or copied into a temporary directory, but tests never write there. No unittest reads the repository's `cases/` or `dict/`: `make check` already validates those through its `validate` target.

The defaults in this paragraph apply only where a test row does not explicitly specify a different fixture property. This includes file names, encoding, file contents, case fields, step fields, and dictionary files. In particular, `test_file_name_problem` and `test_file_name_stops_before_parse` deliberately use the invalid file name `1-a.toml`. Otherwise every case fixture has a distinct valid id, `dicts = ["basic"]`, and at least one step with string `keys = "a"` and `text = ""`. Otherwise every file has a valid name and a group with non-empty `title` and `ref`. Create a valid `basic.jisyo` in the temporary dictionary directory, using the SPEC 4 example; likewise create any other dictionary that a row expects to exist. Leave out only the fields and files the row explicitly tests as missing. A step with an extra key still has an observation; only the step testing `step-empty` omits all observations. Thus each fixture has only the stated defects. Every test that expects problems asserts the full list of `(file, where, code)` triples, in order.

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
| `test_group_empty_title` | A group with `title = ""` and valid `ref` gives exactly one `group-key` at `-` and no cases from that file. |
| `test_group_empty_ref` | A group with `ref = ""` and valid `title` gives exactly one `group-key` at `-` and no cases from that file. |
| `test_group_whitespace_string` | A valid file whose group title and ref are each one U+0020 loads without problems. Whitespace is not trimmed. |
| `test_case_key_problem` | A case with an extra key `foo` gives `case-key` with its id; a case without `id` (the second in its file) gives `case-key` at `#2`. |
| `test_id_pattern_problem` | Id `Bad.Id` gives `id-pattern`. |
| `test_id_duplicate_problem` | The same id in two files gives one `id-duplicate`, on the second file. The first case is loaded. |
| `test_dict_missing_problem` | One case in one temporary `01-missing.toml`, with id `test.missing-system`, `dicts = ["nope"]`, and no `user_dict`. Do not create `nope.jisyo`. Exactly `[("01-missing.toml", "test.missing-system", "dict-missing")]` and no loaded cases. This test has only this fixture. |
| `test_user_dict_missing_problem` | A separate test with its own temporary directory and one case in `01-missing.toml`, with id `test.missing-user`, valid `dicts = ["basic"]`, and `user_dict = "nope"`. Create valid `basic.jisyo`, but no `nope.jisyo`. Exactly `[("01-missing.toml", "test.missing-user", "dict-missing")]` and no loaded cases. |
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
| `test_validate_dict_interleaves_entry_and_sort` | Write temporary `mixed.jisyo` with exactly these bytes encoded as UTF-8: `;; -*- mode: fundamental; coding: utf-8 -*-\n;; okuri-ari entries.\n;; okuri-nasi entries.\nきょ /距/\nかんじ /漢字/\nこめ 米\nかんじ /幹事/\n`. `validate_dict` returns exactly `[("mixed.jisyo", "line 5", "dict-sort"), ("mixed.jisyo", "line 6", "dict-entry"), ("mixed.jisyo", "line 7", "dict-sort")]`. This pins interleaving rather than grouping problems by code. |
| `test_validate_cli_ok` | Running `python3 -m runner.validate --cases <tmp> --dicts <tmp>` on valid fixtures prints `OK 2 cases in 1 files, 1 dictionaries` and exits 0. |
| `test_validate_cli_problems` | On a fixture with one `mode-value` problem it prints `<file>: <id>#1: mode-value` and exits 1. |
| `test_validate_cli_min_cases` | Loop over two valid cases in a temporary directory with N equal to 0, 2, 3, and 81. For 0 and 2, stdout is exactly `OK 2 cases in 1 files, 1 dictionaries\n` and exit is 0. For 3 and 81, stdout is exactly `cases: -: case-count\n` and exit is 1. |
| `test_validate_cli_floor_rejects_80` | Generate 80 valid synthetic cases with distinct ids in one temporary case file and run the CLI with `--min-cases 81`. Exactly `cases: -: case-count\n` on stdout and exit 1. |
| `test_validate_cli_floor_accepts_81` | Generate 81 valid synthetic cases with distinct ids in one temporary case file and run the CLI with `--min-cases 81`. Exactly `OK 81 cases in 1 files, 1 dictionaries\n` on stdout and exit 0. |
| `test_validate_cli_min_cases_with_problems` | One case with a `mode-value` problem and `--min-cases 81`: stdout is exactly `<file>: <id>#1: mode-value\n`, exit is 1, and there is no case-count or OK line. |
| `test_validate_cli_min_cases_usage` | Loop over `--min-cases -1` and `--min-cases nope` with valid temporary fixtures. Each exits 2, prints nothing to stdout, and writes an argparse usage error to stderr. Do not assert argparse's version-dependent wording. |
| `test_fixture_cases_are_valid` | Two valid synthetic case files with three cases in total and a valid dictionary, all in a temporary directory: `load_cases` returns those three cases and no problems; `validate_dict` returns no problems. Do not read repository cases or dictionaries. |
| `test_problem_file_order` | Create `02-b.toml` before `01-a.toml`, with one `mode-value` problem in each. The two triples are for `01-a.toml` then `02-b.toml`, each at its case label plus `#1`. |
| `test_problem_multiplicity` | One case has unknown keys `foo` and `bar`; its one step also has unknown keys `foo` and `bar`. Exactly one `case-key` at the case label, then one `step-key` at that label plus `#1`. |
| `test_missing_or_nonstring_id_labels` | Case 1 has no id; case 2 has integer id `7`. In each case, `dicts = ["nope"]` and step 1 has `keys = "a  b"` with an observation. Exactly `case-key`, `dict-missing`, `keys-spacing` per case, using labels `#1`, `#2` and step labels `#1#1`, `#2#1`. No id pattern or duplicate problems. |
| `test_invalid_case_reserves_id` | `01-a.toml` has id `test.same` and an extra case key; `02-b.toml` has the same id and no other defects. Exactly `case-key` in the first file, then `id-duplicate` in the second. No cases load. |
| `test_rejected_filename_does_not_reserve_id` | A valid TOML fixture named `01_bad.toml` contains id `test.same`; valid `02-good.toml` contains the same id. Exactly `[("01_bad.toml", "-", "file-name")]`; only the case from `02-good.toml` loads, with no duplicate problem. |
| `test_rejected_syntax_does_not_reserve_id` | `01-bad.toml` contains a complete valid case with id `test.same` followed by an invalid TOML line `=`, and valid `02-good.toml` contains the same id. Exactly `[("01-bad.toml", "-", "toml-syntax")]`; only the case from `02-good.toml` loads, with no duplicate problem. |
| `test_rejected_top_does_not_reserve_id` | Validly parsed `01-bad.toml` has an extra top-level `foo` key and case id `test.same`; valid `02-good.toml` has the same id. Exactly `[("01-bad.toml", "-", "top-key")]`; only the case from `02-good.toml` loads, with no duplicate problem. |
| `test_rejected_group_does_not_reserve_id` | `01-bad.toml` has a group missing `ref` and case id `test.same`; valid `02-good.toml` has the same id. Exactly `[("01-bad.toml", "-", "group-key")]`; only the case from `02-good.toml` loads, with no duplicate problem. |
| `test_file_name_stops_before_parse` | `1-a.toml` contains byte `0xff`. Exactly `[("1-a.toml", "-", "file-name")]`; no cases load. |
| `test_case_bom_is_syntax` | A valid case file prefixed with UTF-8 BOM gives exactly one `toml-syntax` at `-`; no cases load. |
| `test_dict_name_rejected` | Loop over names `"../outside"`, `"/outside"`, `"a/b"`, `"a\\b"`, `".."`, and `""`, testing each in `dicts` and then in `user_dict`. Each fixture gives exactly one `dict-name` at the case label, no `dict-missing`, and no loaded case. All fixtures stay inside a temporary directory. |
| `test_dict_resolved_path_stays_inside` | In a temporary directory, create `dict/basic.jisyo` as a symlink to a valid synthetic `outside.jisyo` in its parent. A case naming `basic` gives exactly one `dict-missing` at its label and no case. No private or real dictionary is used. |
| `test_repeated_missing_names` | `dicts = ["nope", "nope"]` and `user_dict = "nope"` give exactly three `dict-missing` triples at the case label. |
| `test_validate_dict_before_marker` | In the SPEC 4 example insert a non-comment line as line 2, shifting the okuri-ari marker to line 3. Exactly one `dict-entry` at `line 2`. With a comment at line 2 instead, no problems. The unchanged example with the marker on line 2 has no problems. |
| `test_validate_dict_marker_on_first_line` | Remove the coding line from the otherwise valid SPEC 4 example, so the okuri-ari marker is on line 1. Exactly `[(<name>, "line 1", "dict-coding-line")]`, with no `dict-entry` or other problem. |
| `test_validate_cli_problem_order` | Two case files with one `mode-value` each, then `a.jisyo` and `b.jisyo` with one wrong coding line each, plus valid `basic.jisyo`. The CLI prints exactly the two case triples in file-name order, then the two `dict-coding-line` triples in dictionary-name order, one per line with a final newline, and exits 1. |

Must fail without: `id-duplicate` check → `test_id_duplicate_problem`.

Must fail without: dictionary sort check → `test_validate_dict_sort`.

Must fail without: dictionary name validation → `test_dict_name_rejected`.

Must fail without: resolved dictionary directory check → `test_dict_resolved_path_stays_inside`.

Must fail without: minimum case count check → `test_validate_cli_min_cases`, `test_validate_cli_floor_rejects_80`.

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
| `test_user_dict_copied_from_dict` | A case with `user_dict = "u"`: the JSON string `text` equals the contents of the temporary fixture `dict/u.jisyo` decoded as UTF-8, without newline translation. Compare strings, not a string with bytes. |
| `test_user_dict_is_fresh_per_case` | Two cases with `append_user_dict`: the second case's `text` holds only its own line after the markers. |
| `test_table_format` | Two files, two engines (one `n/a`): stdout is exactly the expected table string, columns labelled `<name> <version>` and `<name>`. |
| `test_details_lines` | One fail, one error, one timeout: the details lines are exactly as specified. |
| `test_json_output` | The JSON file parses and equals the expected object for one pass and one fail. |
| `test_case_problems_exit_2` | A case file with a `mode-value` problem: exit status 2 and the problem line on stdout. |
| `test_engine_selection_order` | `--engine b --engine a`: the columns are `b` then `a`. Unknown `--engine c` exits 2. |
| `test_adapter_closed_at_end` | After the run, the fake process has exited with status 0 (record a marker line on exit in the fake, or check `close()` returns 0). |

Must fail without: the comparison of observations → `test_pass_and_fail_counts`; the restart after a timeout → `test_timeout_restarts_adapter`; the fresh user dictionary per case → `test_user_dict_is_fresh_per_case`.

- Done: `make check` exits 0.

## C9. Pull-request and main-branch CI

Status: done

- Needs: C1's committed implementation on `origin/card/C1`. Create the C9 implementation worktree from that branch, with `runner/` and its tests already present. C1 does not have to be merged into main first. C9's implementation PR targets `card/C1`, not main; its diff adds only the workflow file listed below. C1 files are inherited from the PR base, not added by C9. C2 and the engine adapters are not needed.
- Spec: `SPEC.md` section 8; `Makefile`; `../CLAUDE.md` sections GitHub and merge criteria; issue https://github.com/kkiyama117/kskk/issues/4.
- Files: `.github/workflows/check.yml` only. The worker may create the missing `.github/workflows/` directories. No Python code, dependency files, Makefile changes, or test fixtures belong to this card.
- The C9 number leaves C3-C8 available for the planned engine adapters. This card is a draft until its own ambiguity review and dispatch approval.

### Workflow contract

Write a YAML workflow named `Conformance check`. Its only events are `pull_request` without branch, path, or activity filters, and `push` restricted to the branch `main`. Do not use `pull_request_target`, a schedule, or `workflow_run`. Its only job has id `check`, name `make check`, `runs-on: ubuntu-24.04`, and `timeout-minutes: 10`. Do not add a matrix, a container, services, job conditions, or `continue-on-error`.

Set top-level permissions to exactly `contents: read`, with no job-level override. The job has these four steps, in this order:

1. `Checkout`. Use `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`, with an end-of-line comment `v7.0.1`. Set `persist-credentials: false` and `fetch-depth: 1`. Do not set `ref`. On a pull request, checkout must use the event's default merge result of the head into the base branch, not the head alone. On a push it must use the pushed commit. CI is reported on the PR head, but the tested tree is the merge result. Do not add a token, SSH key, submodules, or another repository.
2. `Set up Python`. Use `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`, with an end-of-line comment `v7.1.0`. Set `python-version: '3.15.2'`, `architecture: 'x64'`, and `allow-prereleases: false`. Do not add a package cache, mirror, or token. This action supplies the interpreter through its tool cache or Python distribution download; do not rely on the runner's system Python and do not fall back to another Python version.
3. `Python version`. Run exactly `python3 --version` so the native CI log identifies the interpreter.
4. `Run gate`. Run exactly `make check` from the repository root. Do not replace it with selected tests, suppress its exit code, or allow failure. The Makefile already sets `PYTHONDONTWRITEBYTECODE=1`.

The Python version and runner/action choices above come from the manager's CI evidence supplied to the lead. Ubuntu 24.04 has a listed x64 distribution of Python 3.15.2. The explicit runner label avoids changes in the meaning of ubuntu-latest. Keep both full action SHAs, not mutable version tags.

Do not add pip or apt installation, external engine runs, containers, real dictionaries, secrets, publication, uploads, or deployment. Network access used by the checkout and interpreter-setup actions is distinct from the offline `make check` gate. The gate itself needs no network or credentials.

### Verification

The worker runs the full `make check` locally and reports its exit code and last 20 lines. Do not start a worker or contact GitHub from a unittest. No new unittest is requested: this card connects the existing public gate to the native Actions events, and does not add Python logic. A unit test that compares a YAML file with a second copy of itself would not test that integration.

The following are separate acceptance checks by the lead or manager, not new Python test function names. Inspect the workflow artifact for the static checks. Native Actions checks require the manager's actual run and cannot be claimed from a local gate or a worker report.

| Acceptance check | Assert and evidence |
|---|---|
| `ci_events` | The workflow's event mapping is exactly unfiltered `pull_request` plus `push` with `branches: [main]`. |
| `ci_runner` | The check job uses `ubuntu-24.04`, x64 Python, and a 10-minute timeout. |
| `ci_action_pins` | Both uses values contain exactly the full SHAs specified above, with the stated version comments. |
| `ci_readonly_token` | Workflow permissions are exactly contents read and there is no job-level override. |
| `ci_no_persisted_credentials` | Checkout explicitly sets persist-credentials false and adds no credential input. |
| `ci_pr_merge` | Checkout has no ref override. C9's PR base is `card/C1`. Record the PR head SHA receiving the check and the tested SHA of that head merged into `card/C1`; the tested tree contains C1's runner and C9's workflow. |
| `ci_python_version` | The native Python version step prints `Python 3.15.2`. A YAML field alone does not prove the installed version. |
| `ci_pr_gate` | Before C9 merges into `card/C1`, its own pull_request workflow runs the full make check on the merge result into `card/C1` and succeeds. Record the run URL, PR head SHA, base branch, and tested merge SHA. This is not a main-based workflow-only tree without runner. |
| `ci_main_push_gate` | First C9 merges into `card/C1`. Later C1 PR #2, now containing the workflow, passes CI and merges into main. Only that main push supplies this check: the native push run executes the same full gate. Record its run URL and main commit before marking C9 done. A push to card/C1 is not this evidence and needs no added workflow trigger. |

Must fail without: the explicit read-only permissions declaration → `ci_readonly_token`.

Must fail without: disabling persisted checkout credentials → `ci_no_persisted_credentials`.

These two guard-removal checks are assertions on the workflow artifact, not unittest runs. The lead removes each declaration in turn, confirms that its acceptance assertion no longer holds, and restores the file exactly before any native CI run. Never run a deliberately weakened workflow on GitHub. Report these checks separately from test counts.

- Done for the stacked C9 PR: local `make check` exits 0 on the C1-based worktree, the artifact checks hold, and the native PR gate passes on C9's merge result into `card/C1`; security review and manager review precede that PR. The later main-push check after C1 PR #2 merges, and inclusion in origin/main, are required before Status: done. This order grants no CI bypass and no changes outside C9's Files line. Do not push, open a PR, merge, or mark done as a worker.
