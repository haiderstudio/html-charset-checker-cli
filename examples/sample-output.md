Output of `sh examples/run-example.sh`, run from the repo root:

```
== examples/good.html ==
OK — 1 file(s) checked, every file declares UTF-8.

== examples/bad.html ==
FAIL examples/bad.html: missing charset — add <meta charset="utf-8"> at the top of <head> (line 1)
Checked 1 file(s), 1 problem(s) in 1 file(s).

== examples/edge.html ==
FAIL examples/edge.html: declares charset iso-8859-1, not UTF-8 — change it to utf-8 (line 4)
Checked 1 file(s), 1 problem(s) in 1 file(s).

== examples/late.html ==
FAIL examples/late.html: charset is declared 1154 bytes into the file — it must be in the first 1024 bytes, move it to the top of <head> (line 5)
Checked 1 file(s), 1 problem(s) in 1 file(s).

== examples/ : the whole folder ==
FAIL examples/bad.html: missing charset — add <meta charset="utf-8"> at the top of <head> (line 1)
FAIL examples/edge.html: declares charset iso-8859-1, not UTF-8 — change it to utf-8 (line 4)
FAIL examples/late.html: charset is declared 1154 bytes into the file — it must be in the first 1024 bytes, move it to the top of <head> (line 5)
Checked 4 file(s), 3 problem(s) in 3 file(s).
```
