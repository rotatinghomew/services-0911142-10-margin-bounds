from pathlib import Path
import importlib
import json
import sys
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrowserWorkflow(unittest.TestCase):
    def test_scope_freeze_raw_and_export(self):
        product = json.loads((ROOT / "product.json").read_text())
        package = json.loads((ROOT / "package.json").read_text())
        module = package["scripts"]["start"].split()[2]
        server_module = importlib.import_module(module + ".server")
        with tempfile.TemporaryDirectory() as state:
            server = server_module.make_server(ROOT, state, port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with sync_playwright() as runtime:
                    browser = runtime.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto("http://127.0.0.1:" + str(server.server_port), wait_until="networkidle")
                        page.locator("#status").filter(has_text="已更新描述").wait_for()
                        self.assertEqual(page.locator("h1").inner_text(), product["name"])
                        self.assertGreater(page.locator("#rows tr").count(), 0)
                        page.locator("#rows tr").first.click()
                        self.assertIn("{", page.locator("#details").inner_text())
                        page.locator("#raw").click()
                        raw_table = next(iter(json.loads((ROOT / "fixtures/data.json").read_text())))
                        page.wait_for_function("key => document.getElementById('details').textContent.includes(JSON.stringify(key))", arg=raw_table)
                        page.locator("#title").fill("复核记录")
                        page.locator("#save").click()
                        page.locator("#status").filter(has_text="已保存记录").wait_for()
                        frozen = json.loads(page.locator("#details").inner_text())
                        option = product["options"][-1]
                        alternative = next(value for value in option[2] if value != product["selection"][option[0]])
                        page.locator("#select-" + option[0]).select_option(alternative)
                        page.locator("#inspect").click()
                        page.wait_for_function("value => {try{return JSON.parse(document.getElementById('details').textContent).selection[value.key] === value.choice}catch{return false}}", arg={"key":option[0],"choice":alternative})
                        page.locator("#archive button").first.click()
                        page.locator("#status").filter(has_text="已读取保存的描述").wait_for()
                        self.assertEqual(frozen, json.loads(page.locator("#details").inner_text()))
                        with page.expect_download() as event:
                            page.locator("#export").click()
                        exported = json.loads(Path(event.value.path()).read_text())
                        self.assertEqual(exported["description"]["revision"], frozen["revision"])
                        self.assertIn(raw_table, exported["data"])
                        page.locator("#upload").set_input_files(str(ROOT / "fixtures/data.json"))
                        page.locator("#status").filter(has_text="已导入独立数据版本").wait_for()
                        self.assertEqual(page.locator("#revision option").count(), 1)
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                worker.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
