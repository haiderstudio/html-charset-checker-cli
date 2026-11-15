# html-charset-checker-cli

Check every HTML file declares UTF-8 early in the head, fail CI when one does not.

[![CI](https://github.com/haiderstudio/html-charset-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/html-charset-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`html_charset_checker` walks HTML files, checks each one
declares its character encoding as UTF-8 early in `<head>`, and
reports each file that is missing it, or declares something
else, with the file and the line number. It exits 1 when any
file fails, so it can fail a CI run. A page that declares UTF-8
early in `<head>` exits 0.

- A page with no charset makes the browser guess the encoding,
  and the guess is wrong often enough that accented names and
  emoji turn into garbled characters — a real bug that looks
  like corrupt content, and a one-line fix per page once it is
  found.
- A declaration is a `<meta charset="utf-8">` tag, or a `<meta
  http-equiv="content-type">` tag whose content names
  `charset=utf-8`. Either form passes; a `content-type` tag with
  no charset in it is not a declaration.
- The declaration must sit in the first 1024 bytes of the file
  — the browser reads only that far when it looks for one — so a
  tag that comes later is reported as too late, and a tag after
  `</head>` is reported as outside the head.
- A page needs exactly one declaration. A second one is
  reported, and two that disagree — say `utf-8` and
  `iso-8859-1` — are reported as a conflict.
- A UTF-8 byte-order mark at the start of the file also counts
  as a declaration, because the browser reads it first — but it
  is not a substitute for the tag, and a wrong tag is still
  reported even when a mark is present.
- A charset tag inside an HTML comment does not count — a
  commented-out tag is the same as no tag.
- A file given directly on the command line is always checked,
  whatever its name. A folder is walked for `.html` and `.htm`
  files only, recursively by default (`--no-recursive` stops at
  the top level). `.git` folders are never walked, and directory
  links are never followed.
- `--json` prints the result as JSON, and `--stdin` checks one
  HTML document read from standard input.

## Who it is for

Anyone who ships pages with names, places, or emoji in them —
which is every site owner. One missing line per page is the
difference between text that reads as written and text that
comes out garbled, and nothing in a normal build flags it. This
is the gate that stops it at the pull request.

## What it does NOT do

- It does not check the viewport tag, the `lang` attribute, the
  title, or anything else in the page. The viewport tag is repo
  #97, html-viewport-checker-cli; `lang` is repo #87,
  html-lang-checker-cli; the title is repo #50,
  html-title-checker-cli — the charset is this repo's different
  check on the same pages.
- It does not convert a file to UTF-8, and it does not check the
  encoding of the file's bytes beyond reading them as UTF-8. A
  file saved in another encoding is reported as unreadable, not
  converted.
- It never rewrites a file, and it never touches the network.

## How this differs

- A fresh search of GitHub on Nov 14, 2026 found 0 results for
  `"html-charset-checker-cli"` and 1 result for `html charset
  checker` — ryadav8052/Battery, 0 stars, an HTML file that
  merely contains a charset tag. It is not a checker at all.
- No rival checks charsets in local files. Repo #9,
  seo-meta-audit-skill, checks title, meta description,
  canonical, Open Graph, and H1 on one page — it does not check
  the charset, and it is a skill, not a CLI gate. Repo #87,
  html-lang-checker-cli, checks `lang` — the charset is a
  different check on the same pages.
- So the narrow slice stands: the charset only, per-file and
  per-line reporting, and a CI exit code.

## Install

```sh
git clone https://github.com/haiderstudio/html-charset-checker-cli.git
cd html-charset-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one page:

```sh
python3 src/html_charset_checker.py page.html
```

A page that declares UTF-8 early in the head passes:

```sh
$ python3 src/html_charset_checker.py examples/good.html
OK — 1 file(s) checked, every file declares UTF-8.
```

A page with no charset fails, with the file and the line:

```sh
$ python3 src/html_charset_checker.py examples/bad.html
FAIL examples/bad.html: missing charset — add <meta charset="utf-8"> at the top of <head> (line 1)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

A page that declares another charset fails on the value:

```sh
$ python3 src/html_charset_checker.py examples/edge.html
FAIL examples/edge.html: declares charset iso-8859-1, not UTF-8 — change it to utf-8 (line 4)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

A page that declares UTF-8 too late fails on the position:

```sh
$ python3 src/html_charset_checker.py examples/late.html
FAIL examples/late.html: charset is declared 1154 bytes into the file — it must be in the first 1024 bytes, move it to the top of <head> (line 5)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a whole folder (`.html` and `.htm` files only):

```sh
$ python3 src/html_charset_checker.py examples/
FAIL examples/bad.html: missing charset — add <meta charset="utf-8"> at the top of <head> (line 1)
FAIL examples/edge.html: declares charset iso-8859-1, not UTF-8 — change it to utf-8 (line 4)
FAIL examples/late.html: charset is declared 1154 bytes into the file — it must be in the first 1024 bytes, move it to the top of <head> (line 5)
Checked 4 file(s), 3 problem(s) in 3 file(s).
```

Check one document from standard input — the older
`http-equiv` form passes too, when it names UTF-8:

```sh
$ printf '<!DOCTYPE html>\n<html><head>\n<meta http-equiv="content-type" content="text/html; charset=utf-8">\n<title>t</title></head><body></body></html>\n' | python3 src/html_charset_checker.py --stdin
OK — 1 file(s) checked, every file declares UTF-8.
```

Machine-readable output:

```sh
$ python3 src/html_charset_checker.py --json examples/bad.html
{
  "files_checked": 1,
  "problems": [
    {
      "file": "examples/bad.html",
      "line": 1,
      "kind": "missing",
      "message": "missing charset — add <meta charset=\"utf-8\"> at the top of <head>"
    }
  ],
  "ok": false
}
```

Exit codes: 0 when every file declares UTF-8 early in the
head, 1 when any file fails or a file cannot be read, 2 for a
usage error (a missing path, a bad flag, or no HTML files
found).

## Examples

Two declarations that disagree are a conflict, not just a
duplicate — the browser can only honour one:

```sh
$ printf '<!DOCTYPE html>\n<html><head>\n<meta charset="utf-8">\n<meta charset="iso-8859-1">\n<title>t</title></head><body></body></html>\n' | python3 src/html_charset_checker.py --stdin
FAIL <stdin>: declares charset iso-8859-1, not UTF-8 — change it to utf-8 (line 4)
FAIL <stdin>: declares charset iso-8859-1 but the page already declares utf-8 — keep one declaration only (line 4)
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_html_charset_checker.py
```

The tests cover the declaration forms (a `<meta charset>`
tag, the `http-equiv` form, `utf8` without the hyphen, an
uppercase `UTF-8`, a `content-type` tag with no charset, a
`content-type` tag with no content, a charset tag with no
value, a charset tag inside a comment), the document check (a
good page, a missing charset, an empty document, a non-UTF-8
value, a declaration past 1024 bytes, a declaration just
inside 1024 bytes, a declaration after `</head>`, two matching
declarations, two conflicting declarations, a byte-order mark
alone, a byte-order mark with a wrong tag, a page with no
`<head>` at all, uppercase tags and attributes, unquoted
attributes, a non-charset meta left alone), the file check (a
clean file, a bad file, a missing file, a non-UTF-8 file, a
file with a byte-order mark, input files left unchanged),
folder walking (direct files, `.html` and `.htm` only, nested
folders, `.git` skipped, `--no-recursive`, `--exclude`,
missing paths, uppercase extensions), the CLI (exit 0/1/2,
folder summary counts, `--json` output, `--stdin`, bad flags,
missing paths, empty folders, `--version`, a non-UTF-8 file,
the tool run from another folder, the tool run under a fake
HOME), the bundled examples (sample output compared
byte-for-byte against a fresh run, and the README-quoted outputs
checked against it), and hygiene checks (no placeholder text, no
absolute paths, no real secrets, stdlib imports only, no network
use in the source, `.env` first in `.gitignore`, CI file runs
the test file, README names the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
declaring a page's charset is not new, and UTF-8 is the
encoding every guide recommends — but no existing tool checks
charset declarations in local files as a tested command-line
gate, as the search above shows — and every line of code here
is original, built on nothing but Python's standard library.
