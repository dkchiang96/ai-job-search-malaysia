#!/usr/bin/env python3
"""Token-efficient DOCX editing for Track B (job-application-assistant/10-docx-editing.md).

A .docx is a zip archive; word/document.xml holds the body. This module edits
that XML directly by rebuilding whole <w:p> paragraph blocks from their own
parts (never python-docx, never any library that re-renders styles) so every
paragraph keeps its exact existing style reference.

Why this file exists: printing raw document.xml or full pdftotext dumps into
a model's context burns thousands of tokens per look. The fix is a compact
paragraph index (`Docx.index()`) instead of the raw XML, and a compact
verification report (`report()`) instead of a full-page text dump. See
10-docx-editing.md's "Token-efficient workflow" section for the intended
call sequence.

Typical usage from a short tailoring script:

    import sys
    sys.path.insert(0, "tools")
    from docx_edit import Docx, report

    d = Docx("documents/cv/Base_Resume.docx", workdir=SCRATCH)
    print(d.index())                      # ~1-2k tokens, not ~18k

    # ... decide edits by paragraph index or a unique text marker ...
    d.apply(
        edits={4: "New profile statement...", "Built the monthly KPI": "..."},
        deletes=["Coordinated the office move"],
    )
    pdf = d.render(out_docx="cv/main_acme_ops.docx", out_pdf="cv/main_acme_ops.pdf")
    report(pdf)                            # compact: page count + widows only

Predicting line wrap locally (calibrate CPL once per template, see
`calibrate_cpl`) avoids blind render-and-check loops for content that merely
needs to cross a wrap threshold, not just get shorter.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

BULLET = "•"
DOC_PATH = "word/document.xml"

_PARA_RE = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_TEXT_RE = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.S)
_RUN_RE = re.compile(r"<w:r[ >].*?</w:r>", re.S)
_PPR_RE = re.compile(r"<w:pPr>.*?</w:pPr>", re.S)
_RPR_RE = re.compile(r"<w:rPr>.*?</w:rPr>", re.S)
_OPEN_TAG_RE = re.compile(r"(<w:p[ >][^>]*>)")


def esc(text: str) -> str:
    """Escape &, <, > in that order. Skipping this corrupts the docx silently."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para_text(pxml: str) -> str:
    return "".join(_TEXT_RE.findall(pxml))


def rebuild_paragraph(pxml: str, newtext: str) -> str:
    """Rebuild one <w:p> block with new text, preserving <w:pPr> and a cloned <w:rPr>.

    Word fragments a sentence across many runs; a target string can span a run
    boundary, so this collapses all runs into one rather than doing a substring
    replace inside a single <w:t>. Only safe because the destination run's
    <w:rPr> is what every collapsed run shared in practice for body/bullet
    paragraphs. A paragraph that deliberately mixes bold/italic mid-line (rare
    outside role headings, which this function is not meant to rewrite) should
    be left alone or edited run-by-run instead.
    """
    ppr_m = _PPR_RE.search(pxml)
    ppr = ppr_m.group(0) if ppr_m else ""
    open_tag = _OPEN_TAG_RE.match(pxml).group(1)

    runs = _RUN_RE.findall(pxml)

    # Keep a leading bullet-glyph run (and a lone space run after it) untouched
    # so the bullet's own formatting never gets collapsed into the text run.
    keep = []
    for r in runs:
        t = "".join(_TEXT_RE.findall(r))
        if t.strip() == BULLET or t == " ":
            keep.append(r)
        else:
            break

    rpr = ""
    if runs:
        rpr_m = _RPR_RE.search(runs[-1])
        rpr = rpr_m.group(0) if rpr_m else ""

    # Gotcha: some paragraphs put the bullet glyph inside the same run as the
    # text rather than its own run. If we didn't keep a separate bullet run
    # but the original text started with one, re-add it or the bullet vanishes.
    if not keep and para_text(pxml).lstrip().startswith(BULLET):
        newtext = BULLET + " " + newtext

    newrun = f'<w:r>{rpr}<w:t xml:space="preserve">{esc(newtext)}</w:t></w:r>'
    return open_tag + ppr + "".join(keep) + newrun + "</w:p>"


