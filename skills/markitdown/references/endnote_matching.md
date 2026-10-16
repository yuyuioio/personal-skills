# EndNote matching for local research PDFs

When converting, reading, or summarizing supplied scholarly PDFs, automatically preserve a matching record for each PDF. Do not apply this to unrelated PDF operations such as form filling or rotation. An extracted full-text Markdown is not a completed literature summary.

For summaries, deliver a Chinese Markdown file plus a same-paper `.match.json`. For conversion only, deliver extracted Markdown plus the matching record and leave summary status pending. Preserve:

- The absolute original PDF path, filename, full SHA-256, and page count.
- The primary article's DOI and its status (`missing`, `candidate`, `unresolved`, `verified`), all extracted DOI candidates with page/context evidence, and verification sources. Never generate an invented DOI or select the first reference-list DOI. A single candidate still needs identity checking.
- Actual title, authors, year and journal; unknown fields remain empty. Filename guesses are not verified bibliographic facts.
- Active EndNote `.enl` path and library-scoped record number when observed, candidate records/matching reasons and ambiguity status. Leave them empty if unavailable; an `.enlx` backup does not establish the active library.
- Final Markdown path and hash, summary status, and separate EndNote writeback status.

Use the `paper_bundle.py` helper in the sibling `endnote-summary` skill's scripts directory and its matching contract when available. Locate its directory from skill discovery, not a hardcoded machine path. Run `prepare` for each PDF; after identifying the primary DOI, pass evidence-backed bibliography JSON and regenerate with `--overwrite`. EndNote-exported XML and the active library path can be supplied for read-only matching. Read that skill's instructions before packaging a summary.

If the helper is unavailable, create an equivalent JSON sidecar with empty unknown values and no automatic selection. Do not delay a requested summary just because the user has no EndNote export. For a multi-paper review, keep per-PDF records separate from the aggregate review; avoid mixing citations' DOI identities with the source PDF identity.

The future writeback target is an existing EndNote record's File Attachments (Markdown file) and optionally Research Notes (short plain text). Never reimport RIS/XML to pretend to update the original record, modify the EndNote database directly, or claim an attachment was added without live verification. `matched` is distinct from `attached`. Skills execute when called; they do not persistently monitor folders.
