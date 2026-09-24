# Template: clean-resume

- **Type:** CV
- **Source extension:** .docx
- **Engine/toolchain:** Microsoft Word (COM) — `tools/docx_to_pdf.ps1`. LibreOffice (`soffice --headless --convert-to pdf`) is a documented cross-platform fallback, not verified in this repo.
- **Editing method:** edit-in-place — Claude edits this document's existing XML runs per `.claude/skills/job-application-assistant/10-docx-editing.md`. Never regenerate it from scratch, never use `python-docx` or any library that re-renders styles.
- **Page limit:** 2 page(s)
- **Fonts:** system default document font (Times New Roman-family serif body, as embedded in the source `.docx`'s `styles.xml`) — no bundled fonts, relies on the fonts already installed with Microsoft Office.
- **Class/packages:** standard OOXML (`word/document.xml` + `styles.xml`), no external dependencies.
- **Calibrated CPL:** 117 characters/line (body font/size, this template's margins) — pass this to `tools/docx_edit.py`'s `est_lines()`/`last_line_word_count()` to predict wrapping and widows before rendering, instead of iterating blind. Recalibrate with `calibrate_cpl()` only if this template's font, size, or margins change.

## Compile command

    powershell -File tools/docx_to_pdf.ps1 <file>.docx <file>.pdf

## Style rules

- Plain single-column layout, no sidebars, no icon glyphs in the header — name centered at the top, then a centered contact line (location | phone | email | LinkedIn).
- Section headings (PROFESSIONAL SUMMARY, KEY ACHIEVEMENTS, EXPERIENCE, EDUCATION, CERTIFICATIONS & AFFILIATIONS, SKILLS, LANGUAGES) are bold, dark blue, each followed by a horizontal rule. Keep this exact section order and these exact heading labels — do not reorder, rename, or add new top-level sections.
- Bullets use a literal `•` character typed into the run text (not Word's native bullet/numbering feature) — when cloning a bullet paragraph for a new item, clone an existing bullet `<w:p>` so the `•` and its spacing come along automatically.
- Job/education entries: `[Title] - [Company/Institution], [Location] | [Start Date] – [End Date]` on one bold line, bullets underneath.
- Certifications, Skills, and Languages sections are single-line, pipe-separated (`|`) lists — not bulleted.

## Known pitfalls

- The source document's text runs are split at irregular points inside words and sentences (an artifact of the original authoring, not something this template introduced) — when editing a paragraph's content, replace text across *all* of that paragraph's runs, or collapse to the first run and blank the rest, rather than assuming one run holds one whole sentence.
- The `&` in "CERTIFICATIONS & AFFILIATIONS" is stored as the XML entity `&amp;` in `word/document.xml` — unescape XML entities before doing any text comparison/matching against this document's content, or a literal string match against `&` will silently fail.
- No page-break run has been needed yet at 2 pages of placeholder content; if a real tailored version needs one, see the page-break recipe in `10-docx-editing.md`.
- Every entry heading (`[JOB TITLE N] - [Company N]...` and the Education heading) carries `<w:keepNext/>` so Word never orphans a heading alone at the bottom of a page with its bullets pushed to the next one. This was added after a real tailoring pass hit exactly that failure and content trims alone did not fix it (trimming changes wrapped *line* count, not which paragraph the page break falls between). Any new entry-heading paragraph cloned for a 5th or later role should clone from an existing heading paragraph (not the placeholder bullet paragraphs) so it inherits `keepNext` automatically.
