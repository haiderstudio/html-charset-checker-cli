#!/usr/bin/env python3
"""Check every HTML file declares its character encoding.

Run: python3 src/html_charset_checker.py page.html
     python3 src/html_charset_checker.py site/
     python3 src/html_charset_checker.py --stdin < page.html

A page with no charset makes the browser guess the encoding, and
the guess is wrong often enough that accented names and emoji turn
into garbled characters — a real bug that looks like corrupt
content. The fix is one line per page once it is found, but nothing
stops you shipping a page without one. This tool finds every HTML
file that is missing a charset declaration, or declares something
other than UTF-8, and reports each one with the file and the line
number. It exits 1 when any file fails, so it can fail a CI run.
A page that declares UTF-8 early in <head> exits 0.

A declaration is a <meta charset="utf-8"> tag, or a <meta
http-equiv="content-type"> tag whose content names charset=utf-8.
The declaration must sit in the first 1024 bytes of the file —
the browser reads only that far when it looks for one — so a tag
that comes later is reported as too late, and a tag after </head>
is reported as outside the head. A page needs exactly one
declaration: a second one is reported, and two that disagree are
reported as a conflict. A UTF-8 byte-order mark at the start of
the file also counts as a declaration, because the browser reads
it first — but it is not a substitute for the tag, and a wrong
tag is still reported even when a mark is present. Only the
charset is checked: the viewport tag, the lang attribute, and
everything else in the page are other tools' jobs.

Report-only: it never edits a file, never fetches a URL, and only
reads the files and folders you point it at.
"""

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

VERSION = "1.0.0"

# The browser looks for a charset declaration only in the first
# 1024 bytes of the file, so a tag past that point does not count.
EARLY_BYTES = 1024

CHARSET_RE = re.compile(r"charset\s*=\s*([^\s;\"']+)", re.IGNORECASE)


def _is_utf8(value):
    """True when a charset value names UTF-8, any spelling."""
    if value is None:
        return False
    return value.strip().lower() in ("utf-8", "utf8")


class _CharsetParser(HTMLParser):
    """Collect every charset declaration, with line and position.

    A tag inside an HTML comment never reaches handle_starttag,
    so commented-out tags do not count. The parser also records
    whether each tag sits inside <head> or after </head>, and how
    far into the file — in bytes — each tag starts.
    """

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text = text
        self.lines = text.splitlines(keepends=True)
        self.declarations = []
        self._in_head = False
        self._head_closed = False

    def _byte_offset(self, line, col):
        chars = sum(len(self.lines[i]) for i in range(line - 1)) + col
        return len(self.text[:chars].encode("utf-8"))

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self._in_head = True
            return
        if tag != "meta":
            return
        values = {}
        for name, value in attrs:
            values[name.lower()] = value
        line, col = self.getpos()
        offset = self._byte_offset(line, col)
        if "charset" in values:
            self.declarations.append((line, offset, values["charset"],
                                      self._in_head, self._head_closed))
            return
        http_equiv = values.get("http-equiv", "")
        if http_equiv is None:
            http_equiv = ""
        if http_equiv.strip().lower() != "content-type":
            return
        content = values.get("content", "")
        if content is None:
            return
        match = CHARSET_RE.search(content)
        if match:
            self.declarations.append((line, offset, match.group(1),
                                      self._in_head, self._head_closed))

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
            self._head_closed = True


def check_document(text, name):
    """Check one HTML document's text. Returns a list of problems.

    Each problem is a dict with file, line, kind, and message.
    kind is one of: missing, wrong-value, too-late, outside-head,
    multiple, conflict.
    """
    has_bom = text.startswith("\ufeff")
    parser = _CharsetParser(text)
    parser.feed(text)
    problems = []
    declarations = parser.declarations
    if not declarations:
        if has_bom:
            return problems
        problems.append({
            "file": name,
            "line": 1,
            "kind": "missing",
            "message": "missing charset — add <meta charset="
                       "\"utf-8\"> at the top of <head>",
        })
        return problems
    first_value = declarations[0][2]
    for index, (line, offset, value, _in_head, head_closed) in enumerate(
            declarations):
        if value is None or str(value).strip() == "":
            problems.append({
                "file": name,
                "line": line,
                "kind": "wrong-value",
                "message": "charset tag has no value — set it to "
                           "utf-8",
            })
        elif not _is_utf8(value):
            problems.append({
                "file": name,
                "line": line,
                "kind": "wrong-value",
                "message": "declares charset %s, not UTF-8 — change "
                           "it to utf-8" % value.strip(),
            })
        if offset > EARLY_BYTES:
            problems.append({
                "file": name,
                "line": line,
                "kind": "too-late",
                "message": "charset is declared %d bytes into the "
                           "file — it must be in the first 1024 "
                           "bytes, move it to the top of <head>"
                           % offset,
            })
        if head_closed:
            problems.append({
                "file": name,
                "line": line,
                "kind": "outside-head",
                "message": "charset tag is after </head> — move it "
                           "inside <head>",
            })
        if index > 0:
            if first_value is None or value is None:
                same = first_value is value
            else:
                same = (str(first_value).strip().lower()
                        == str(value).strip().lower())
            if same:
                problems.append({
                    "file": name,
                    "line": line,
                    "kind": "multiple",
                    "message": "second charset declaration — a page "
                               "needs one charset only",
                })
            else:
                problems.append({
                    "file": name,
                    "line": line,
                    "kind": "conflict",
                    "message": "declares charset %s but the page "
                               "already declares %s — keep one "
                               "declaration only"
                               % (value, first_value),
                })
    return problems