def add_pagebreak(pxml: str) -> str:
    """Insert a page-break run as the first run after <w:pPr>. Content, not styling.

    The one permitted structural insert (10-docx-editing.md). Never touches
    widow/orphan or keep-with-next flags, which live in <w:pPr> and stay frozen.
    """
    ppr_m = _PPR_RE.search(pxml)
    if not ppr_m:
        raise ValueError("paragraph has no <w:pPr> to anchor a page break after")
    ppr = ppr_m.group(0)
    return pxml.replace(ppr, ppr + '<w:r><w:br w:type="page"/></w:r>', 1)


def add_keep_next(pxml: str) -> str:
    """Add <w:keepNext/> to a paragraph's <w:pPr> so Word never orphans it from
    the paragraph immediately after it (e.g. an entry heading from its first
    bullet). Idempotent - a no-op if already present."""
    if "<w:keepNext/>" in pxml:
        return pxml
    ppr_m = _PPR_RE.search(pxml)
    if not ppr_m:
        raise ValueError("paragraph has no <w:pPr> to add keepNext to")
    ppr = ppr_m.group(0)
    new_ppr = ppr.replace("<w:pPr>", "<w:pPr><w:keepNext/>", 1)
    return pxml.replace(ppr, new_ppr, 1)


class Docx:
    """An in-memory, index-addressable view of a .docx's word/document.xml.

    Never edits the source file in place; always copies into `workdir` first.
    Never shells out to unzip/zip - uses zipfile so every other part (styles.xml,
    numbering.xml, fontTable.xml, theme/) rides through byte-identical without
    ever being opened.
    """

    def __init__(self, src, workdir):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.work_path = self.workdir / "work.docx"
        shutil.copy(src, self.work_path)
        self._load()

    def _load(self):
        with zipfile.ZipFile(self.work_path) as z:
            self._entries = {name: z.read(name) for name in z.namelist()}
        if DOC_PATH not in self._entries:
            raise ValueError(f"{self.work_path} has no {DOC_PATH} - not a valid docx")
        self.xml = self._entries[DOC_PATH].decode("utf-8")
        self._reindex()

    def _reindex(self):
        self.spans = [(m.start(), m.end()) for m in _PARA_RE.finditer(self.xml)]

    def text(self, i: int) -> str:
        s, e = self.spans[i]
        return para_text(self.xml[s:e])

    def index(self, width: int = 120) -> str:
        """Compact paragraph listing to print to the model instead of raw XML.

        ~1,200 tokens for a 54-paragraph resume, vs. ~18,000 for the raw XML.
        """
        return "\n".join(f"{i} | {self.text(i)[:width]}" for i in range(len(self.spans)))

    def find(self, marker: str) -> int:
        """Paragraph index whose text contains `marker`. Raises unless exactly one match.

        Prefer this over a raw integer when edits might add/delete paragraphs
        first in the same call - text markers survive re-indexing, integers
        computed against a stale index silently target the wrong paragraph
        (this bit a real session: two placeholder paragraphs shared the same
        w:rsid/paraId, an integer-position guess landed on the wrong one).
        """
        hits = [i for i in range(len(self.spans)) if marker in self.text(i)]
        if len(hits) != 1:
            raise KeyError(f"marker {marker!r} matched {len(hits)} paragraph(s), expected exactly 1")
        return hits[0]

    def _resolve(self, key) -> int:
        return key if isinstance(key, int) else self.find(key)

    def apply(self, edits=None, deletes=(), pagebreaks=(), keep_next=()):
        """Apply a batch of edits in one call.

        edits: {index_or_marker: new_text} - rewrite a paragraph's text
        deletes: [index_or_marker, ...] - remove a whole paragraph
        pagebreaks: [index_or_marker, ...] - force this paragraph to start a new page
        keep_next: [index_or_marker, ...] - glue this paragraph to the next one

        Every op is resolved to a paragraph index against the CURRENT index
        before any XML is touched, then applied in descending span order so
        earlier spans stay valid as later ones shift the string.
        """
        edits = edits or {}
        ops = []
        for key, newtext in edits.items():
            ops.append(("edit", self._resolve(key), newtext))
        for key in deletes:
            ops.append(("delete", self._resolve(key), None))
        for key in pagebreaks:
            ops.append(("pagebreak", self._resolve(key), None))
        for key in keep_next:
            ops.append(("keep_next", self._resolve(key), None))

        ops.sort(key=lambda o: o[1], reverse=True)

        for kind, idx, val in ops:
            s, e = self.spans[idx]
            if kind == "edit":
                self.xml = self.xml[:s] + rebuild_paragraph(self.xml[s:e], val) + self.xml[e:]
            elif kind == "delete":
                self.xml = self.xml[:s] + self.xml[e:]
            elif kind == "pagebreak":
                self.xml = self.xml[:s] + add_pagebreak(self.xml[s:e]) + self.xml[e:]
            elif kind == "keep_next":
                self.xml = self.xml[:s] + add_keep_next(self.xml[s:e]) + self.xml[e:]
            self._reindex()

        self._entries[DOC_PATH] = self.xml.encode("utf-8")

    def save(self, out_path=None) -> Path:
        out_path = Path(out_path) if out_path else self.workdir / "out.docx"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in self._entries.items():
                z.writestr(name, data)
        return out_path

    def render(self, out_docx=None, out_pdf=None, converter: str = "word") -> Path:
        """Save then convert to PDF. converter: 'word' (Windows/Word COM) or 'soffice'."""
        out_docx = self.save(out_docx)
        out_pdf = Path(out_pdf) if out_pdf else out_docx.with_suffix(".pdf")
        if converter == "word":
            script = Path(__file__).parent / "docx_to_pdf.ps1"
            # -ExecutionPolicy Bypass: the default policy blocks script loading
            # for a plain `powershell -File` subprocess call (unlike the harness's
            # own PowerShell tool, which sets this itself).
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 str(out_docx), str(out_pdf)],
                check=True, capture_output=True, text=True,
            )
        elif converter == "soffice":
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf",
                 "--outdir", str(out_pdf.parent), str(out_docx)],
                check=True, capture_output=True, text=True,
            )
        else:
            raise ValueError(f"unknown converter: {converter!r}")
        if not out_pdf.exists():
            raise RuntimeError(f"conversion did not produce {out_pdf}")
        return out_pdf


