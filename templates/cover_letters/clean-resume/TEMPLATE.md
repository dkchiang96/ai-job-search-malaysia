# Template: clean-resume

- **Type:** Cover letter
- **Source extension:** .docx
- **Engine/toolchain:** Microsoft Word (COM) — `tools/docx_to_pdf.ps1`. LibreOffice (`soffice --headless --convert-to pdf`) is a documented cross-platform fallback, not verified in this repo.
- **Editing method:** edit-in-place — fill the `[[BLOCK]]` placeholder paragraphs per `.claude/skills/job-application-assistant/10-docx-editing.md`. Never regenerate the document from scratch.
- **Page limit:** 1 page(s)
- **Fonts:** cloned directly from `templates/cv/clean-resume/template.docx` — same body font, size, and margins as the CV. Rebuild only if that CV template's header/style changes.
- **Class/packages:** standard OOXML, no external dependencies.
- **Calibrated CPL:** 117 characters/line — same value as `templates/cv/clean-resume/TEMPLATE.md` since fonts/margins are cloned identically. Recalibrate both together if either changes.

## Compile command

    powershell -File tools/docx_to_pdf.ps1 <file>.docx <file>.pdf

## Style rules

- Header (name + contact line) is cloned verbatim from `templates/cv/clean-resume/template.docx` — never edit it when filling a letter.
- Body follows the frozen block structure from `06-cover-letter-templates.md`: `[[DATE]]`, `[[RECIPIENT]]`, `[[GREETING]]`, `[[OPENING]]`, `[[BODY1]]`, `[[BODY2]]`, `[[CLOSING]]`, `[[SIGNOFF]]`, in that order, one paragraph each. Fill each placeholder in place; do not add, remove, or reorder blocks.
- ~250-350 words of body text, one page, per the tone contract and Writing Quality Rules in `06-cover-letter-templates.md`.

## Known pitfalls

- Built by cloning a body paragraph from the CV template (see `10-docx-editing.md`'s "Building the cover-letter template by cloning the resume") so every block paragraph already carries the correct body font/size — do not hand-write new paragraphs from scratch, clone an existing block instead if a ninth block is ever genuinely needed.
- Same XML-entity caveat as the CV template: unescape entities (e.g. `&amp;`) before doing text comparisons against this document's content.
