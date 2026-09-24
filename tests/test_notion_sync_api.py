"""tools/notion_sync_api.py against a fake Notion API: row selection, schema
planning, create/update, and the never-overwrite-a-human-status rule."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import notion_sync_api as ns  # noqa: E402

SEEN = {
    "a_lead": {"title": "Ops Lead", "company": "A", "status": "ranked", "rank_score": 78, "rank_verdict": "Apply",
               "rank_date": "2026-09-20", "portal": "hiredly-search", "url": "https://my.hiredly.com/jobs/a",
               "first_seen": "2026-09-19", "strengths": ["s1", "s2"], "gaps": ["g1"],
               "fit_breakdown": {"cs": 80.0, "dv": 70.0, "wp": 76.0}},
    "b_low": {"title": "Clerk", "company": "B", "status": "ranked", "rank_score": 30, "rank_date": "2026-09-20"},
    "c_new": {"title": "Ops", "company": "C", "status": "new"},
    "d_vetoed": {"title": "Ops US", "company": "D", "status": "ranked", "rank_score": 90, "location_verdict": "FAIL"},
    "e_old": {"title": "Ops Mgr", "company": "E", "status": "ranked", "rank_score": 60, "rank_date": "2026-08-01",
              "portal": "jobstreet-alert", "alert_name": "ops in KL"},
}


class FakeNotion:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.calls = []

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        if method == "POST" and path == "/pages":
            pid = f"p{len(self.pages) + 1}"
            self.pages[pid] = {"id": pid, "properties": body["properties"]}
            return {"id": pid}
        if method == "GET" and path.startswith("/pages/"):
            return self.pages[path.split("/")[-1]]
        if method == "PATCH" and path.startswith("/pages/"):
            return {}
        raise AssertionError((method, path))


class TestRows(unittest.TestCase):
    def test_selects_ranked_above_threshold_and_skips_vetoed(self):
        rows = ns.build_rows(SEEN)
        self.assertEqual([r["Key"] for r in rows], ["a_lead", "e_old"])
        self.assertEqual(rows[0]["Strengths"], "s1; s2")
        self.assertEqual((rows[0]["CS"], rows[0]["DV"]), (80.0, 70.0))

    def test_since_filter(self):
        self.assertEqual([r["Key"] for r in ns.build_rows(SEEN, since="2026-09-01")], ["a_lead"])

    def test_properties_shape(self):
        props = ns.to_properties(ns.build_rows(SEEN)[0], include_status=True)
        self.assertEqual(props["Status"], {"select": {"name": "New"}})
        self.assertEqual(props["Found on"], {"date": {"start": "2026-09-19"}})
        self.assertEqual(props["Posted"], {"date": None})
        self.assertNotIn("Status", ns.to_properties(ns.build_rows(SEEN)[0], include_status=False))


class TestSchema(unittest.TestCase):
    def test_plan_adds_missing_renames_title_never_removes(self):
        db = {"properties": {"Name": {"type": "title"}, "Score": {"type": "number"},
                             "Status": {"type": "select", "select": {"options": [{"name": "Applied"}, {"name": "Mine"}]}}}}
        patch = ns.plan_schema_patch(db)
        self.assertEqual(patch["Name"], {"name": "Title"})
        self.assertNotIn("Score", patch)
        self.assertEqual([o["name"] for o in patch["Status"]["select"]["options"]], ["Applied", "Mine", "New", "Shortlist", "Rejected"])


class TestSync(unittest.TestCase):
    def test_create_then_update_keeps_human_status(self):
        api, page_map = FakeNotion(), {}
        rows = ns.build_rows(SEEN)
        first = ns.sync(rows, "db", api, page_map)
        self.assertEqual((first["created"], first["updated"]), (2, 0))

        # The user moves one page to Shortlist and the other to Applied in Notion.
        api.pages[page_map["a_lead"]]["properties"]["Status"] = {"select": {"name": "Shortlist"}}
        api.pages[page_map["e_old"]]["properties"]["Status"] = {"select": {"name": "Applied"}}
        api.calls.clear()
        second = ns.sync(rows, "db", api, page_map)
        self.assertEqual((second["updated"], second["skipped_user_status"]), (1, 1))
        patch_body = next(b for m, p, b in api.calls if m == "PATCH")
        self.assertNotIn("Status", patch_body["properties"])

    def test_dry_run_calls_nothing_that_writes(self):
        api = FakeNotion()
        out = ns.sync(ns.build_rows(SEEN), "db", api, {}, dry_run=True)
        self.assertEqual(out["created"], 2)
        self.assertEqual(api.calls, [])

    def test_missing_credentials_is_a_clear_error(self):
        import os
        saved = {k: os.environ.pop(k, None) for k in ("NOTION_API_TOKEN", "NOTION_DATABASE_ID")}
        orig = ns.ENV_FILE
        ns.ENV_FILE = Path("does-not-exist.env")
        try:
            with self.assertRaisesRegex(ns.NotionError, "MISSING_CREDENTIALS"):
                ns.credentials()
        finally:
            ns.ENV_FILE = orig
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
