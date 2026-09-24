---
framework_version: 1.1.0
---

# DOCX Editing, Conversion, and Verification (Track B)

How to tailor a CV or cover letter when the active template is the user's
own uploaded `.docx` ("Track B", chosen in `/setup-malaysia` and registered via
`/add-template`; the stock LaTeX templates are "Track A"). The rule
that makes this track work is simple and non-negotiable: **preserve
formatting exactly by editing the raw XML. Never use `python-docx` or any
library that re-renders styles** — those rebuild paragraph/run objects and
can silently drift fonts, spacing, or colors away from the source document.
The user chose this track specifically because they like their document's
exact look; regenerating it defeats the purpose.

## Why raw XML, not python-docx

A `.docx` is a zip archive. `word/document.xml` holds the visible content;
`styles.xml`, `fontTable.xml`, and the document's `sectPr` hold the
formatting. Editing the zip's XML directly means every paragraph and run
keeps its exact existing style reference — nothing is regenerated, so
nothing can drift. `python-docx` (or any similar library) builds new
paragraph/run objects through its own API, which does not guarantee
byte-identical style application even when it looks fine on screen.

## Editing method

**Use `tools/docx_edit.py` — do not hand-roll unzip/regex/rezip in an ad hoc
script.** It implements everything below (paragraph indexing, whole-block
rebuild, entity escaping, the page-break and keepNext inserts, rendering,
and compact verification) as one importable module, and it is the
token-efficient path — see "Token-efficient workflow" below for why that
matters and what it costs when skipped.

```python
import sys
sys.path.insert(0, "tools")
from docx_edit import Docx, report

d = Docx("documents/cv/<uploaded_filename>.docx", workdir=SCRATCHPAD)
print(d.index())   # paragraph index: "0 | [YOUR NAME]", "4 | [Professional summary...]", etc.
```

1. **`Docx(src, workdir)`** copies the source into `workdir` first — never
   edits the original — and loads `word/document.xml` via `zipfile`
   (no shelling out to `unzip`/`zip`, no loose `unz/` directory to clean up
   afterward).

2. **Read `d.index()`, not raw XML.** This is the whole point: a
   54-paragraph resume's `document.xml` is ~18,000 tokens; its index is
   ~1,200. **Never `cat`/`Read` `word/document.xml` directly** to decide
   what to edit — the index is what you look at.

3. **Operate on whole paragraph blocks**, addressed by index or by a unique
   text marker:
   ```python
   d.apply(
       edits={4: "New profile statement...", "Built the monthly KPI": "..."},
       deletes=["Coordinated the office move"],
   )
   ```
   `edits` rewrites a paragraph's text (rebuilding all its runs into one,
   see `rebuild_paragraph()` — this is what correctly handles a sentence
   split across several `<w:r>` runs, keeps the paragraph's `<w:pPr>`
   untouched, clones an existing `<w:rPr>` for the new run, and preserves a
   separate leading bullet-glyph run so the `•` never vanishes). `deletes`
   removes a whole `<w:p>...</w:p>` block. To add a bullet, clone an
   existing paragraph's XML rather than writing new XML from scratch — this
   inherits all formatting; `Docx` does not do this one for you since it
   depends on which paragraph you're cloning.

   **Prefer a text marker over an integer index whenever a batch mixes
   edits and deletes**, or whenever you're not certain the index is still
   current. An integer computed against a stale index can silently land on
   the wrong paragraph — this happened in practice: two placeholder
   paragraphs in a real template shared the same `w:rsid`/`paraId` pair,
   and a hand-written string-match accidentally rewrote the date line
   instead of the signoff line. `d.find(marker)` (which `apply()` calls
   automatically for a non-integer key) raises unless the marker matches
   **exactly one** paragraph, so a collision surfaces immediately instead
   of silently editing the wrong text.

4. **Never touch:** `<w:pPr>`, `<w:rPr>` (run properties), section
   properties `<w:sectPr>` (margins/page size), `styles.xml`, fonts, or
   spacing. Content only. `rebuild_paragraph()` enforces this by
   construction — it copies the existing `<w:pPr>` verbatim and only ever
   emits a new `<w:r>`.

   **Two permitted structural exceptions**, both available as `apply()`
   kwargs:
   - **Page break** (`pagebreaks=[...]`) — force a role to start clean on
     page 2 (see "Page-2 integrity, widow-line and page-fill checks" below). Inserts `<w:r><w:br w:type="page"/></w:r>` as the
     first run after that paragraph's `<w:pPr>`. Content, not styling.
   - **Keep-with-next** (`keep_next=[...]`) — add `<w:keepNext/>` to a
     paragraph's `<w:pPr>` so Word never separates it from the paragraph
     immediately after it. Use this on entry/role headings: without it, a
     heading can end up as the very last line of a page with all its
     bullets pushed to the next page — an orphan that pure content trimming
     will not fix, because trimming shortens *wrapped line count*, not
     which paragraph the page break falls between. If every entry heading
     in the document shares the same `<w:pPr>` signature, it is safe and
     usually correct to apply `keep_next` to all of them at once rather
     than reactively, one broken entry at a time.

