#!/usr/bin/env python3
"""Tests for html_charset_checker — stdlib unittest only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html_charset_checker as checker

REPO = Path(__file__).resolve().parent.parent
GOOD = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        '  <title>t</title>\n</head>\n<body></body>\n</html>\n')
HTTP_EQUIV_GOOD = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n'
                   '  <meta http-equiv="content-type" '
                   'content="text/html; charset=utf-8">\n'
                   '  <title>t</title>\n</head>\n<body></body>\n'
                   '</html>\n')


def run_cli(argv, stdin_text=None):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    old_stdin = sys.stdin
    if stdin_text is not None:
        sys.stdin = io.StringIO(stdin_text)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = checker.main(argv)
            except SystemExit as exc:
                code = exc.code
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def kinds(problems):
    return [p["kind"] for p in problems]


def _padded_doc(pad_chars):
    """A document whose charset tag follows a comment of pad_chars."""
    return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n  <!-- '
            + "x" * pad_chars + ' -->\n  <meta charset="utf-8">\n'
            '  <title>t</title>\n</head>\n<body></body>\n</html>\n')


class TestIsUtf8(unittest.TestCase):
    def test_utf8_with_hyphen(self):
        self.assertTrue(checker._is_utf8("utf-8"))

    def test_utf8_uppercase(self):
        self.assertTrue(checker._is_utf8("UTF-8"))

    def test_utf8_without_hyphen(self):
        self.assertTrue(checker._is_utf8("utf8"))

    def test_other_charset_false(self):
        self.assertFalse(checker._is_utf8("iso-8859-1"))

    def test_empty_false(self):
        self.assertFalse(checker._is_utf8(""))

    def test_none_false(self):
        self.assertFalse(checker._is_utf8(None))


class TestCheckDocument(unittest.TestCase):
    def test_good_page_no_problems(self):
        self.assertEqual(checker.check_document(GOOD, "x.html"), [])

    def test_http_equiv_form_passes(self):
        self.assertEqual(
            checker.check_document(HTTP_EQUIV_GOOD, "x.html"), [])

    def test_http_equiv_uppercase_passes(self):
        text = ('<html><head>\n<meta HTTP-EQUIV="Content-Type" '
                'content="text/html; charset=UTF-8">\n</head></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_http_equiv_no_charset_missing(self):
        text = ('<html><head>\n<meta http-equiv="content-type" '
                'content="text/html">\n</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["missing"])

    def test_http_equiv_no_content_missing(self):
        text = ('<html><head>\n<meta http-equiv="content-type">\n'
                '</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["missing"])

    def test_charset_no_value(self):
        text = '<html><head>\n<meta charset>\n</head></html>'
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["wrong-value"])
        self.assertIn("no value", problems[0]["message"])

    def test_missing_charset(self):
        problems = checker.check_document(
            "<html><head><title>t</title></head></html>", "x.html")
        self.assertEqual(kinds(problems), ["missing"])
        self.assertEqual(problems[0]["line"], 1)
        self.assertIn("missing charset", problems[0]["message"])

    def test_empty_document_missing(self):
        problems = checker.check_document("", "x.html")
        self.assertEqual(kinds(problems), ["missing"])

    def test_non_utf8_value(self):
        text = ('<html><head>\n<meta charset="iso-8859-1">\n'
                '</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["wrong-value"])
        self.assertEqual(problems[0]["line"], 2)
        self.assertIn("iso-8859-1", problems[0]["message"])

    def test_charset_too_late(self):
        text = _padded_doc(1100)
        offset = len(text[:text.index("<meta charset")].encode("utf-8"))
        self.assertGreater(offset, 1024)
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["too-late"])
        self.assertIn("1024 bytes", problems[0]["message"])
        self.assertIn(str(offset), problems[0]["message"])

    def test_charset_just_inside_1024_bytes(self):
        text = _padded_doc(800)
        offset = len(text[:text.index("<meta charset")].encode("utf-8"))
        self.assertLessEqual(offset, 1024)
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_charset_after_head_flagged(self):
        text = ('<html><head><title>t</title></head>\n<body>\n'
                '<meta charset="utf-8">\n</body></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["outside-head"])
        self.assertEqual(problems[0]["line"], 3)

    def test_two_matching_declarations(self):
        text = ('<html><head>\n<meta charset="utf-8">\n'
                '<meta charset="utf-8">\n</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["multiple"])
        self.assertEqual(problems[0]["line"], 3)

    def test_two_conflicting_declarations(self):
        text = ('<html><head>\n<meta charset="utf-8">\n'
                '<meta charset="iso-8859-1">\n</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems),
                         ["wrong-value", "conflict"])
        self.assertEqual([p["line"] for p in problems], [3, 3])
        self.assertIn("already declares utf-8", problems[1]["message"])

    def test_bom_alone_passes(self):
        text = ('\ufeff<!DOCTYPE html>\n<html><head>\n'
                '<title>t</title></head><body></body></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_bom_with_wrong_tag_still_flagged(self):
        text = ('\ufeff<html><head>\n<meta charset="iso-8859-1">\n'
                '</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["wrong-value"])

    def test_no_head_at_all_passes(self):
        text = ('<html><body>\n<meta charset="utf-8">\n'
                '</body></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_uppercase_tag_and_value_ok(self):
        text = ('<HTML><HEAD>\n<META CHARSET="UTF-8">\n'
                '</HEAD></HTML>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_unquoted_value_ok(self):
        text = ('<html><head>\n<meta charset=utf-8>\n</head></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_charset_inside_comment_does_not_count(self):
        text = ('<html><head>\n<!-- <meta charset="utf-8"> -->\n'
                '</head></html>')
        problems = checker.check_document(text, "x.html")
        self.assertEqual(kinds(problems), ["missing"])

    def test_non_charset_meta_ignored(self):
        text = ('<html><head>\n<meta name="viewport" '
                'content="width=device-width, initial-scale=1">\n'
                '<meta charset="utf-8">\n</head></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])

    def test_problem_carries_file_name(self):
        problems = checker.check_document("<html></html>", "page.html")
        self.assertEqual(problems[0]["file"], "page.html")

    def test_charset_with_quotes_in_content(self):
        text = ('<html><head>\n<meta http-equiv="content-type" '
                'content="text/html;charset=UTF-8">\n</head></html>')
        self.assertEqual(checker.check_document(text, "x.html"), [])


class TestCheckFile(unittest.TestCase):
    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "good.html", GOOD)
            self.assertEqual(checker.check_file(path), [])

    def test_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", "<html></html>")
            problems = checker.check_file(path)
            self.assertEqual(kinds(problems), ["missing"])
            self.assertEqual(problems[0]["file"], path)

    def test_missing_file_reports_error(self):
        problems = checker.check_file("/nonexistent/page.html")
        self.assertEqual(kinds(problems), ["unreadable"])
        self.assertIn("could not be read", problems[0]["message"])

    def test_non_utf8_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", b"<html>\xff</html>")
            problems = checker.check_file(path)
            self.assertEqual(kinds(problems), ["unreadable"])
            self.assertIn("UTF-8", problems[0]["message"])

    def test_bom_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "good.html",
                         b"\xef\xbb\xbf<html><head><title>t</title>"
                         b"</head><body></body></html>")
            self.assertEqual(checker.check_file(path), [])

    def test_input_file_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", "<html></html>")
            before = Path(path).read_bytes()
            checker.check_file(path)
            self.assertEqual(Path(path).read_bytes(), before)


class TestCollectFiles(unittest.TestCase):
    def test_direct_file_any_name_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "page.txt", GOOD)
            self.assertEqual(checker.collect_files([path]), [path])

    def test_folder_walk_finds_html_and_htm_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", GOOD)
            b = write(tmp, "b.htm", GOOD)
            write(tmp, "c.txt", GOOD)
            write(tmp, "d.css", GOOD)
            self.assertEqual(checker.collect_files([tmp]), [a, b])

    def test_folder_walk_is_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", GOOD)
            b = write(tmp, "sub/b.html", GOOD)
            self.assertEqual(checker.collect_files([tmp]), [a, b])

    def test_git_folder_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", GOOD)
            write(tmp, ".git/hooks/b.html", GOOD)
            self.assertEqual(checker.collect_files([tmp]), [a])

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", GOOD)
            write(tmp, "sub/b.html", GOOD)
            self.assertEqual(
                checker.collect_files([tmp], recursive=False), [a])

    def test_exclude_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "a.html", GOOD)
            write(tmp, "skip.html", GOOD)
            self.assertEqual(
                checker.collect_files([tmp], exclude=["skip"]),
                [a])

    def test_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                checker.collect_files([os.path.join(tmp, "nope")])

    def test_uppercase_extension_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, "UP.HTML", GOOD)
            self.assertEqual(checker.collect_files([tmp]), [a])


class TestMain(unittest.TestCase):
    def test_clean_run_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "good.html", GOOD)
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK", out)

    def test_dirty_run_exit_1_and_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", "<html></html>")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("FAIL", out)
            self.assertIn("bad.html", out)
            self.assertIn("line 1", out)

    def test_folder_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.html", GOOD)
            write(tmp, "b.html", "<html></html>")
            write(tmp, "c.html", '<html><head><meta charset="iso-8859-1">'
                  '</head></html>')
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 3 file(s), 2 problem(s) in 2 file(s).",
                          out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", "<html></html>")
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertFalse(data["ok"])
            self.assertEqual(data["files_checked"], 1)
            self.assertEqual(len(data["problems"]), 1)
            self.assertEqual(data["problems"][0]["kind"], "missing")
            self.assertTrue(data["problems"][0]["file"].endswith("bad.html"))

    def test_json_output_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "good.html", GOOD)
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 0)
            data = json.loads(out)
            self.assertTrue(data["ok"])
            self.assertEqual(data["problems"], [])

    def test_stdin_clean(self):
        code, out, _ = run_cli(["--stdin"], stdin_text=GOOD)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_stdin_dirty(self):
        code, out, _ = run_cli(["--stdin"], stdin_text="<html></html>")
        self.assertEqual(code, 1)
        self.assertIn("missing charset", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "x.html"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err.lower())

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("usage", err.lower())

    def test_missing_path_exit_2(self):
        code, _, err = run_cli(["/nonexistent/page.html"])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err.lower())

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no HTML files", err)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("html_charset_checker", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.html", b"<html>\xff</html>")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("UTF-8", out)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "good.html", GOOD)
            result = subprocess.run(
                [sys.executable, str(REPO / "src" / "html_charset_checker.py"), path],
                capture_output=True, text=True, cwd="/tmp",
                env={**os.environ, "HOME": "/tmp/fakehome"},
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("OK", result.stdout)

    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", str(REPO / "examples" / "run-example.sh")],
            capture_output=True, text=True, cwd=str(REPO),
        )
        sample = (REPO / "examples" / "sample-output.md").read_text()
        self.assertIn(result.stdout.strip(), sample)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        good = subprocess.run(
            [sys.executable, "src/html_charset_checker.py",
             "examples/good.html"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(good.returncode, 0)
        self.assertIn(good.stdout.strip(), readme)
        bad = subprocess.run(
            [sys.executable, "src/html_charset_checker.py",
             "examples/bad.html"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(bad.returncode, 1)
        self.assertIn(bad.stdout.strip(), readme)
        edge = subprocess.run(
            [sys.executable, "src/html_charset_checker.py",
             "examples/edge.html"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(edge.returncode, 1)
        self.assertIn(edge.stdout.strip(), readme)
        late = subprocess.run(
            [sys.executable, "src/html_charset_checker.py",
             "examples/late.html"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(late.returncode, 1)
        self.assertIn(late.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/html_charset_checker.py", "examples/"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(folder.returncode, 1)
        self.assertIn(folder.stdout.strip(), readme)
        self.assertIn("Checked 4 file(s), 3 problem(s) in 3 file(s).",
                      folder.stdout)
        self.assertIn("Checked 4 file(s), 3 problem(s) in 3 file(s).",
                      readme)
        js = subprocess.run(
            [sys.executable, "src/html_charset_checker.py",
             "--json", "examples/bad.html"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)
        http_equiv = subprocess.run(
            [sys.executable, "src/html_charset_checker.py", "--stdin"],
            input='<!DOCTYPE html>\n<html><head>\n<meta '
                  'http-equiv="content-type" content="text/html; '
                  'charset=utf-8">\n<title>t</title></head>'
                  '<body></body></html>\n',
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(http_equiv.returncode, 0)
        self.assertIn(http_equiv.stdout.strip(), readme)
        conflict = subprocess.run(
            [sys.executable, "src/html_charset_checker.py", "--stdin"],
            input='<!DOCTYPE html>\n<html><head>\n<meta '
                  'charset="utf-8">\n<meta charset="iso-8859-1">\n'
                  '<title>t</title></head><body></body></html>\n',
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(conflict.returncode, 1)
        self.assertIn(conflict.stdout.strip(), readme)
        nested = subprocess.run(
            [sys.executable, str(REPO / "src" / "html_charset_checker.py"),
             str(REPO / "examples" / "good.html")],
            capture_output=True, text=True, cwd="/tmp",
        )
        self.assertEqual(nested.returncode, 0)


class TestRepoHygiene(unittest.TestCase):
    def _repo_files(self):
        files = []
        for root, dirs, filenames in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", "tests")]
            for name in filenames:
                files.append(Path(root) / name)
        return files

    def test_no_placeholder_text(self):
        banned = ["TODO", "FIXME", "coming soon", "lorem", "XXX"]
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for word in banned:
                self.assertNotIn(word, text, "%s contains %r" % (path, word))

    def test_no_absolute_paths(self):
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            self.assertNotIn("/home/hatch", text, str(path))
            self.assertNotIn("/Users/", text, str(path))
            self.assertNotIn("/tmp/", text, str(path))

    def test_no_secrets(self):
        for path in self._repo_files():
            text = path.read_text(errors="ignore").lower()
            for word in ["api_key", "password =", "secret =", "token ="]:
                self.assertNotIn(word, text, "%s contains %r" % (path, word))

    def test_stdlib_imports_only(self):
        import ast
        allowed = {"argparse", "json", "os", "re", "sys", "html"}
        tree = ast.parse((REPO / "src" / "html_charset_checker.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module.split(".")[0], allowed)

    def test_no_network_use_in_src(self):
        src = (REPO / "src" / "html_charset_checker.py").read_text()
        for word in ["urllib", "requests", "socket", "http.client", "urlopen"]:
            self.assertNotIn(word, src)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("tests/test_html_charset_checker.py", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)
        self.assertIn("3.12", ci)

    def test_licence_present(self):
        self.assertTrue((REPO / "LICENSE").exists())
        self.assertIn("MIT License", (REPO / "LICENSE").read_text())

    def test_readme_names_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("html-viewport-checker-cli", readme)
        self.assertIn("html-lang-checker-cli", readme)
        self.assertIn("html-title-checker-cli", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
