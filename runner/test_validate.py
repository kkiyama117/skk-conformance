import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASIC = (
    ";; -*- mode: fundamental; coding: utf-8 -*-\n"
    ";; okuri-ari entries.\n"
    "うごk /動/\n"
    ";; okuri-nasi entries.\n"
    "かんじ /漢字/幹事/\n"
)
GROUP = '[group]\ntitle = "Group"\nref = "Ref"\n'
DEFAULT_STEP = '[[case.step]]\nkeys = "a"\ntext = ""\n'
BAD_MODE_STEP = '[[case.step]]\nkeys = "a"\ntext = ""\nmode = "kana"\n'
BAD_CODING = BASIC.replace(
    ";; -*- mode: fundamental; coding: utf-8 -*-", ";; coding: utf-8", 1
)


def case_block(case_id, step=DEFAULT_STEP):
    return f'[[case]]\nid = "{case_id}"\ndicts = ["basic"]\n{step}'


def many_cases(count):
    blocks = [
        f'[[case]]\nid = "test.case-{index}"\ndicts = ["basic"]\n{DEFAULT_STEP}'
        for index in range(count)
    ]
    return GROUP + "\n" + "".join(blocks)


class ValidateCliTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = pathlib.Path(self._temp.name)
        self.cases = self.root / "cases"
        self.dicts = self.root / "dict"
        self.cases.mkdir()
        self.dicts.mkdir()

    def write_case(self, name, text):
        (self.cases / name).write_text(text, encoding="utf-8")

    def write_dict(self, name, text):
        (self.dicts / name).write_text(text, encoding="utf-8")

    def add_basic(self):
        self.write_dict("basic.jisyo", BASIC)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "runner.validate", *map(str, args)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_validate_cli_ok(self):
        self.add_basic()
        self.write_case(
            "01-ok.toml",
            GROUP
            + "\n"
            + case_block("test.one")
            + "\n"
            + case_block("test.two"),
        )
        result = self.run_cli(
            "--cases", self.cases, "--dicts", self.dicts
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout, "OK 2 cases in 1 files, 1 dictionaries\n"
        )

    def test_validate_cli_problems(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            GROUP + "\n" + case_block("test.mode", BAD_MODE_STEP),
        )
        result = self.run_cli(
            "--cases", self.cases, "--dicts", self.dicts
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stdout, "01-bad.toml: test.mode#1: mode-value\n"
        )

    def test_validate_cli_min_cases(self):
        self.add_basic()
        self.write_case(
            "01-two.toml",
            GROUP
            + "\n"
            + case_block("test.one")
            + "\n"
            + case_block("test.two"),
        )
        for floor in (0, 2, 3, 81):
            with self.subTest(floor=floor):
                result = self.run_cli(
                    "--cases",
                    self.cases,
                    "--dicts",
                    self.dicts,
                    "--min-cases",
                    floor,
                )
                if floor in (0, 2):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        result.stdout,
                        "OK 2 cases in 1 files, 1 dictionaries\n",
                    )
                else:
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(
                        result.stdout, "cases: -: case-count\n"
                    )

    def test_validate_cli_floor_rejects_80(self):
        self.add_basic()
        self.write_case("01-many.toml", many_cases(80))
        result = self.run_cli(
            "--cases",
            self.cases,
            "--dicts",
            self.dicts,
            "--min-cases",
            81,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "cases: -: case-count\n")

    def test_validate_cli_floor_accepts_81(self):
        self.add_basic()
        self.write_case("01-many.toml", many_cases(81))
        result = self.run_cli(
            "--cases",
            self.cases,
            "--dicts",
            self.dicts,
            "--min-cases",
            81,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout, "OK 81 cases in 1 files, 1 dictionaries\n"
        )

    def test_validate_cli_min_cases_with_problems(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            GROUP + "\n" + case_block("test.mode", BAD_MODE_STEP),
        )
        result = self.run_cli(
            "--cases",
            self.cases,
            "--dicts",
            self.dicts,
            "--min-cases",
            81,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stdout, "01-bad.toml: test.mode#1: mode-value\n"
        )
        self.assertNotIn("case-count", result.stdout)
        self.assertNotIn("OK", result.stdout)

    def test_validate_cli_min_cases_usage(self):
        self.add_basic()
        self.write_case(
            "01-ok.toml", GROUP + "\n" + case_block("test.one")
        )
        for value in ("-1", "nope"):
            with self.subTest(value=value):
                result = self.run_cli(
                    "--cases",
                    self.cases,
                    "--dicts",
                    self.dicts,
                    "--min-cases",
                    value,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())

    def test_validate_cli_problem_order(self):
        self.add_basic()
        self.write_dict("a.jisyo", BAD_CODING)
        self.write_dict("b.jisyo", BAD_CODING)
        self.write_case(
            "02-b.toml",
            GROUP + "\n" + case_block("test.b", BAD_MODE_STEP),
        )
        self.write_case(
            "01-a.toml",
            GROUP + "\n" + case_block("test.a", BAD_MODE_STEP),
        )
        result = self.run_cli(
            "--cases", self.cases, "--dicts", self.dicts
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stdout,
            "01-a.toml: test.a#1: mode-value\n"
            "02-b.toml: test.b#1: mode-value\n"
            "a.jisyo: line 1: dict-coding-line\n"
            "b.jisyo: line 1: dict-coding-line\n",
        )


if __name__ == "__main__":
    unittest.main()
