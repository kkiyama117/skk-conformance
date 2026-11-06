import json
import pathlib
import tempfile
import unittest

from runner import cases


BASIC = (
    ";; -*- mode: fundamental; coding: utf-8 -*-\n"
    ";; okuri-ari entries.\n"
    "うごk /動/\n"
    ";; okuri-nasi entries.\n"
    "かんじ /漢字/幹事/\n"
)
GROUP = '[group]\ntitle = "Group"\nref = "Ref"\n'
DEFAULT_STEP = '[[case.step]]\nkeys = "a"\ntext = ""\n'


def triples(problems):
    return [(problem.file, problem.where, problem.code) for problem in problems]


def case_block(
    *,
    id_line='id = "test.one"',
    dicts='["basic"]',
    extra="",
    steps=DEFAULT_STEP,
):
    body = f"[[case]]\n{id_line}\ndicts = {dicts}\n{extra}{steps}"
    return body if body.endswith("\n") else body + "\n"


class CaseTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = pathlib.Path(self._temp.name)
        self.cases_dir = self.root / "cases"
        self.dict_dir = self.root / "dict"
        self.cases_dir.mkdir()
        self.dict_dir.mkdir()

    def write_case(self, name, text):
        (self.cases_dir / name).write_text(text, encoding="utf-8")

    def write_case_bytes(self, name, data):
        (self.cases_dir / name).write_bytes(data)

    def write_dict(self, name, text):
        (self.dict_dir / name).write_text(text, encoding="utf-8")

    def write_dict_bytes(self, name, data):
        (self.dict_dir / name).write_bytes(data)

    def add_basic(self):
        self.write_dict("basic.jisyo", BASIC)

    def load(self):
        return cases.load_cases(self.cases_dir, self.dict_dir)

    def test_tokenize_simple(self):
        self.assertEqual(
            cases.tokenize("K a n j i SPC"),
            ("K", "a", "n", "j", "i", "SPC"),
        )

    def test_tokenize_named_and_control(self):
        self.assertEqual(
            cases.tokenize("RET BS C-j C-g ; /"),
            ("RET", "BS", "C-j", "C-g", ";", "/"),
        )

    def test_tokenize_rejects_bad_token(self):
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("C-J")
        self.assertEqual(str(caught.exception), "keys-token")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("TAB")
        self.assertEqual(str(caught.exception), "keys-token")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("ab")
        self.assertEqual(str(caught.exception), "keys-token")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("C-")
        self.assertEqual(str(caught.exception), "keys-token")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("あ")
        self.assertEqual(str(caught.exception), "keys-token")

    def test_tokenize_rejects_spacing(self):
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("")
        self.assertEqual(str(caught.exception), "keys-spacing")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize(" a")
        self.assertEqual(str(caught.exception), "keys-spacing")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("a ")
        self.assertEqual(str(caught.exception), "keys-spacing")
        with self.assertRaises(ValueError) as caught:
            cases.tokenize("a  b")
        self.assertEqual(str(caught.exception), "keys-spacing")

    def test_load_valid_file(self):
        self.add_basic()
        self.write_case(
            "01-valid.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.first"\ndicts = ["basic"]\nnote = "free"\n'
            + '[[case.step]]\nkeys = "a b"\ntext = "あ"\npreedit = ""\n'
            + 'mode = "hiragana"\n'
            + '[[case.step]]\nkeys = "SPC"\ntext = ""\n'
            + '[[case]]\nid = "test.second"\ndicts = ["basic"]\n'
            + '[[case.step]]\nkeys = "RET"\npreedit = ""\n',
        )
        loaded, problems = self.load()
        expected = [
            cases.Case(
                id="test.first",
                file="01-valid.toml",
                group="Group",
                dicts=("basic",),
                user_dict=None,
                steps=(
                    cases.Step(
                        keys=("a", "b"),
                        text="あ",
                        preedit="",
                        mode="hiragana",
                    ),
                    cases.Step(
                        keys=("SPC",), text="", preedit=None, mode=None
                    ),
                ),
            ),
            cases.Case(
                id="test.second",
                file="01-valid.toml",
                group="Group",
                dicts=("basic",),
                user_dict=None,
                steps=(
                    cases.Step(
                        keys=("RET",), text=None, preedit="", mode=None
                    ),
                ),
            ),
        ]
        self.assertEqual(loaded, expected)
        self.assertEqual(problems, [])

    def test_load_orders_files_by_name(self):
        self.add_basic()
        self.write_case(
            "02-b.toml", GROUP + "\n" + case_block(id_line='id = "test.b"')
        )
        self.write_case(
            "01-a.toml", GROUP + "\n" + case_block(id_line='id = "test.a"')
        )
        loaded, problems = self.load()
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("01-a.toml", "test.a"), ("02-b.toml", "test.b")],
        )
        self.assertEqual(problems, [])

    def test_file_name_problem(self):
        self.add_basic()
        self.write_case("1-a.toml", GROUP + "\n" + case_block())
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("1-a.toml", "-", "file-name")])
        self.assertEqual(loaded, [])

    def test_toml_syntax_problem(self):
        self.add_basic()
        self.write_case("01-bad.toml", "= nope\n")
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "toml-syntax")])
        self.assertEqual(loaded, [])

    def test_group_key_problem(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            '[group]\ntitle = "Group"\n' + "\n" + case_block(),
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "group-key")])
        self.assertEqual(loaded, [])

    def test_group_empty_title(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            '[group]\ntitle = ""\nref = "Ref"\n' + "\n" + case_block(),
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "group-key")])
        self.assertEqual(loaded, [])

    def test_group_empty_ref(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            '[group]\ntitle = "Group"\nref = ""\n' + "\n" + case_block(),
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "group-key")])
        self.assertEqual(loaded, [])

    def test_group_whitespace_string(self):
        self.add_basic()
        self.write_case(
            "01-space.toml",
            '[group]\ntitle = " "\nref = " "\n' + "\n" + case_block(),
        )
        loaded, problems = self.load()
        self.assertEqual(problems, [])
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].group, " ")

    def test_case_key_problem(self):
        self.add_basic()
        self.write_case(
            "01-cases.toml",
            GROUP
            + "\n"
            + case_block(
                id_line='id = "test.extra"', extra='foo = "x"\n'
            )
            + "\n"
            + case_block(id_line=""),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-cases.toml", "test.extra", "case-key"),
                ("01-cases.toml", "#2", "case-key"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_id_pattern_problem(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            GROUP + "\n" + case_block(id_line='id = "Bad.Id"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems), [("01-bad.toml", "Bad.Id", "id-pattern")]
        )
        self.assertEqual(loaded, [])

    def test_id_duplicate_problem(self):
        self.add_basic()
        self.write_case(
            "01-a.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        self.write_case(
            "02-b.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [("02-b.toml", "test.same", "id-duplicate")],
        )
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("01-a.toml", "test.same")],
        )

    def test_dict_missing_problem(self):
        self.write_case(
            "01-missing.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.missing-system"\ndicts = ["nope"]\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [("01-missing.toml", "test.missing-system", "dict-missing")],
        )
        self.assertEqual(loaded, [])

    def test_user_dict_missing_problem(self):
        self.add_basic()
        self.write_case(
            "01-missing.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.missing-user"\ndicts = ["basic"]\n'
            + 'user_dict = "nope"\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [("01-missing.toml", "test.missing-user", "dict-missing")],
        )
        self.assertEqual(loaded, [])

    def test_step_problems(self):
        self.add_basic()
        self.write_case(
            "01-steps.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.steps"\ndicts = ["basic"]\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\nfoo = "x"\n'
            + '[[case.step]]\nkeys = "a"\n'
            + '[[case.step]]\nkeys = "a  b"\ntext = ""\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\nmode = "kana"\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-steps.toml", "test.steps#1", "step-key"),
                ("01-steps.toml", "test.steps#2", "step-empty"),
                ("01-steps.toml", "test.steps#3", "keys-spacing"),
                ("01-steps.toml", "test.steps#4", "mode-value"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_validate_dict_ok(self):
        self.write_dict("basic.jisyo", BASIC)
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "basic.jisyo")), []
        )

    def test_validate_dict_coding_line(self):
        self.write_dict(
            "coding.jisyo",
            BASIC.replace(
                ";; -*- mode: fundamental; coding: utf-8 -*-",
                ";; coding: utf-8",
                1,
            ),
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "coding.jisyo")),
            [("coding.jisyo", "line 1", "dict-coding-line")],
        )

    def test_validate_dict_markers(self):
        self.write_dict(
            "markers.jisyo",
            BASIC.replace(";; okuri-nasi entries.\n", "", 1),
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "markers.jisyo")),
            [("markers.jisyo", "-", "dict-markers")],
        )

    def test_dict_missing_order(self):
        self.add_basic()
        self.write_case(
            "01-missing.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.order"\n'
            + 'dicts = ["x", "basic", "y"]\nuser_dict = "z"\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-missing.toml", "test.order", "dict-missing"),
                ("01-missing.toml", "test.order", "dict-missing"),
                ("01-missing.toml", "test.order", "dict-missing"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_top_key_problem(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            'foo = "x"\n' + GROUP + "\n" + case_block(),
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "top-key")])
        self.assertEqual(loaded, [])

    def test_non_utf8_case_file(self):
        self.add_basic()
        self.write_case_bytes(
            "01-bad.toml",
            '[group]\ntitle = "Group"\nref = "Ref"\n'.encode("utf-8")
            + b"\xff",
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "toml-syntax")])
        self.assertEqual(loaded, [])

    def test_validate_dict_encoding(self):
        self.write_dict_bytes(
            "encoding.jisyo", b"\xef\xbb\xbf" + BASIC.encode("utf-8")
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "encoding.jisyo")),
            [("encoding.jisyo", "-", "dict-encoding")],
        )

    def test_validate_dict_line_end(self):
        self.write_dict("crlf.jisyo", BASIC.replace("\n", "\r\n"))
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "crlf.jisyo")),
            [("crlf.jisyo", "-", "dict-line-end")],
        )
        self.write_dict("nofinal.jisyo", BASIC[:-1])
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "nofinal.jisyo")),
            [("nofinal.jisyo", "-", "dict-line-end")],
        )

    def test_validate_dict_sort(self):
        self.write_dict(
            "nasi.jisyo",
            ";; -*- mode: fundamental; coding: utf-8 -*-\n"
            ";; okuri-ari entries.\n"
            ";; okuri-nasi entries.\n"
            "きょ /距/\n"
            "かんじ /漢字/\n",
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "nasi.jisyo")),
            [("nasi.jisyo", "line 5", "dict-sort")],
        )
        self.write_dict(
            "ari.jisyo",
            ";; -*- mode: fundamental; coding: utf-8 -*-\n"
            ";; okuri-ari entries.\n"
            "うごk /動/\n"
            "もt /持/\n"
            ";; okuri-nasi entries.\n",
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "ari.jisyo")),
            [("ari.jisyo", "line 4", "dict-sort")],
        )

    def test_validate_dict_entry(self):
        self.write_dict(
            "entry.jisyo",
            ";; -*- mode: fundamental; coding: utf-8 -*-\n"
            ";; okuri-ari entries.\n"
            ";; okuri-nasi entries.\n"
            "かんじ 漢字\n"
            "かんじ /漢字;注/\n"
            'こめ /(concat "a")/\n'
            ";; comment\n"
            "さ /差/\n",
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "entry.jisyo")),
            [
                ("entry.jisyo", "line 4", "dict-entry"),
                ("entry.jisyo", "line 5", "dict-entry"),
                ("entry.jisyo", "line 6", "dict-entry"),
                ("entry.jisyo", "line 7", "dict-entry"),
            ],
        )

    def test_validate_dict_interleaves_entry_and_sort(self):
        content = (
            ";; -*- mode: fundamental; coding: utf-8 -*-\n"
            ";; okuri-ari entries.\n"
            ";; okuri-nasi entries.\n"
            "きょ /距/\n"
            "かんじ /漢字/\n"
            "こめ 米\n"
            "かんじ /幹事/\n"
        )
        self.write_dict_bytes("mixed.jisyo", content.encode("utf-8"))
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "mixed.jisyo")),
            [
                ("mixed.jisyo", "line 5", "dict-sort"),
                ("mixed.jisyo", "line 6", "dict-entry"),
                ("mixed.jisyo", "line 7", "dict-sort"),
            ],
        )

    def test_fixture_cases_are_valid(self):
        self.add_basic()
        self.write_case(
            "01-a.toml",
            GROUP
            + "\n"
            + case_block(id_line='id = "test.one"')
            + "\n"
            + case_block(id_line='id = "test.two"'),
        )
        self.write_case(
            "02-b.toml",
            GROUP + "\n" + case_block(id_line='id = "test.three"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            [case.id for case in loaded], ["test.one", "test.two", "test.three"]
        )
        self.assertEqual(problems, [])
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "basic.jisyo")), []
        )

    def test_problem_file_order(self):
        self.add_basic()
        bad_step = '[[case.step]]\nkeys = "a"\ntext = ""\nmode = "kana"\n'
        self.write_case(
            "02-b.toml",
            GROUP + "\n" + case_block(id_line='id = "test.b"', steps=bad_step),
        )
        self.write_case(
            "01-a.toml",
            GROUP + "\n" + case_block(id_line='id = "test.a"', steps=bad_step),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-a.toml", "test.a#1", "mode-value"),
                ("02-b.toml", "test.b#1", "mode-value"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_problem_multiplicity(self):
        self.add_basic()
        self.write_case(
            "01-multi.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.multi"\ndicts = ["basic"]\n'
            + 'foo = "x"\nbar = "y"\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\n'
            + 'foo = "x"\nbar = "y"\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-multi.toml", "test.multi", "case-key"),
                ("01-multi.toml", "test.multi#1", "step-key"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_missing_or_nonstring_id_labels(self):
        self.write_case(
            "01-labels.toml",
            GROUP
            + "\n"
            + '[[case]]\ndicts = ["nope"]\n'
            + '[[case.step]]\nkeys = "a  b"\ntext = ""\n'
            + '[[case]]\nid = 7\ndicts = ["nope"]\n'
            + '[[case.step]]\nkeys = "a  b"\ntext = ""\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-labels.toml", "#1", "case-key"),
                ("01-labels.toml", "#1", "dict-missing"),
                ("01-labels.toml", "#1#1", "keys-spacing"),
                ("01-labels.toml", "#2", "case-key"),
                ("01-labels.toml", "#2", "dict-missing"),
                ("01-labels.toml", "#2#1", "keys-spacing"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_invalid_case_reserves_id(self):
        self.add_basic()
        self.write_case(
            "01-a.toml",
            GROUP
            + "\n"
            + case_block(
                id_line='id = "test.same"', extra='foo = "x"\n'
            ),
        )
        self.write_case(
            "02-b.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-a.toml", "test.same", "case-key"),
                ("02-b.toml", "test.same", "id-duplicate"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_rejected_filename_does_not_reserve_id(self):
        self.add_basic()
        self.write_case(
            "01_bad.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        self.write_case(
            "02-good.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems), [("01_bad.toml", "-", "file-name")]
        )
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("02-good.toml", "test.same")],
        )

    def test_rejected_syntax_does_not_reserve_id(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            GROUP
            + "\n"
            + case_block(id_line='id = "test.same"')
            + "=\n",
        )
        self.write_case(
            "02-good.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems), [("01-bad.toml", "-", "toml-syntax")]
        )
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("02-good.toml", "test.same")],
        )

    def test_rejected_top_does_not_reserve_id(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            'foo = "x"\n'
            + GROUP
            + "\n"
            + case_block(id_line='id = "test.same"'),
        )
        self.write_case(
            "02-good.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bad.toml", "-", "top-key")])
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("02-good.toml", "test.same")],
        )

    def test_rejected_group_does_not_reserve_id(self):
        self.add_basic()
        self.write_case(
            "01-bad.toml",
            '[group]\ntitle = "Group"\n'
            + "\n"
            + case_block(id_line='id = "test.same"'),
        )
        self.write_case(
            "02-good.toml",
            GROUP + "\n" + case_block(id_line='id = "test.same"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems), [("01-bad.toml", "-", "group-key")]
        )
        self.assertEqual(
            [(case.file, case.id) for case in loaded],
            [("02-good.toml", "test.same")],
        )

    def test_file_name_stops_before_parse(self):
        self.write_case_bytes("1-a.toml", b"\xff")
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("1-a.toml", "-", "file-name")])
        self.assertEqual(loaded, [])

    def test_case_bom_is_syntax(self):
        self.add_basic()
        content = GROUP + "\n" + case_block()
        self.write_case_bytes(
            "01-bom.toml", b"\xef\xbb\xbf" + content.encode("utf-8")
        )
        loaded, problems = self.load()
        self.assertEqual(triples(problems), [("01-bom.toml", "-", "toml-syntax")])
        self.assertEqual(loaded, [])

    def test_dict_name_rejected(self):
        self.add_basic()
        names = ["../outside", "/outside", "a/b", "a\\b", "..", ""]
        for name in names:
            for field in ("dicts", "user_dict"):
                with self.subTest(name=name, field=field):
                    if field == "dicts":
                        body = case_block(
                            id_line='id = "test.name"',
                            dicts=f"[{json.dumps(name)}]",
                        )
                    else:
                        body = case_block(
                            id_line='id = "test.name"',
                            extra=f"user_dict = {json.dumps(name)}\n",
                        )
                    self.write_case("01-name.toml", GROUP + "\n" + body)
                    loaded, problems = self.load()
                    self.assertEqual(
                        triples(problems),
                        [("01-name.toml", "test.name", "dict-name")],
                    )
                    self.assertEqual(loaded, [])

    def test_dict_resolved_path_stays_inside(self):
        outside = self.root / "outside.jisyo"
        outside.write_text(BASIC, encoding="utf-8")
        (self.dict_dir / "basic.jisyo").symlink_to(outside)
        self.write_case(
            "01-link.toml",
            GROUP + "\n" + case_block(id_line='id = "test.link"'),
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems), [("01-link.toml", "test.link", "dict-missing")]
        )
        self.assertEqual(loaded, [])

    def test_repeated_missing_names(self):
        self.add_basic()
        self.write_case(
            "01-missing.toml",
            GROUP
            + "\n"
            + '[[case]]\nid = "test.repeated"\n'
            + 'dicts = ["nope", "nope"]\nuser_dict = "nope"\n'
            + '[[case.step]]\nkeys = "a"\ntext = ""\n',
        )
        loaded, problems = self.load()
        self.assertEqual(
            triples(problems),
            [
                ("01-missing.toml", "test.repeated", "dict-missing"),
                ("01-missing.toml", "test.repeated", "dict-missing"),
                ("01-missing.toml", "test.repeated", "dict-missing"),
            ],
        )
        self.assertEqual(loaded, [])

    def test_validate_dict_before_marker(self):
        self.write_dict(
            "before.jisyo",
            BASIC.replace(
                ";; okuri-ari entries.\n",
                "not a comment\n;; okuri-ari entries.\n",
                1,
            ),
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "before.jisyo")),
            [("before.jisyo", "line 2", "dict-entry")],
        )
        self.write_dict(
            "commented.jisyo",
            BASIC.replace(
                ";; okuri-ari entries.\n",
                ";; comment\n;; okuri-ari entries.\n",
                1,
            ),
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "commented.jisyo")), []
        )
        self.write_dict("unchanged.jisyo", BASIC)
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "unchanged.jisyo")), []
        )

    def test_validate_dict_marker_on_first_line(self):
        self.write_dict(
            "marker.jisyo",
            BASIC.replace(
                ";; -*- mode: fundamental; coding: utf-8 -*-\n", "", 1
            ),
        )
        self.assertEqual(
            triples(cases.validate_dict(self.dict_dir / "marker.jisyo")),
            [("marker.jisyo", "line 1", "dict-coding-line")],
        )


if __name__ == "__main__":
    unittest.main()