5. **Entity escaping is automatic** (`esc()`, called inside
   `rebuild_paragraph()`) — `&` before `<` before `>`. If you ever build XML
   by hand instead of going through `Docx.apply()`, do the same in that
   order; a bare `&` (e.g. from "Sales & Marketing") is the most
   common way this track produces a `.docx` that Word reports as corrupt.

6. **`d.render(out_docx=..., out_pdf=...)`** saves (rezips via `zipfile`,
   no shell `zip` call) and converts in one call — see "DOCX → PDF
   conversion" below for the `converter` argument.

## Token-efficient workflow

The failure mode this section exists to prevent: burning most of a
session's token budget on things that don't need to be in context at all —
raw XML dumps, full-page `pdftotext` dumps every verification pass, and
blind render-and-check loops for a fix that doesn't actually change line
wrapping. Concretely, per iteration:

| Practice | Approx. cost | Use instead |
|---|---|---|
| Printing/reading raw `word/document.xml` | ~18,000 tok | `d.index()` — ~1,200 tok |
| Full `pdftotext -layout` dump per check | ~2,500 tok | `report(pdf)` — ~150 tok |
| Re-emitting the whole edit script inline every call | ~ hundreds of tok × N calls | One script file, edited incrementally |
| Blind render → check → trim → render → check | 2-5 extra render cycles | Predict wrapping locally first (below) |

**Verify with `report()`, not raw `pdftotext`:**
```python
from docx_edit import report
report(pdf_path, expected_pages=2)
# pages: 2 (expected 2)
#   page 1: 34 non-blank lines
#   page 2: 32 non-blank lines
# (or, if something's wrong:)
#   WIDOW page 1: "Reduced month-end close..." -> "days."
#   POSSIBLE ORPHAN HEADING page 1 (last line): "Operations Manager - Contoh Sdn Bhd, KL | Jan 2022 – Dec 2023"
```
Only fall back to a full `pdftotext -layout` dump of one specific page when
`report()` flags something and you need to see the surrounding context to
decide the fix — don't dump every page on every pass by default.

**Predict line wrapping before rendering, instead of iterating blind.**
Each registered Track B template records a calibrated characters-per-line
constant in its `TEMPLATE.md` (see `templates/cv/clean-resume/TEMPLATE.md`
for the reference example, CPL 117). Use it:
```python
from docx_edit import est_lines, last_line_word_count
CPL = 117  # from this template's TEMPLATE.md
est_lines(candidate_bullet_text, CPL)             # predicted line count
last_line_word_count(candidate_bullet_text, CPL)  # predicted widow risk
```
This is an approximation (proportional-font text; accurate to about ±1
line) — it tells you whether a trim is even long enough to cross a
wrap-line boundary *before* you spend a render-and-check cycle finding out
the hard way. A word-level trim that doesn't cross that boundary will
render identically to the untrimmed version — checking this locally first
is what avoids that wasted cycle. **Never skip the final render-and-check**
against the real PDF; the estimate is a filter for what to try, not a
substitute for verifying what shipped. If a template has no calibrated CPL
yet, derive one with `calibrate_cpl(pdf_path)` after any render and record
it in that template's `TEMPLATE.md` for reuse.

## DOCX → PDF conversion

`d.render(out_docx=..., out_pdf=..., converter="word")` (the `converter`
kwarg defaults to `"word"`) does this in one call. Two backends are
supported — use whichever is available; prefer Word if both are:

**Microsoft Word (Windows only), `converter="word"` (default), via
`tools/docx_to_pdf.ps1`:**
```powershell
powershell -File tools/docx_to_pdf.ps1 "<path>/out.docx" "<path>/out.pdf"
```
Wraps Word COM automation (`Documents.Open` → `SaveAs` PDF format → `Close`
→ `Quit`). Requires Microsoft Word installed and licensed on the machine
running Claude Code.

**LibreOffice (cross-platform), `converter="soffice"`, if installed:**
```bash
soffice --headless --convert-to pdf --outdir "<dir>" "<path>/out.docx"
```
Not verified in this repo's own environment (no LibreOffice installed
here) — if you hit this path, verify it produces a correct PDF before
trusting it, the same way `docx_to_pdf.ps1` was verified for Word.

If neither is available, stop and tell the user Track B needs one of the
two to produce a compiled PDF — content can still be tailored in the
`.docx`, but it cannot be verified or previewed without a converter.

## Verification loop

```python
from docx_edit import report
report(out_pdf, expected_pages=2)   # 2 for a CV, 1 for a cover letter
```

- **CV: must be exactly 2 pages.** **Cover letter: must be exactly 1 page.**
  If over, cut content only (see the cut order below) —
  never shrink margins, fonts, or spacing to force a fit.
- `report()` covers page count, the **widow-line check**, and a **possible
  orphan heading** flag (a heading sitting as the very last line of a page)
  in one compact call — pass this document's role/section heading text as
  `heading_markers=[...]` for a precise orphan check instead of the
  last-line heuristic. The rules it checks are defined in "Page-2
  integrity, widow-line and page-fill checks" below; fix by editing the
  `.docx` via `d.apply(...)` (content trim, or the `pagebreaks`/`keep_next`
  structural inserts above).
