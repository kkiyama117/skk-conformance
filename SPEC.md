// CONTRACT: do not edit

# conformance: the behavior contract

This repository defines "the same SKK behavior" as data. A **case** is a key sequence plus the dictionaries it runs against, and the preedit, committed text, and input mode that the reference implementation (ddskk 17.2, ADR-0002) shows after each group of keys. A **runner** drives an engine through an **adapter** and prints a pass table. Every engine, ours included, is judged by the same cases.

The decision record is `../docs/adr/0003-conformance-case-format.md` (Japanese). This file is the contract. Workers do not edit it, `cases/`, or `dict/`.

## 1. Layout

| Path | Owner | Contents |
|---|---|---|
| `SPEC.md` | lead | This contract. |
| `TASKS.md` | lead | Cards `C1`, `C2`, ... |
| `cases/*.toml` | lead | The cases, one file per group (section 3). |
| `dict/*.jisyo` | lead | Synthetic SKK-JISYO dictionaries, UTF-8, LF (section 4). |
| `engines.toml` | lead | The engines the runner knows (section 6). |
| `runner/` | worker (cards) | The validator and the runner (section 7). |
| `adapters/<engine>/` | worker (cards) | One adapter per engine (section 5). |
| `testdata/` | worker (cards) | Fixtures for the runner's own tests. |
| `Makefile` | lead | `make check` is the gate (section 8). |

## 2. The model the cases assume

Every case starts from the same state: a fresh engine session with SKK turned on, input mode `hiragana`, no preedit, an empty text buffer, and the dictionaries the case names. Options are the ddskk defaults (`skk-egg-like-newline` nil, `skk-kakutei-early` t, `skk-kutouten-type` `jp`, `skk-henkan-show-candidates-keys` `(?a ?s ?d ?f ?j ?k ?l)`, `skk-show-candidates-nth-henkan-char` 5, `skk-henkan-number-to-display-candidates` 7, no sticky shift, no AZIK, no completion, no annotation display).

The adapter plays the application. It holds a one-line **text buffer** with the cursor always at its end. After each key:

- If the engine commits text, the adapter appends it to the buffer.
- If the engine does not consume the key, the adapter applies the key to the buffer itself: a printable character or `SPC` is appended (`SPC` as U+0020), `RET` appends `\n`, `BS` deletes the last character of the buffer if there is one, and every other key does nothing.

An engine that edits the application's text directly (ddskk edits the Emacs buffer) is observed the same way: `text` is the buffer contents outside the preedit.

A yes-or-no confirmation (ddskk asks one before `X` purges a word) is answered "yes" by the adapter. Cases never contain the answer keys.

## 3. Case files

A case file is TOML (v1.0), UTF-8, in `cases/`. Its name is `<NN>-<group>.toml`, where `NN` is two digits that order the groups in the pass table. The file has one top-level table and an array of cases:

```toml
[group]
title = "▼モード: 送り仮名が無い場合"
ref = "ddskk manual 5 変換モード > ▼モード"

[[case]]
id = "conv.first-candidate"
dicts = ["basic"]

[[case.step]]
keys = "K a n j i"
preedit = "▽かんじ"
text = ""

[[case.step]]
keys = "SPC"
preedit = "▼漢字"
mode = "hiragana"
```

### 3.1 `[group]`

| Key | Type | Required | Meaning |
|---|---|---|---|
| `title` | string | yes | Row label in the pass table. |
| `ref` | string | yes | Where in the ddskk manual (17.1 text in `docs/05_basic.rst` and `docs/06_apps.rst` of the ddskk source) the behavior is described. |

### 3.2 `[[case]]`

| Key | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique across all case files. Matches `^[a-z0-9]+(\.[a-z0-9-]+)+$`. |
| `dicts` | array of strings | yes, at least one | Names of system dictionaries, in search order. Name `x` means the file `dict/x.jisyo`. |
| `user_dict` | string | no | Name of a dictionary in `dict/` to copy as the initial user dictionary. Without it the user dictionary starts as the two marker lines only (section 4). |
| `note` | string | no | Free text for the reader. The runner ignores it. |
| `step` | array of tables | yes, at least one | Section 3.3. |

