import math


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