# ---------------------------------------------------------------------------
# Verification: compact report instead of full pdftotext dumps
# ---------------------------------------------------------------------------

def page_count(pdf_path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    if not m:
        raise ValueError("pdfinfo output did not contain a page count")
    return int(m.group(1))


def page_texts(pdf_path) -> list[str]:
    """One string per page. pdftotext trails every page (including the last)
    with a form feed, so a naive split leaves a phantom empty final entry -
    strip trailing empty entries so len(page_texts(...)) == pdfinfo's page count."""
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    pages = out.split("\f")
    while pages and not pages[-1].strip():
        pages.pop()
    return pages


def find_widows(text: str) -> list[tuple[str, str]]:
    """Bulleted groups whose wrapped final line carries <=2 words. (heading, last_line) pairs.

    Groups on indentation, not just the bullet glyph: a bullet start ("  • ...")
    or a flush-left line (a role/section heading, no leading whitespace) both
    open a new group; only a line with MORE leading whitespace than that is a
    wrapped continuation of the current group. Treating every non-bullet line
    as a continuation (bullet-only grouping) merges a heading with the next
    bullet's lines into one false multi-line group - the exact false positive
    this function used to produce.
    """
    groups, cur = [], []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line.strip():
            if cur:
                groups.append(cur)
                cur = []
            continue
        stripped = line.lstrip()
        is_new_block = stripped.startswith(BULLET) or line == stripped  # bullet start or flush-left heading
        if is_new_block:
            if cur:
                groups.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        groups.append(cur)

    widows = []
    for g in groups:
        if len(g) > 1 and g[0].lstrip().startswith(BULLET) and len(g[-1].split()) <= 2:
            widows.append((g[0].strip()[:60], g[-1].strip()))
    return widows


def find_orphan_headings(text: str, heading_markers=()) -> list[str]:
    """Flag a heading line that is the LAST non-blank line of a page (its content
    would spill to the next page). Pass the known role/section heading substrings
    from this document if you have them; otherwise this only checks the very
    last line, which is enough to catch the common case."""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return []
    last = lines[-1].strip()
    if heading_markers:
        if any(marker in last for marker in heading_markers):
            return [last]
        return []
    # Heuristic without known markers: a short line with no bullet and no
    # trailing period reads like a heading, not a wrapped sentence.
    if not last.startswith(BULLET) and not last.endswith(".") and len(last) < 90:
        return [last]
    return []


def report(pdf_path, expected_pages: int | None = None, heading_markers=()) -> str:
    """Print and return a compact verification report: page count, per-page
    non-blank line counts, widow lines, and a possible orphaned trailing heading.
    Costs ~150 tokens vs. ~2,500 for a full pdftotext dump."""
    pages = page_texts(pdf_path)
    n_pages = page_count(pdf_path)
    lines = [f"pages: {n_pages}" + (" (expected {})".format(expected_pages) if expected_pages else "")]
    if expected_pages is not None and n_pages != expected_pages:
        lines.append(f"  FAIL: expected {expected_pages} page(s)")
    for i, p in enumerate(pages, 1):
        if not p.strip():
            continue
        nonblank = len([l for l in p.split("\n") if l.strip()])
        lines.append(f"  page {i}: {nonblank} non-blank lines")
        for head, last in find_widows(p):
            lines.append(f'  WIDOW page {i}: "{head}" -> "{last}"')
        if i < len(pages):
            for orphan in find_orphan_headings(p, heading_markers):
                lines.append(f'  POSSIBLE ORPHAN HEADING page {i} (last line): "{orphan}"')
    text = "\n".join(lines)
    print(text)
    return text


# ---------------------------------------------------------------------------
# Local line-wrap prediction: avoid blind render-and-check loops
# ---------------------------------------------------------------------------

def est_lines(text: str, cpl: float) -> int:
    """Greedy word-wrap line count at `cpl` characters per line. Approximate
    (proportional font), accurate to about +/-1 line - keep a final render as
    the ground-truth check, never skip it."""
    n, cur = 1, 0
    for w in text.split():
        add = len(w) + (1 if cur else 0)
        if cur + add > cpl:
            n += 1
            cur = len(w)
        else:
            cur += add
    return n


def last_line_word_count(text: str, cpl: float) -> int:
    """Word count of the final wrapped line, for widow prediction before rendering.
    Returns 99 (never a widow) for single-line text."""
    words = text.split()
    lines, cur = [[]], 0
    for w in words:
        add = len(w) + (1 if cur else 0)
        if cur + add > cpl:
            lines.append([w])
            cur = len(w)
        else:
            lines[-1].append(w)
            cur += add
    return len(lines[-1]) if len(lines) > 1 else 99


def calibrate_cpl(pdf_path) -> float:
    """Derive a characters-per-line constant from an already-rendered PDF: the
    90th percentile of non-final line lengths across all pages. Run once per
    template (font/size/margins), store the result (e.g. in that template's
    TEMPLATE.md), and reuse it - only recalibrate if the template's font,
    size, or margins change."""
    pages = page_texts(pdf_path)
    lengths = []
    for p in pages:
        para_lines = [l for l in p.split("\n") if l.strip()]
        for i, line in enumerate(para_lines):
            is_last_in_para = (i == len(para_lines) - 1) or not para_lines[i + 1].strip()
            if not is_last_in_para:
                lengths.append(len(line.rstrip()))
    if not lengths:
        raise ValueError("no wrapped lines found to calibrate against")
    lengths.sort()
    idx = int(len(lengths) * 0.9)
    return float(lengths[min(idx, len(lengths) - 1)])


# ---------------------------------------------------------------------------
# Minimal CLI for the two standalone-useful operations
# ---------------------------------------------------------------------------

def _main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: docx_edit.py index <file.docx>\n"
              "       docx_edit.py report <file.pdf> [expected_pages]\n"
              "       docx_edit.py calibrate <file.pdf>", file=sys.stderr)
        return 2
    cmd, path = argv[0], argv[1]
    if cmd == "index":
        d = Docx(path, workdir=Path(path).parent / "_docx_edit_tmp")
        print(d.index())
    elif cmd == "report":
        expected = int(argv[2]) if len(argv) > 2 else None
        report(path, expected_pages=expected)
    elif cmd == "calibrate":
        print(calibrate_cpl(path))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