No other keys are allowed in a case.

### 3.3 `[[case.step]]`

A step is a group of keys followed by the observations expected after the last key of the group. A key in a step is fed only after the previous key has been fully handled.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `keys` | string | yes | Key notation, section 3.4. At least one key. |
| `text` | string | no | The whole text buffer after the step, as defined in section 2. Not only what this step added. |
| `preedit` | string | no | The preedit after the step, section 3.5. `""` means no preedit. |
| `mode` | string | no | The input mode after the step, section 3.6. |

A step needs at least one of `text`, `preedit`, `mode`. An observation that a step leaves out is not checked for that step. No other keys are allowed in a step.

### 3.4 Key notation

`keys` is a list of tokens separated by single spaces (U+0020), with no leading or trailing space. Each token is one of:

| Token | Key |
|---|---|
| one printable ASCII character from `!` (0x21) to `~` (0x7E) | That character, typed as is. An uppercase letter means Shift plus the letter. |
| `SPC` | Space bar. |
| `RET` | Enter. |
| `BS` | Backspace. |
| `C-` followed by one lowercase letter `a` to `z` | Control plus that letter, for example `C-j`, `C-g`, `C-q`. |

Nothing else is a token. In particular a literal space, `TAB`, `ESC`, and Meta keys are not tokens in version 1.

### 3.5 Preedit

The preedit is the text the engine shows as uncommitted, as one string, with the markers ddskk shows in the buffer:

- `▽` (U+25BD) starts a reading being typed (▽モード, and SKK abbrev mode).
- `▼` (U+25BC) starts a conversion (▼モード).
- `*` (U+002A) separates the reading from the okurigana prefix, as in `▽うご*k`, while the okurigana is not complete.
- Romaji typed but not yet converted to kana is part of the preedit, as in `▽かんj` or `s` alone in ■モード.

Cursor marks, highlighting, underlines, and candidate windows are not part of the preedit. During dictionary registration, engines show the registration in different places (ddskk in the minibuffer, libskk inside the preedit), so cases do not check `preedit` on a step that ends inside registration.

### 3.6 Input mode

| Value | ddskk name | ddskk state |
|---|---|---|
| `hiragana` | かなモード | `skk-j-mode` t, `skk-katakana` nil |
| `katakana` | カナモード | `skk-j-mode` t, `skk-katakana` t |
| `hankaku-katakana` | (none in the basic chapter) | `skk-jisx0201-mode` t |
| `zenkaku-latin` | 全英モード | `skk-jisx0208-latin-mode` t |
| `ascii` | アスキーモード | `skk-latin-mode` t |

While SKK abbrev mode is on (`/`), the input mode is the one that was active before `/`. Cases do not check `mode` on such a step.

## 4. Dictionaries

`dict/<name>.jisyo` files are synthetic SKK-JISYO dictionaries written for these cases. They are UTF-8 without BOM, LF line ends, and have this shape:

```
;; -*- mode: fundamental; coding: utf-8 -*-
;; okuri-ari entries.
うごk /動/
;; okuri-nasi entries.
かんじ /漢字/幹事/
```

- The first line is the coding line above, exactly.
- The okuri-ari section is sorted in descending order and the okuri-nasi section in ascending order, comparing midashi by Unicode code point, so that ddskk's binary search (`skk-large-jisyo`) works.
- Every line ends with `\n`, including the last.
- No annotations, no Lisp candidates, and no okurigana blocks in version 1.

The initial user dictionary of a case without `user_dict` is exactly these two lines:

```
;; okuri-ari entries.
;; okuri-nasi entries.
```

The runner writes the user dictionary file into a new temporary directory for each case, and removes the directory after the case.

## 5. Adapter protocol, version 1

