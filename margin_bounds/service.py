from pathlib import Path
import json

from .domain import explore, validate
from . import identification
from .storage import Store, fingerprint


class Workbench:
    def __init__(self, root, state):
        self.root = Path(root)
        self.product = json.loads((self.root / "product.json").read_text(encoding="utf-8"))
        self.store = Store(Path(state) / "research.sqlite3")
        initial = json.loads((self.root / "fixtures" / "data.json").read_text(encoding="utf-8"))
        validate(initial)
        self.default_revision = self.store.put_dataset("演示材料", initial)

    def context(self):
        return {"product": self.product, "default_revision": self.default_revision,
                "datasets": self.store.datasets(), "notebooks": self.store.notebooks()}

    def upload(self, body):
        data = body["data"]
        try:
            validate(data)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("字段结构不完整或类型不符") from error
        return {"revision": self.store.put_dataset(body.get("label", ""), data)}

    def inspect(self, body):
        revision = body.get("revision", self.default_revision)
        selection = body.get("selection", self.product["selection"])
        if not isinstance(selection, dict):
            raise ValueError("选择条件必须是对象")
        data = self.store.dataset(revision)
        result = explore(data, selection)
        return {"revision": revision, "selection": selection, "data_sha256": fingerprint(data), "view": result}

    def axes(self, revision=None):
        data = self.store.dataset(revision or self.default_revision)
        return {"revision": revision or self.default_revision,
                "axes": data["axes"], "releases": data["releases"]}

    def analyze(self, body):
        revision = body.get("revision", self.default_revision)
        selection = body.get("selection", self.product["selection"])
        query = body.get("query")
        if query is None:
            raise ValueError("请提供要分析的交叉人群问题")
        data = self.store.dataset(revision)
        analysis = identification.identify(data, query, selection)
        return {"revision": revision, "selection": selection,
                "data_sha256": fingerprint(data), "analysis": analysis}

    def compare(self, body):
        queries = body.get("queries")
        if not isinstance(queries, list) or not queries or len(queries) > 20:
            raise ValueError("请提供1至20个待比较问题")
        before = body.get("baseline")
        after = body.get("current")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError("比较需要基线材料与当前材料")
        baseline_revision = before.get("revision", self.default_revision)
        current_revision = after.get("revision", self.default_revision)
        baseline_selection = before.get("selection", self.product["selection"])
        current_selection = after.get("selection", self.product["selection"])
        if not isinstance(baseline_selection, dict) or not isinstance(current_selection, dict):
            raise ValueError("选择条件必须是对象")
        baseline_data = self.store.dataset(baseline_revision)
        current_data = self.store.dataset(current_revision)
        result = identification.compare(
            queries, {"data": baseline_data, "selection": baseline_selection,
                      "universe": before.get("universe")},
            {"data": current_data, "selection": current_selection,
             "universe": after.get("universe")})
        return {"baseline": {"revision": baseline_revision, "selection": baseline_selection,
                             "data_sha256": fingerprint(baseline_data)},
                "current": {"revision": current_revision, "selection": current_selection,
                            "data_sha256": fingerprint(current_data)},
                "comparison": result}

    def save(self, body):
        result = self.inspect(body)
        return self.store.save(body.get("title", ""), result["revision"], result["selection"], result)

    def save_analysis(self, body):
        result = self.analyze(body)
        return self.store.save(body.get("title", ""), result["revision"], result["selection"],
                               {"kind": "identification", **result})

    def save_comparison(self, body):
        result = self.compare(body)
        return self.store.save(body.get("title", ""), result["current"]["revision"],
                               result["current"]["selection"],
                               {"kind": "comparison", **result})