- **Page-fill** (page 2 of a CV should not ship noticeably under-filled) is
  the `page N: NN non-blank lines` line in the report — compare it to the
  other page(s) rather than reading a full dump.
- Loop the page-count check and these together until all pass
  simultaneously — they interact. A fix for one can reintroduce another
  (this happened in practice: fixing an orphaned heading by removing a
  bullet pushed the *next* heading into the same orphaned position — the
  general fix was `keep_next` on every entry heading at once, not another
  round of content trims).
- Sanity-check the docx opened without error during `render()` (it raises
  if Word/soffice fails) before presenting — no separate `unzip -t` step
  needed, since `Docx.save()` always writes a fresh, complete zip from the
  in-memory entry list.

## Page-2 integrity, widow-line and page-fill checks

These are stricter than "does it fit in 2 pages", and they catch defects a bare
page count misses. Run them on every Track B CV, every time.

- **Page-2 integrity: no role straddles the page break.** A role's heading
  and all its bullets land on one page. It fails if page 2 opens with 1-2
  dangling bullets whose heading is on page 1, or if a heading sits alone at
  the bottom of page 1. Fix by trimming content first so the role fits on
  page 1. Only if it can't, put `keep_next` on the heading, or a `pagebreaks`
  entry before it.
- **Cut order when over the page limit (protect the strongest evidence):**
  1. the least relevant bullets in the oldest roles
  2. generic bullets without a metric
  3. lower-relevance detail in mid-tenure roles

  Cut last, or never: quantified achievements, the most job-relevant role,
  the profile statement, the contact line and education.
- **Widow lines: no wrapped bullet ends on 1-2 words.** A last line holding
  only "monthly." wastes a line and reads as careless. Shorten the bullet so
  it ends flush, or lengthen it with real content (never padding) so the last
  line carries 3+ words. `report()` flags these as `WIDOW`.
- **Page fill: don't ship a half-empty page 2.** If page 2 is clearly short,
  restore a bullet you cut, or add claimable detail from
  `01-candidate-profile.md`. Never add filler.
- **Loop all four checks (page count included) until they pass together.**
  They interact, and fixing one often breaks another.

## Output

Present **both** the `.docx` and the `.pdf` — the `.docx` is the actual
editable output, the `.pdf` is the verification artifact and what most
employers expect to receive. `Docx(src, workdir=SCRATCHPAD)` keeps its
scratch copy (`work.docx`) inside the scratchpad only — there is no `unz/`
directory to clean up (edits happen on an in-memory zip entry list) — but
still delete the scratchpad workdir once the final `.docx`/`.pdf` are
copied to their real output paths; do not leave it in the repo.

## Building the cover-letter template by cloning the resume (one-time)

When a user registers a Track B CV template, the matching cover-letter
template is built **once**, immediately after, by cloning that same resume
document rather than starting from a blank letter:

1. Copy the registered CV's `template.docx`.
2. Keep `styles.xml`, fonts, `sectPr`, and the **name + contact-line
   paragraphs** verbatim — this is what makes the letter pixel-identical to
   the resume.
3. Delete the resume body (profile statement, achievements, experience,
   etc.). In its place, add paragraphs for: a date line, a recipient block,
   a greeting, and the frozen letter body blocks from
   `06-cover-letter-templates.md` (opening, body 1, body 2, closing,
   sign-off) — each cloned from an existing body paragraph in the source
   resume so it inherits the exact same font/size/spacing.
4. Rezip as `templates/cover_letters/<name>/template.docx`.
5. Rebuild only if the user changes their resume's header or style — not on
   every application.

## `/add-template` integration notes

- **Step 1 (source):** accept a `.docx` path alongside `.tex`/`.typ`.
- **Step 2 (compile command):** record `docx_to_pdf.ps1` (or the `soffice`
  command, whichever the user's machine supports) as the declared compile
  command in the template's manifest. Note the platform requirement
  explicitly in `TEMPLATE.md` so a later session on a different machine
  knows what it needs.
- **Step 3 (store template):** placeholder-ify the same way LaTeX/Typst
  templates already are — `[YOUR_NAME]`, `[YOUR_EMAIL]`, etc. for the header,
  and generic bracketed placeholders for example body content — so the
  stored `template.docx` is shareable and profile-agnostic like every other
  registered template. The user's own real content lives in
  `documents/cv/*.docx` (already gitignored), never in the shared
  `templates/` tree.
- **Step 4 (verify):** run the conversion + full verification loop above on
  dummy placeholder content before activating.
- **Step 5 (activate):** the existing `ACTIVE-TEMPLATE` managed block
  mechanism is unchanged — it names the template, its source extension
  (`.docx`), and the compile command. `/apply` Steps 2 and 5 branch on the
  source extension: `.tex`/`.typ` follow the existing generate-from-scratch
  authoring model, `.docx` follows the edit-in-place method in this file.
