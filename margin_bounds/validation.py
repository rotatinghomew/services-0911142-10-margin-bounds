import math

ZERO_SEMANTICS = {"impossible", "empty", "unknown"}
PERIOD_MODES = {"aggregate", "annual"}


def require_tables(data, names):
    if not isinstance(data, dict):
        raise ValueError("数据必须是对象")
    for name in names:
        if name not in data or not isinstance(data[name], list):
            raise ValueError("缺少数据表或表不是数组：" + name)
    if sum(len(value) for value in data.values() if isinstance(value, list)) > 100000:
        raise ValueError("单份分析数据超过十万条，请拆分业务范围")


def unique(records, keys):
    identifiers = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("表内记录必须是对象")
        try:
            identifier = tuple(record[key] for key in keys)
            if any(value is None or value == "" for value in identifier) or identifier in identifiers:
                raise ValueError("记录主键为空或重复：" + ",".join(keys))
            identifiers.add(identifier)
        except (KeyError, TypeError):
            raise ValueError("记录主键字段缺失或不可用：" + ",".join(keys)) from None


def finite(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("数值应为有限数字")
    if minimum is not None and value < minimum:
        raise ValueError("数值低于允许范围")
    if maximum is not None and value > maximum:
        raise ValueError("数值超过允许范围")


def references(records, field, targets, target_key):
    identifiers = {record[target_key] for record in targets}
    if any(record.get(field) not in identifiers for record in records):
        raise ValueError("引用了不存在的对象：" + field)


def coordinate_patterns(records, axes, key="rule"):
    """校验 margins 的 coordinates 与 structural_zeros 的语义。"""
    signatures = set()
    for record in records:
        coordinates = record["coordinates"]
        if not isinstance(coordinates, dict) or not coordinates:
            raise ValueError("交叉条件应为非空对象")
        if any(not isinstance(axis, str) or axis not in axes for axis in coordinates):
            raise ValueError("交叉条件引用未知维度")
        if any(value not in axes[axis] for axis, value in coordinates.items()):
            raise ValueError("交叉条件引用未知水平")
        signature = (record.get(key), frozenset(coordinates.items()))
        if signature in signatures:
            raise ValueError("交叉条件重复")
        signatures.add(signature)


def release_conventions(records):
    """校验表的单位、计数、期间与取整约定，为识别性分析提供可靠元数据。"""
    for record in records:
        if record["unit"] not in {"persons", "weighted"}:
            raise ValueError("统计单位未知：" + str(record["unit"]))
        if record["counting"] not in {"distinct-household", "visits",
                                     "distinct-person", "households"}:
            raise ValueError("计数对象未知：" + str(record["counting"]))
        period = record.get("period", "aggregate")
        if period not in PERIOD_MODES:
            raise ValueError("期间口径未知：" + str(period))
        start, stop = record["start"], record["stop"]
        if start > stop:
            raise ValueError("期间起点晚于终点：" + record["table"])
        tolerance = record["tolerance"]
        finite(tolerance, minimum=0)
        if record["unit"] == "persons" and tolerance != 0:
            raise ValueError("整数人数表的取整容差应为 0：" + record["table"])
        if record["unit"] == "weighted" and tolerance >= 1:
            raise ValueError("加权表的取整容差应小于 1：" + record["table"])


def margin_bounds(records, releases, zero_semantics):
    """边际非负；明确不可能的单元不得报出会影响结构零的正值。"""
    units = {record["table"]: record["unit"] for record in releases}
    for record in records:
        finite(record["value"], minimum=0)
        if units[record["table"]] == "persons" and not float(record["value"]).is_integer():
            raise ValueError("整数人数表的边际应为整数：" + record["cell"])
    for record in zero_semantics:
        if record.get("zero", "impossible") not in ZERO_SEMANTICS:
            raise ValueError("结构零语义未知：" + str(record.get("zero")))
