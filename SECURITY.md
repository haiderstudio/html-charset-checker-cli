# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads HTML files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL: remote addresses are skipped, not opened.

It never edits a file it checks, and it never follows directory links when walking a folder.

If you find a case where the tool edits a file, follows a link out of the folder you pointed it at, or reports a pass for a page with no charset declaration, please open an issue describing the exact commands and input.