An adapter is a program that drives one engine. The runner starts it once per engine run, writes requests to its stdin, and reads responses from its stdout. Each request and each response is one JSON object on one line, UTF-8, ended by `\n`. The adapter writes nothing else to stdout. It may write diagnostics to stderr, and the runner keeps stderr in its log only.

### 5.1 `hello`

The first request is:

```json
{"type": "hello", "protocol": 1}
```

The adapter answers:

```json
{"type": "hello", "protocol": 1, "engine": "libskk", "version": "1.1.1"}
```

`engine` is the engine's name in `engines.toml`. `version` is the engine version the adapter loaded, as the engine reports it, or `"unknown"`.

### 5.2 `case`

```json
{"type": "case", "id": "conv.first-candidate",
 "dicts": [{"path": "/abs/path/dict/basic.jisyo", "encoding": "utf-8"}],
 "user_dict": {"path": "/tmp/xyz/user.jisyo", "encoding": "utf-8"},
 "steps": [{"keys": ["K", "a", "n", "j", "i"]}, {"keys": ["SPC"]}]}
```

- `dicts` are in search order. Paths are absolute. `encoding` is always `"utf-8"` in version 1.
- `user_dict` is a file that already exists. The engine may read it, write it, or both.
- `keys` are the tokens of section 3.4, already split.

The adapter starts a new engine session for the case, so that no state, learning included, passes from one case to the next. It feeds every key of every step in order and answers once:

```json
{"type": "result", "id": "conv.first-candidate",
 "steps": [{"text": "", "preedit": "▽かんじ", "mode": "hiragana"},
           {"text": "", "preedit": "▼漢字", "mode": "hiragana"}]}
```

`steps` has one object per request step, each with all three of `text`, `preedit`, and `mode`, observed after the step's last key. `mode` is one of the values of section 3.6.

When the adapter cannot run the case, it answers instead:

```json
{"type": "result", "id": "conv.first-candidate", "error": {"code": "unsupported-key", "detail": "C-q"}}
```

| `code` | Meaning |
|---|---|
| `unsupported-key` | The engine or adapter cannot send this key. `detail` is the token. |
| `unsupported-mode` | The engine reports a mode outside section 3.6. `detail` is the engine's own name for it. |
| `engine-error` | The engine failed (crash, exception, error return). `detail` is a short message without dictionary or typed text. |

After an error answer the adapter must still accept the next request.

### 5.3 End

When stdin reaches end of file, the adapter ends its sessions and exits with status 0.

## 6. `engines.toml`

```toml
[engine.libskk]
build = ["make", "-C", "adapters/libskk"]
command = ["adapters/libskk/build/adapter"]
```

| Key | Required | Meaning |
|---|---|---|
| `command` | yes | argv of the adapter, relative to the repository root. |
| `build` | no | argv that builds the adapter, run once before the first use. |
| `available` | no | argv that exits 0 only when the engine can run on this machine (for example, a container image exists). Without it the engine is always available. |

## 7. The runner

The runner and validator are cards (`TASKS.md`). They follow these rules:

- A case **passes** when the adapter answered `steps` and, for every step, every observation the case gives equals the adapter's value exactly (string equality, no normalization).
- A case **fails** when an observation differs, **errors** on an `error` answer or a malformed answer, and **times out** when no answer comes within the per-case limit. After a timeout or a malformed answer the runner kills the adapter and starts it again for the next case.
- An engine whose `available` command exits nonzero is reported as not available, and none of its cases run.
- The pass table has one row per case file in `NN` order and one column per engine. A cell is `passed/total`. The last row is the total over all files.

## 8. The gate

`make check` validates every case file and dictionary against sections 3 and 4, and runs the runner's own tests. It does not need the network or a container. Engine runs that need a container or a long time are separate `make` targets, named in `TASKS.md`.

## 9. Versioning

A change to sections 2 to 6 that an existing adapter would misread bumps `protocol` and is recorded in the ADR. Adding cases or dictionaries is not a change to the contract.