def check_file(path):
    """Check one file on disk. Returns a list of problems."""
    try:
        raw = open(path, "rb").read()
    except OSError as exc:
        return [{
            "file": path,
            "line": 1,
            "kind": "unreadable",
            "message": "could not be read: %s" % exc.strerror,
        }]
    try:
        # Plain UTF-8, not utf-8-sig: the byte-order mark is kept so
        # check_document can count it as a declaration.
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [{
            "file": path,
            "line": 1,
            "kind": "unreadable",
            "message": "could not be read as UTF-8 — save the file "
                       "as UTF-8 and try again",
        }]
    return check_document(text, path)


def _is_html_file(path):
    lowered = path.lower()
    return lowered.endswith(".html") or lowered.endswith(".htm")


def collect_files(paths, recursive=True, exclude=None):
    """Expand paths into a sorted list of HTML files to check.

    A path given directly is always checked, whatever its name.
    A folder is walked for .html and .htm files. .git folders are
    never walked, and directory links are never followed.
    """
    exclude = exclude or []
    found = []
    for path in paths:
        if os.path.isfile(path):
            found.append(path)
        elif os.path.isdir(path):
            if recursive:
                for root, dirs, files in os.walk(path, followlinks=False):
                    dirs[:] = sorted(
                        d for d in dirs
                        if d != ".git"
                        and not any(re.search(p, d) for p in exclude)
                    )
                    for name in sorted(files):
                        full = os.path.join(root, name)
                        if _is_html_file(full):
                            if any(re.search(p, full) for p in exclude):
                                continue
                            found.append(full)
            else:
                for name in sorted(os.listdir(path)):
                    full = os.path.join(path, name)
                    if os.path.isfile(full) and _is_html_file(full):
                        if any(re.search(p, full) for p in exclude):
                            continue
                        found.append(full)
        else:
            raise FileNotFoundError(path)
    return found


def _print_text(problems, checked):
    bad_files = sorted({p["file"] for p in problems})
    for problem in problems:
        print("FAIL %s: %s (line %d)"
              % (problem["file"], problem["message"], problem["line"]))
    if problems:
        print("Checked %d file(s), %d problem(s) in %d file(s)."
              % (checked, len(problems), len(bad_files)))
    else:
        print("OK — %d file(s) checked, every file declares UTF-8."
              % checked)


def _print_json(problems, checked):
    print(json.dumps({
        "files_checked": checked,
        "problems": problems,
        "ok": not problems,
    }, indent=2, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html_charset_checker",
        description="Check every HTML file declares UTF-8 early in "
                    "<head>.",
    )
    parser.add_argument("paths", nargs="*", help="HTML files or folders to check")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one HTML document read from standard input")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="PATTERN",
                        help="skip files or folders whose path matches "
                             "this regular expression (repeatable)")
    parser.add_argument("--version", action="version",
                        version="html_charset_checker " + VERSION)
    args = parser.parse_args(argv)

    if args.stdin and args.paths:
        parser.error("--stdin takes no paths")
    if not args.stdin and not args.paths:
        parser.error("give at least one file or folder, or --stdin")

    if args.stdin:
        text = sys.stdin.read()
        problems = check_document(text, "<stdin>")
        if args.json:
            _print_json(problems, 1)
        else:
            _print_text(problems, 1)
        return 0 if not problems else 1

    try:
        files = collect_files(
            args.paths,
            recursive=not args.no_recursive,
            exclude=args.exclude,
        )
    except FileNotFoundError as exc:
        print("error: no such file or folder: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no HTML files found", file=sys.stderr)
        return 2

    problems = []
    for path in files:
        problems.extend(check_file(path))

    if args.json:
        _print_json(problems, len(files))
    else:
        _print_text(problems, len(files))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
