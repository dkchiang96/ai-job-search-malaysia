"""tools/docx_edit.py against the shipped clean-resume template: edits keep the
paragraph's formatting, entities are escaped, structural inserts work, and the
shipped templates carry no personal metadata."""

import html
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import docx_edit as dx  # noqa: E402

CV = ROOT / "templates" / "cv" / "clean-resume" / "template.docx"
COVER = ROOT / "templates" / "cover_letters" / "clean-resume" / "template.docx"


def _para(d, i: int) -> str:
    s, e = d.spans[i]
    return d.xml[s:e]


def _ppr(pxml: str) -> str:
    m = re.search(r"<w:pPr>.*?</w:pPr>", pxml, re.S)
    return m.group(0) if m else ""


class TestEditing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = dx.Docx(CV, workdir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_is_compact_and_numbered(self):
        idx = self.d.index()
        self.assertIn("[YOUR NAME]", idx)
        self.assertIn("[JOB TITLE 4]", idx)
        self.assertLess(len(idx), 6000)

    def test_edit_keeps_paragraph_properties_and_escapes(self):
        i = self.d.find("[3-5 sentence professional summary")
        before = _ppr(_para(self.d, i))
        self.d.apply(edits={i: "Operations lead: R&D <-> ops, 6 years in KL & Selangor"})
        # text() returns the stored (XML-escaped) form - unescape before comparing, as TEMPLATE.md says
        self.assertEqual(html.unescape(self.d.text(i)), "Operations lead: R&D <-> ops, 6 years in KL & Selangor")
        self.assertEqual(_ppr(_para(self.d, i)), before)
        self.assertIn("R&amp;D &lt;-&gt; ops", _para(self.d, i))

    def test_delete_and_structural_inserts(self):
        n = len(self.d.spans)
        heading = self.d.find("[JOB TITLE 2]")
        self.d.apply(deletes=[heading + 1], keep_next=[heading], pagebreaks=["[JOB TITLE 3]"])
        self.assertEqual(len(self.d.spans), n - 1)
        self.assertIn("<w:keepNext/>", _para(self.d, self.d.find("[JOB TITLE 2]")))
        self.assertIn('w:type="page"', _para(self.d, self.d.find("[JOB TITLE 3]")))
        out = self.d.save(Path(self.tmp.name) / "out.docx")
        with zipfile.ZipFile(out) as z:
            self.assertIn("word/document.xml", z.namelist())
            self.assertIsNone(z.testzip())

    def test_original_file_is_never_modified(self):
        before = CV.read_bytes()
        self.d.apply(edits={0: "Someone Else"})
        self.d.save(Path(self.tmp.name) / "out.docx")
        self.assertEqual(CV.read_bytes(), before)


class TestWidowHelpers(unittest.TestCase):
    def test_find_widows_flags_short_last_lines(self):
        text = "• Reduced month-end close from ten days to four by automating\n  reconciliations.\n\n• Short bullet"
        widows = dx.find_widows(text)
        self.assertEqual(len(widows), 1)


class TestShippedTemplatesArePersonalDataFree(unittest.TestCase):
    def test_no_author_metadata_or_revision_ids(self):
        for path in (CV, COVER):
            with zipfile.ZipFile(path) as z:
                core = z.read("docProps/core.xml").decode("utf-8")
                self.assertIn("<cp:lastModifiedBy>ai-job-search-malaysia</cp:lastModifiedBy>", core, path)
                blob = b"".join(z.read(n) for n in z.namelist())
                self.assertNotRegex(blob, rb'w:rsid\w*="', path)
                text = z.read("word/document.xml").decode("utf-8")
                self.assertNotRegex(text, r"@(?!.*YOUR)[a-z0-9.-]+\.(com|my)", path)


if __name__ == "__main__":
    unittest.main()
