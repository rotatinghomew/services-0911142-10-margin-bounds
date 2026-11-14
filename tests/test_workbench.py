from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import unittest

from margin_bounds.domain import explore, validate
from margin_bounds.service import Workbench
from margin_bounds.server import make_server
from margin_bounds.storage import fingerprint


ROOT = Path(__file__).resolve().parents[1]


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "fixtures" / "data.json").read_text())
        self.selection = json.loads((ROOT / "product.json").read_text())["selection"]

    def test_fixture_is_valid_and_serializable(self):
        validate(self.data)
        view = explore(self.data, self.selection)
        self.assertTrue(view["rows"])
        self.assertTrue(view["notes"])
        json.dumps(view, allow_nan=False)

    def test_exploration_does_not_mutate_inputs(self):
        before = deepcopy(self.data)
        explore(self.data, self.selection)
        self.assertEqual(before, self.data)

    def test_missing_table_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            validate({})

    def test_incompatible_universe_is_kept_as_separate_evidence(self):
        validate(self.data)
        self.selection["release"] = "supplement"
        self.assertTrue(any(row["counting"] == "visits" for row in explore(self.data,self.selection)["rows"]))

    def test_unknown_axis_level_is_rejected(self):
        self.data["margins"][0]["coordinates"]["age"] = "unlisted"
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_duplicate_primary_identifier_rejected(self):
        table = 'releases'
        self.data[table].append(deepcopy(self.data[table][0]))
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_invalid_selection_rejected(self):
        self.selection['release'] = "not-available"
        with self.assertRaises(ValueError):
            explore(self.data,self.selection)

    def test_missing_required_field_rejected(self):
        table = 'releases'
        del self.data[table][0]['table']
        with self.assertRaises(ValueError):
            validate(self.data)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workbench = Workbench(ROOT, self.temporary.name)

    def test_content_addressed_import_is_idempotent(self):
        data = self.workbench.store.dataset(self.workbench.default_revision)
        uploaded = self.workbench.upload({"label": "再次导入", "data": data})
        self.assertEqual(uploaded["revision"], self.workbench.default_revision)
        self.assertEqual(len(self.workbench.store.datasets()), 1)

    def test_browser_numeric_roundtrip_preserves_fingerprint(self):
        self.assertEqual(fingerprint({"values": [1.0, 2, -0.0]}), fingerprint({"values": [1, 2.0, 0]}))

    def test_saved_description_keeps_original_dataset(self):
        saved = self.workbench.save({"title": "会议记录"})
        original = deepcopy(saved)
        data = self.workbench.store.dataset(self.workbench.default_revision)
        data["context_note"] = "新资料"
        newer = self.workbench.upload({"label": "新数据", "data": data})
        self.assertNotEqual(newer["revision"], saved["revision"])
        reopened = self.workbench.store.notebook(saved["id"])
        self.assertEqual(reopened, original)
        self.assertEqual(fingerprint(reopened["dataset"]), saved["revision"])

    def test_invalid_upload_leaves_no_dataset(self):
        with self.assertRaises(ValueError):
            self.workbench.upload({"label": "坏数据", "data": {}})
        self.assertEqual(len(self.workbench.store.datasets()), 1)

    def test_unknown_version_cannot_fall_back(self):
        with self.assertRaises(LookupError):
            self.workbench.inspect({"revision": "missing"})

    def test_blank_title_rejected(self):
        with self.assertRaises(ValueError):
            self.workbench.save({"title": " "})

    def test_saved_view_is_reproducible_after_restart(self):
        saved = self.workbench.save({"title": "重启核对"})
        restarted = Workbench(ROOT, self.temporary.name)
        self.assertEqual(saved, restarted.store.notebook(saved["id"]))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.server = make_server(ROOT, self.temporary.name, port=0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary.cleanup()

    def test_http_explore_save_and_read(self):
        with urlopen(self.base + "/health") as response:
            self.assertEqual(json.load(response)["status"], "ok")
        request = Request(self.base + "/api/notebooks", data=json.dumps({"title": "页面保存"}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            saved = json.load(response)
            self.assertEqual(response.status, 201)
        with urlopen(self.base + "/api/notebooks/" + str(saved["id"])) as response:
            self.assertEqual(saved, json.load(response))

    def test_bad_data_returns_client_error(self):
        request = Request(self.base + "/api/datasets", data=b'{"label":"bad","data":{}}',
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_unknown_route_is_not_static_file_access(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/../product.json")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
