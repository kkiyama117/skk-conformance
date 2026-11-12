import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
import unittest.mock

from runner import adapter, run

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FAKE = REPO_ROOT / "testdata" / "fake_adapter.py"
ARGV_PROBE = REPO_ROOT / "testdata" / "run" / "argv_probe.py"

BASIC_DICT = (
    ";; -*- mode: fundamental; coding: utf-8 -*-\n"
    ";; okuri-ari entries.\n"
    ";; okuri-nasi entries.\n"
)
MARKERS = ";; okuri-ari entries.\n;; okuri-nasi entries.\n"


def _toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values):
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _case_document(cases, group="Group"):
    lines = ["[group]", f"title = {_toml_string(group)}", 'ref = "ref"', ""]
    for case in cases:
        lines.append("[[case]]")
        lines.append(f"id = {_toml_string(case['id'])}")
        lines.append("dicts = " + _toml_array(case.get("dicts", ["basic"])))
        if "user_dict" in case:
            lines.append(f"user_dict = {_toml_string(case['user_dict'])}")
        for step in case["steps"]:
            lines.append("")
            lines.append("[[case.step]]")
            for key in ("keys", "text", "preedit", "mode"):
                if key in step:
                    lines.append(f"{key} = {_toml_string(step[key])}")
    return "\n".join(lines) + "\n"


def _engines_document(engines):
    lines = []
    for name, config in engines:
        lines.append(f"[engine.{name}]")
        for key in ("command", "build", "available"):
            if key in config:
                lines.append(f"{key} = " + _toml_array(config[key]))
        lines.append("")
    return "\n".join(lines)


def _obs(text="", preedit="", mode="hiragana"):
    return {"text": text, "preedit": preedit, "mode": mode}


def _script(engine="e1", version="1", cases=None, **extra):
    document = {"engine": engine, "version": version, "cases": cases or {}}
    document.update(extra)
    return document


class RunTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = pathlib.Path(self._temp.name)
        self.cases = self.root / "cases"
        self.dicts = self.root / "dict"
        self.logs = self.root / "logs"
        self.cases.mkdir()
        self.dicts.mkdir()
        (self.dicts / "basic.jisyo").write_text(BASIC_DICT, encoding="utf-8")

    def write_case(self, name, text):
        (self.cases / name).write_text(text, encoding="utf-8")

    def write_dict(self, name, text):
        (self.dicts / f"{name}.jisyo").write_text(text, encoding="utf-8")

    def write_script(self, path, script):
        path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    def write_engines(self, engines, directory=None):
        directory = self.root if directory is None else directory
        path = directory / "engines.toml"
        path.write_text(_engines_document(engines), encoding="utf-8")
        return path

    def fake_command(self, script_path):
        return [sys.executable, str(FAKE), str(script_path)]

    def call(self, argv):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = run.main(argv)
        return status, out.getvalue(), err.getvalue()

    def base_args(self, engines_path, timeout="1"):
        return [
            "--engines",
            str(engines_path),
            "--cases",
            str(self.cases),
            "--dicts",
            str(self.dicts),
            "--timeout",
            timeout,
            "--logs",
            str(self.logs),
        ]

    def one_file(self, cases, group="Group", name="01-group.toml"):
        self.write_case(name, _case_document(cases, group))

    def test_pass_and_fail_counts(self):
        self.one_file(
            [
                {"id": "t.one", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.two", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.bad", "steps": [{"keys": "a", "text": "ok"}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.one": {"steps": [_obs()]},
                    "t.two": {"steps": [_obs()]},
                    "t.bad": {"steps": [_obs(text="no")]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out,
            "| group | e1 1 |\n"
            "|---|---|\n"
            "| Group | 2/3 |\n"
            "| total | 2/3 |\n",
        )

    def test_fail_records_first_difference(self):
        self.one_file(
            [
                {
                    "id": "t.two-step",
                    "steps": [
                        {"keys": "a", "text": "", "mode": "hiragana"},
                        {"keys": "b", "text": "B"},
                    ],
                }
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.two-step": {
                        "steps": [_obs(mode="katakana"), _obs(text="X")]
                    }
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(
            json.loads(json_path.read_text(encoding="utf-8")),
            {
                "protocol": 1,
                "engines": {
                    "e1": {
                        "mark": "ran",
                        "version": "1",
                        "cases": {
                            "t.two-step": {
                                "status": "fail",
                                "step": 1,
                                "field": "mode",
                            }
                        },
                    }
                },
            },
        )

    def test_unchecked_fields_are_ignored(self):
        self.one_file(
            [{"id": "t.only-text", "steps": [{"keys": "a", "text": ""}]}]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.only-text": {
                        "steps": [_obs(preedit="OTHER", mode="ascii")]
                    }
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out, "| group | e1 1 |\n|---|---|\n| Group | 1/1 |\n| total | 1/1 |\n"
        )

    def test_error_answer(self):
        self.one_file(
            [
                {"id": "t.error", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.ok", "steps": [{"keys": "a", "text": ""}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.error": {"error": {"code": "unsupported-key"}},
                    "t.ok": {"steps": [_obs()]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {
                "t.error": {"status": "error", "code": "unsupported-key"},
                "t.ok": {"status": "pass"},
            },
        )

    def test_malformed_answer_restarts_adapter(self):
        self.one_file(
            [
                {"id": "t.bad", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.ok", "steps": [{"keys": "a", "text": ""}]},
            ]
        )
        script = self.root / "script.json"
        record = self.root / "record.jsonl"
        self.write_script(
            script,
            _script(
                record=str(record),
                cases={
                    "t.bad": {"raw": "not json\n"},
                    "t.ok": {"steps": [_obs()]},
                },
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {
                "t.bad": {"status": "error", "code": "broken"},
                "t.ok": {"status": "pass"},
            },
        )
        requests = [
            json.loads(line)
            for line in record.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(1 for request in requests if request.get("type") == "hello"), 2
        )

    def test_wrong_steps_length_is_malformed(self):
        self.one_file(
            [
                {
                    "id": "t.short",
                    "steps": [
                        {"keys": "a", "text": ""},
                        {"keys": "b", "text": ""},
                    ],
                }
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script, _script(cases={"t.short": {"steps": [_obs()]}})
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"]["t.short"],
            {"status": "error", "code": "malformed"},
        )

    def test_timeout_restarts_adapter(self):
        self.one_file(
            [
                {"id": "t.slow", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.ok", "steps": [{"keys": "a", "text": ""}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.slow": {"sleep": 3},
                    "t.ok": {"steps": [_obs()]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {
                "t.slow": {"status": "timeout"},
                "t.ok": {"status": "pass"},
            },
        )

    def test_crash_restarts_adapter(self):
        self.one_file(
            [
                {"id": "t.crash", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.ok", "steps": [{"keys": "a", "text": ""}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.crash": {"exit": 3},
                    "t.ok": {"steps": [_obs()]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {
                "t.crash": {"status": "error", "code": "broken"},
                "t.ok": {"status": "pass"},
            },
        )

    def test_unavailable_engine(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script = self.root / "script.json"
        record = self.root / "record.jsonl"
        self.write_script(
            script,
            _script(record=str(record), cases={"t.one": {"steps": [_obs()]}}),
        )
        engines = self.write_engines(
            [
                (
                    "e1",
                    {
                        "command": self.fake_command(script),
                        "available": ["false"],
                    },
                )
            ]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out, "| group | e1 |\n|---|---|\n| Group | n/a |\n| total | n/a |\n"
        )
        self.assertFalse(record.exists())

    def test_build_failed_engine(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script = self.root / "script.json"
        self.write_script(script, _script(cases={"t.one": {"steps": [_obs()]}}))
        engines = self.write_engines(
            [
                (
                    "e1",
                    {
                        "command": self.fake_command(script),
                        "build": ["false"],
                    },
                )
            ]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out,
            "| group | e1 |\n|---|---|\n| Group | build-failed |\n"
            "| total | build-failed |\n",
        )

    def test_hello_mismatch(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script = self.root / "script.json"
        record = self.root / "record.jsonl"
        self.write_script(
            script,
            _script(
                engine="other",
                record=str(record),
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(
            json.loads(json_path.read_text(encoding="utf-8")),
            {
                "protocol": 1,
                "engines": {
                    "e1": {"mark": "hello-failed", "cases": {}}
                },
            },
        )
        requests = [
            json.loads(line)
            for line in record.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [request.get("type") for request in requests], ["hello"]
        )

    def test_hello_mismatch_closes_adapter(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script = self.root / "script.json"
        record = self.root / "record.jsonl"
        exit_record = self.root / "exit.txt"
        self.write_script(
            script,
            _script(
                engine="other",
                record=str(record),
                exit_record=str(exit_record),
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(exit_record.read_text(encoding="utf-8"), "closed\n")
        requests = [
            json.loads(line)
            for line in record.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [request.get("type") for request in requests], ["hello"]
        )

    def test_hello_timeout_continues(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script_a = self.root / "a.json"
        script_b = self.root / "b.json"
        self.write_script(
            script_a,
            _script(
                engine="a",
                hello_behavior={"sleep": 3},
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        self.write_script(
            script_b,
            _script(
                engine="b",
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [
                ("a", {"command": self.fake_command(script_a)}),
                ("b", {"command": self.fake_command(script_b)}),
            ]
        )
        json_path = self.root / "out.json"
        original = adapter.Adapter.request

        def shortened(instance, obj, timeout):
            if obj.get("type") == "hello":
                return original(instance, obj, 1.0)
            return original(instance, obj, timeout)

        with unittest.mock.patch.object(
            adapter.Adapter, "request", shortened
        ):
            status, out, err = self.call(
                self.base_args(engines) + ["--json", str(json_path)]
            )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["a"], {"mark": "hello-failed", "cases": {}}
        )
        self.assertEqual(
            parsed["engines"]["b"]["cases"], {"t.one": {"status": "pass"}}
        )

    def test_hello_broken_continues(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script_a = self.root / "a.json"
        script_b = self.root / "b.json"
        self.write_script(
            script_a,
            _script(
                engine="a",
                hello_behavior={"exit": 3},
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        self.write_script(
            script_b,
            _script(engine="b", cases={"t.one": {"steps": [_obs()]}}),
        )
        engines = self.write_engines(
            [
                ("a", {"command": self.fake_command(script_a)}),
                ("b", {"command": self.fake_command(script_b)}),
            ]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["a"], {"mark": "hello-failed", "cases": {}}
        )
        self.assertEqual(
            parsed["engines"]["b"]["cases"], {"t.one": {"status": "pass"}}
        )

    def test_request_shape(self):
        self.write_dict("a", BASIC_DICT)
        self.write_dict("b", BASIC_DICT)
        self.one_file(
            [
                {
                    "id": "t.shape",
                    "dicts": ["a", "b"],
                    "steps": [{"keys": "K e y", "text": ""}],
                }
            ]
        )
        script = self.root / "script.json"
        record = self.root / "record.jsonl"
        self.write_script(
            script,
            _script(
                record=str(record),
                cases={"t.shape": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        lines = record.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        request = json.loads(lines[1])
        self.assertEqual(
            set(request), {"type", "id", "dicts", "user_dict", "steps"}
        )
        self.assertEqual(request["type"], "case")
        self.assertEqual(request["id"], "t.shape")
        self.assertEqual(
            request["dicts"],
            [
                {
                    "path": str((self.dicts / "a.jisyo").resolve()),
                    "encoding": "utf-8",
                },
                {
                    "path": str((self.dicts / "b.jisyo").resolve()),
                    "encoding": "utf-8",
                },
            ],
        )
        user_dict = request["user_dict"]
        self.assertEqual(set(user_dict), {"path", "encoding"})
        self.assertEqual(user_dict["encoding"], "utf-8")
        self.assertTrue(pathlib.Path(user_dict["path"]).is_absolute())
        self.assertEqual(pathlib.Path(user_dict["path"]).name, "user.jisyo")
        self.assertEqual(request["steps"], [{"keys": ["K", "e", "y"]}])

    def test_user_dict_starts_with_markers(self):
        self.one_file(
            [{"id": "t.markers", "steps": [{"keys": "a", "text": MARKERS}]}]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={"t.markers": {"user_dict_text": True}},
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {"t.markers": {"status": "pass"}},
        )

    def test_user_dict_copied_from_dict(self):
        content = (
            ";; -*- mode: fundamental; coding: utf-8 -*-\n"
            ";; okuri-ari entries.\n"
            ";; okuri-nasi entries.\n"
            "うごk /動/\n"
        )
        self.write_dict("u", content)
        self.one_file(
            [
                {
                    "id": "t.copied",
                    "user_dict": "u",
                    "steps": [{"keys": "a", "text": content}],
                }
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(cases={"t.copied": {"user_dict_text": True}}),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {"t.copied": {"status": "pass"}},
        )

    def test_user_dict_is_fresh_per_case(self):
        self.one_file(
            [
                {
                    "id": "t.first",
                    "steps": [{"keys": "a", "text": MARKERS + "first\n"}],
                },
                {
                    "id": "t.second",
                    "steps": [{"keys": "a", "text": MARKERS + "second\n"}],
                },
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.first": {"append_user_dict": "first"},
                    "t.second": {"append_user_dict": "second"},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed["engines"]["e1"]["cases"],
            {
                "t.first": {"status": "pass"},
                "t.second": {"status": "pass"},
            },
        )

    def test_table_format(self):
        self.write_case(
            "01-a.toml",
            _case_document(
                [
                    {"id": "t.a", "steps": [{"keys": "a", "text": ""}]},
                    {"id": "t.b", "steps": [{"keys": "a", "text": ""}]},
                ],
                group="A",
            ),
        )
        self.write_case(
            "02-b.toml",
            _case_document(
                [{"id": "t.c", "steps": [{"keys": "a", "text": ""}]}],
                group="B",
            ),
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                version="1.0",
                cases={
                    "t.a": {"steps": [_obs()]},
                    "t.b": {"steps": [_obs()]},
                    "t.c": {"steps": [_obs()]},
                },
            ),
        )
        engines = self.write_engines(
            [
                ("e1", {"command": self.fake_command(script)}),
                (
                    "e2",
                    {"command": ["false"], "available": ["false"]},
                ),
            ]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out,
            "| group | e1 1.0 | e2 |\n"
            "|---|---|---|\n"
            "| A | 2/2 | n/a |\n"
            "| B | 1/1 | n/a |\n"
            "| total | 3/3 | n/a |\n",
        )

    def test_details_lines(self):
        self.one_file(
            [
                {"id": "t.fail", "steps": [{"keys": "a", "text": "want"}]},
                {"id": "t.error", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.timeout", "steps": [{"keys": "a", "text": ""}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.fail": {"steps": [_obs(text="got")]},
                    "t.error": {"error": {"code": "unsupported-key"}},
                    "t.timeout": {"sleep": 3},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(
            self.base_args(engines) + ["--details"]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out,
            "| group | e1 1 |\n"
            "|---|---|\n"
            "| Group | 0/3 |\n"
            "| total | 0/3 |\n"
            "## e1\n"
            '- t.fail: fail step 1 text expected "want" got "got"\n'
            "- t.error: error unsupported-key\n"
            "- t.timeout: timeout\n",
        )

    def test_json_output(self):
        self.one_file(
            [
                {"id": "t.pass", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.fail", "steps": [{"keys": "a", "text": "want"}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.pass": {"steps": [_obs()]},
                    "t.fail": {"steps": [_obs(text="got")]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(
            json.loads(json_path.read_text(encoding="utf-8")),
            {
                "protocol": 1,
                "engines": {
                    "e1": {
                        "mark": "ran",
                        "version": "1",
                        "cases": {
                            "t.pass": {"status": "pass"},
                            "t.fail": {
                                "status": "fail",
                                "step": 1,
                                "field": "text",
                            },
                        },
                    }
                },
            },
        )

    def test_json_without_details_omits_case_text(self):
        tokens = ["K", "e", "y"]
        expected_text = "EXPECTED-TEXT-SENTINEL"
        actual_text = "ACTUAL-TEXT-SENTINEL"
        expected_preedit = "EXPECTED-PREEDIT-SENTINEL"
        actual_preedit = "ACTUAL-PREEDIT-SENTINEL"
        self.one_file(
            [
                {
                    "id": "t.privacy",
                    "steps": [
                        {
                            "keys": " ".join(tokens),
                            "text": expected_text,
                            "preedit": expected_preedit,
                            "mode": "hiragana",
                        }
                    ],
                }
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.privacy": {
                        "steps": [
                            _obs(
                                text=actual_text,
                                preedit=actual_preedit,
                                mode="hiragana",
                            )
                        ]
                    }
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines) + ["--json", str(json_path)]
        )
        self.assertEqual(status, 0, err)
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parsed,
            {
                "protocol": 1,
                "engines": {
                    "e1": {
                        "mark": "ran",
                        "version": "1",
                        "cases": {
                            "t.privacy": {
                                "status": "fail",
                                "step": 1,
                                "field": "text",
                            }
                        },
                    }
                },
            },
        )
        sentinels = (
            expected_text,
            actual_text,
            expected_preedit,
            actual_preedit,
        )
        self._assert_metadata_only(parsed, tokens, sentinels)

    def _assert_metadata_only(self, value, tokens, sentinels):
        if isinstance(value, dict):
            self.assertNotIn("keys", value)
            self.assertNotIn("expected", value)
            self.assertNotIn("actual", value)
            for item in value.values():
                self._assert_metadata_only(item, tokens, sentinels)
        elif isinstance(value, list):
            self.assertNotEqual(value, tokens)
            for item in value:
                self._assert_metadata_only(item, tokens, sentinels)
        elif isinstance(value, str):
            for sentinel in sentinels:
                self.assertNotIn(sentinel, value)

    def test_json_with_details_includes_values(self):
        self.one_file(
            [
                {"id": "t.pass", "steps": [{"keys": "a", "text": ""}]},
                {"id": "t.fail", "steps": [{"keys": "a", "text": "want"}]},
            ]
        )
        script = self.root / "script.json"
        self.write_script(
            script,
            _script(
                cases={
                    "t.pass": {"steps": [_obs()]},
                    "t.fail": {"steps": [_obs(text="got")]},
                }
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        json_path = self.root / "out.json"
        status, out, err = self.call(
            self.base_args(engines)
            + ["--json", str(json_path), "--details"]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(
            json.loads(json_path.read_text(encoding="utf-8")),
            {
                "protocol": 1,
                "engines": {
                    "e1": {
                        "mark": "ran",
                        "version": "1",
                        "cases": {
                            "t.pass": {"status": "pass"},
                            "t.fail": {
                                "status": "fail",
                                "step": 1,
                                "field": "text",
                                "expected": "want",
                                "actual": "got",
                            },
                        },
                    }
                },
            },
        )

    def test_case_problems_exit_2(self):
        self.write_case(
            "01-bad.toml",
            _case_document(
                [
                    {
                        "id": "t.bad",
                        "steps": [{"keys": "a", "text": "", "mode": "kana"}],
                    }
                ]
            ),
        )
        script = self.root / "script.json"
        self.write_script(script, _script())
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 2)
        self.assertEqual(out, "01-bad.toml: t.bad#1: mode-value\n")

    def test_engine_selection_order(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script_a = self.root / "a.json"
        script_b = self.root / "b.json"
        self.write_script(
            script_a,
            _script(
                engine="a",
                version="va",
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        self.write_script(
            script_b,
            _script(
                engine="b",
                version="vb",
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [
                ("a", {"command": self.fake_command(script_a)}),
                ("b", {"command": self.fake_command(script_b)}),
            ]
        )
        status, out, err = self.call(
            self.base_args(engines) + ["--engine", "b", "--engine", "a"]
        )
        self.assertEqual(status, 0, err)
        self.assertEqual(out.splitlines()[0], "| group | b vb | a va |")

        status, out, err = self.call(
            self.base_args(engines) + ["--engine", "c"]
        )
        self.assertEqual(status, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_adapter_closed_at_end(self):
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        script = self.root / "script.json"
        exit_record = self.root / "exit.txt"
        self.write_script(
            script,
            _script(
                exit_record=str(exit_record),
                cases={"t.one": {"steps": [_obs()]}},
            ),
        )
        engines = self.write_engines(
            [("e1", {"command": self.fake_command(script)})]
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(exit_record.read_text(encoding="utf-8"), "closed\n")

    def test_command_cwd(self):
        config = self.root / "config"
        config.mkdir()
        shutil.copyfile(FAKE, config / "fake_adapter.py")
        shutil.copyfile(ARGV_PROBE, config / "argv_probe.py")
        self.write_script(
            config / "script.json",
            _script(cases={"t.one": {"steps": [_obs()]}}),
        )
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        argv_record = self.root / "argv.txt"
        engines = self.write_engines(
            [
                (
                    "e1",
                    {
                        "command": [
                            "python3",
                            "argv_probe.py",
                            str(argv_record),
                            "fake_adapter.py",
                            "script.json",
                        ]
                    },
                )
            ],
            directory=config,
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out, "| group | e1 1 |\n|---|---|\n| Group | 1/1 |\n| total | 1/1 |\n"
        )
        self.assertEqual(
            argv_record.read_text(encoding="utf-8"),
            "fake_adapter.py\nscript.json",
        )

    def test_available_cwd(self):
        config = self.root / "config"
        config.mkdir()
        shutil.copyfile(FAKE, config / "fake_adapter.py")
        self.write_script(
            config / "script.json",
            _script(cases={"t.one": {"steps": [_obs()]}}),
        )
        (config / "cwd.marker").write_text("", encoding="utf-8")
        (config / "check_marker.py").write_text(
            "import pathlib\n"
            "import sys\n"
            "sys.exit(0 if pathlib.Path('cwd.marker').is_file() else 1)\n",
            encoding="utf-8",
        )
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        engines = self.write_engines(
            [
                (
                    "e1",
                    {
                        "command": ["python3", "fake_adapter.py", "script.json"],
                        "available": ["python3", "check_marker.py"],
                    },
                )
            ],
            directory=config,
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out, "| group | e1 1 |\n|---|---|\n| Group | 1/1 |\n| total | 1/1 |\n"
        )

    def test_build_cwd(self):
        config = self.root / "config"
        config.mkdir()
        shutil.copyfile(FAKE, config / "fake_adapter.py")
        self.write_script(
            config / "script.json",
            _script(cases={"t.one": {"steps": [_obs()]}}),
        )
        (config / "cwd.marker").write_text("", encoding="utf-8")
        (config / "build_marker.py").write_text(
            "import pathlib\n"
            "import sys\n"
            "sys.exit(0 if pathlib.Path('cwd.marker').is_file() else 1)\n",
            encoding="utf-8",
        )
        self.one_file([{"id": "t.one", "steps": [{"keys": "a", "text": ""}]}])
        engines = self.write_engines(
            [
                (
                    "e1",
                    {
                        "command": ["python3", "fake_adapter.py", "script.json"],
                        "build": ["python3", "build_marker.py"],
                    },
                )
            ],
            directory=config,
        )
        status, out, err = self.call(self.base_args(engines))
        self.assertEqual(status, 0, err)
        self.assertEqual(
            out, "| group | e1 1 |\n|---|---|\n| Group | 1/1 |\n| total | 1/1 |\n"
        )


if __name__ == "__main__":
    unittest.main()
