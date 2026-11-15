"""交叉人群的统计可识别性分析。

在汇总边际构成的可行域上求查询的上下界。核心约定：

* 只有同一统计单位（persons / weighted）、同一计数对象（户而不是人次）、
  同一总体、同一期间覆盖的表才能进入同一个可行域。
* 不假定属性独立；不同表的边际只作为联立约束使用，绝不相乘成点估计。
* 明确“不可能”的结构零强制为零；“空”与“未知”只作核对提示，不冒充零。
* 整数表按整数格求解；加权表按带公开取整容差的小数连续格求解。
* 结果是汇总户数或占比的识别区间，不是对任何家庭的识别，也不代表补表后的真实人头。
"""

from itertools import product, combinations
import math

EPS = 1e-7
MAX_CELLS = 1000
MAX_QUERY_TERMS = 40
PERIOD_MODES = {'aggregate', 'annual'}
ZERO_SEMANTICS = {'impossible', 'empty', 'unknown'}
HOUSEHOLD_COUNTS = {'distinct-household'}
UNIVERSE_DEFAULT = 'eligible-households'
UNITS = {'persons', 'weighted'}


# ---------------------------------------------------------------- 基础约定

def prepare(data):
    """把已校验的原始材料整理成分析结构，不修改输入。"""
    releases = {}
    for row in data["releases"]:
        release = dict(row)
        release.setdefault("period", "aggregate")
        release.setdefault("universe", UNIVERSE_DEFAULT)
        if release["period"] not in PERIOD_MODES:
            raise ValueError("期间口径未知：" + str(release["period"]))
        if release["unit"] not in UNITS:
            raise ValueError("统计单位未知：" + str(release["unit"]))
        releases[release["table"]] = release
    axes = {row["axis"]: list(row["levels"]) for row in data["axes"]}
    for release in releases.values():
        for axis in release["dimensions"]:
            if axis not in axes:
                raise ValueError("表 " + release["table"] + " 引用未知维度：" + axis)
    zeros = []
    for row in data.get("structural_zeros", []):
        semantics = row.get("zero", "impossible")
        if semantics not in ZERO_SEMANTICS:
            raise ValueError("结构零语义未知：" + str(semantics))
        coordinates = dict(row["coordinates"])
        if any(axis not in axes or level not in axes[axis]
               for axis, level in coordinates.items()):
            raise ValueError("结构零引用未知维度或水平：" + row["rule"])
        zeros.append({"rule": row["rule"], "coordinates": coordinates,
                      "zero": semantics})
    for margin in data["margins"]:
        if margin["table"] not in releases:
            raise ValueError("边际引用不存在的表：" + margin["cell"])
    return {"releases": releases, "axes": axes, "margins": data["margins"], "zeros": zeros}


def validate_query(model, query):
    """查询由 population（分母人群）和 outcome（在其上再加的结果条件）组成。"""
    if not isinstance(query, dict):
        raise ValueError("查询必须是对象")
    fields = {}
    for field, minimum in [("population", 0), ("outcome", 1)]:
        values = query.get(field, [])
        if not isinstance(values, list) or len(values) < minimum:
            raise ValueError("查询条件格式不正确：" + field)
        fields[field] = []
        for term in values:
            if not isinstance(term, dict) or set(term) != {"axis", "level"}:
                raise ValueError("每个条件应只含 axis 与 level")
            axis, level = term["axis"], term["level"]
            if axis not in model["axes"]:
                raise ValueError("材料中没有该维度：" + str(axis))
            if level not in model["axes"][axis]:
                raise ValueError("该维度没有此水平：" + str(level))
            fields[field].append({"axis": axis, "level": level})
    count = len(fields["population"]) + len(fields["outcome"])
    if count > MAX_QUERY_TERMS:
        raise ValueError("查询条件过多")
    used = [term["axis"] for term in fields["population"] + fields["outcome"]]
    if len(used) != len(set(used)):
        raise ValueError("同一维度不能在分母或结果条件中重复出现")
    return {"population": fields["population"], "outcome": fields["outcome"]}


def validate_selection(selection):
    if not isinstance(selection, dict):
        raise ValueError("选择条件必须是对象")
    if selection.get("release") not in {"first", "supplement"}:
        raise ValueError("选择范围无效：release")
    if selection.get("unit") not in UNITS:
        raise ValueError("选择范围无效：unit")
    universe = selection.get("universe", UNIVERSE_DEFAULT)
    if not isinstance(universe, str) or not universe:
        raise ValueError("选择范围无效：universe")
    return {"release": selection["release"], "unit": selection["unit"],
            "universe": universe}


def terms_text(terms):
    return "，".join(str(term["axis"]) + "=" + str(term["level"]) for term in terms) or "全部户"


def _covered(release):
    return int(release["start"]), int(release["stop"])


def _coverage_years(release):
    low, high = _covered(release)
    return set(range(low, high + 1))


# ---------------------------------------------------------------- 表与期间

def candidates(model, selection):
    """逐表判断是否可进入同一可行域，并给出具体排除原因。"""
    rounds = {"first"} if selection["release"] == "first" else {"first", "supplement"}
    result = []
    for name, release in sorted(model["releases"].items()):
        reasons = []
        if release["unit"] != selection["unit"]:
            reasons.append("统计单位为 " + release["unit"] + "，与当前选择的 " +
                           selection["unit"] + " 不同，不能拼入同一可行域")
        if release["release"] not in rounds:
            reasons.append("属于 " + release["release"] + " 轮次，当前选择未纳入")
        if release["counting"] not in HOUSEHOLD_COUNTS:
            reasons.append("按 " + release["counting"] + " 计数，不是去重户数，不能与其他户汇总表相加")
        if release["universe"] != selection["universe"]:
            reasons.append("总体为 " + release["universe"] + "，与查询总体不同")
        result.append({"table": name, "release": release,
                       "eligible": not reasons, "reasons": reasons})
    return result


def choose_window(eligible):
    """选出真正兼容的期间组；期间口径或覆盖不同的一律不并入。

    aggregate 表要求起止完全一致；annual 表要求存在共同年份，默认用覆盖
    最多表的年份，也接受调用方指定年份。
    """
    if not eligible:
        return None, [], []
    modes = {mode: [item for item in eligible if item["release"]["period"] == mode]
             for mode in PERIOD_MODES}
    present = [mode for mode in modes if modes[mode]]
    chosen_mode = max(present, key=lambda mode: (len(modes[mode]), mode == "aggregate"))
    excluded = []
    for mode in present:
        if mode == chosen_mode:
            continue
        for item in modes[mode]:
            excluded.append({"table": item["table"],
                             "reason": "期间口径为 " + mode + "，与所选 " + chosen_mode + " 组不混用"})
    chosen = modes[chosen_mode]
    if chosen_mode == "aggregate":
        spans = {}
        for item in chosen:
            spans.setdefault(_covered(item["release"]), []).append(item)
        span = max(spans, key=lambda value: (len(spans[value]), value[1] - value[0]))
        group = spans[span]
        for other, items in spans.items():
            if other == span:
                continue
            for item in items:
                excluded.append({"table": item["table"],
                                 "reason": "汇总期间为 " + str(other[0]) + "–" + str(other[1]) +
                                           "，与所选组的 " + str(span[0]) + "–" + str(span[1]) + " 不同"})
        return {"mode": "aggregate", "year": None, "items": group,
                "period": str(span[0]) + "–" + str(span[1])}, \
            [item for item in eligible if item not in group], excluded
    years = {}
    for year_value in range(0, 61):
        for item in chosen:
            if year_value in _coverage_years(item["release"]):
                years.setdefault(year_value, []).append(item)
    if not years:
        return None, [], []
    year_value = max(years, key=lambda value: (len(years[value]), value))
    group = years[year_value]
    for item in chosen:
        if item not in group:
            excluded.append({"table": item["table"],
                             "reason": "未覆盖 " + str(year_value) + " 年"})
    return {"mode": "annual", "year": year_value, "items": group,
            "period": str(year_value) + " 年"}, \
        [item for item in eligible if item not in group], excluded


# ---------------------------------------------------------------- 可行域

def _axis_levels(releases):
    axes = []
    for release in releases:
        for axis in release["dimensions"]:
            if axis not in axes:
                axes.append(axis)
    return axes


def _table_rows(release, axes, levels, cell_index):
    dims = list(release["dimensions"])
    others = [axis for axis in axes if axis not in dims]
    rows = []
    for combination in product(*[levels[axis] for axis in dims]):
        coordinates = dict(zip(dims, combination))
        indices = []
        for rest in product(*[levels[axis] for axis in others]):
            cell = dict(zip(others, rest))
            cell.update(coordinates)
            indices.append(cell_index[tuple(cell[axis] for axis in axes)])
        rows.append({"coordinates": coordinates, "indices": indices})
    return rows


def build_grid(model, releases, period, year, universe):
    axes = _axis_levels(releases)
    if not axes:
        raise ValueError("没有可用的交叉维度")
    levels = {axis: model["axes"][axis] for axis in axes}
    cells = [dict(zip(axes, combination))
             for combination in product(*[levels[axis] for axis in axes])]
    if len(cells) > MAX_CELLS:
        raise ValueError("可共用单元格超过上限（1000），请缩小材料范围或减少交叉维度")
    cell_index = {tuple(cell[axis] for axis in axes): index for index, cell in enumerate(cells)}
    rows = []
    info = []
    cell_upper = None
    for release in releases:
        table_rows = _table_rows(release, axes, levels, cell_index)
        by_coordinates = {tuple(sorted(row["coordinates"].items())): row for row in table_rows}
        table_upper = 0.0
        matched = set()
        for margin in model["margins"]:
            if margin["table"] != release["table"]:
                continue
            key = tuple(sorted(margin["coordinates"].items()))
            if key not in by_coordinates:
                raise ValueError("边际坐标不在表维度内：" + margin["cell"])
            if key in matched:
                raise ValueError("同一行被多条边际重复约束：" + margin["cell"])
            matched.add(key)
            row = by_coordinates[key]
            low = margin["value"] - release["tolerance"]
            high = margin["value"] + release["tolerance"]
            table_upper += high
            rows.append({"kind": "table", "table": release["table"],
                         "label": release["table"] + " " + terms_text(
                             [{"axis": axis, "level": value}
                              for axis, value in margin["coordinates"].items()]),
                         "coef": {index: 1 for index in row["indices"]},
                         "low": low, "high": high,
                         "value": margin["value"], "tolerance": release["tolerance"],
                         "coordinates": dict(margin["coordinates"])})
        if len(matched) != len(table_rows):
            raise ValueError("表 " + release["table"] + " 的行不完整，不能作为可行约束")
        cell_upper = table_upper if cell_upper is None else min(cell_upper, table_upper)
        info.append({"table": release["table"], "release": release["release"],
                     "unit": release["unit"], "counting": release["counting"],
                     "universe": release["universe"], "tolerance": release["tolerance"],
                     "period": period, "dimensions": list(release["dimensions"]),
                     "rows": len(table_rows)})
    rules = []
    for zero in model["zeros"]:
        coordinates = zero["coordinates"]
        if any(axis not in levels for axis in coordinates):
            rules.append({"rule": zero["rule"], "zero": zero["zero"], "applied": False,
                          "effect": "规则含当前材料未覆盖的维度，未并入可行域"})
            continue
        indices = [index for index, cell in enumerate(cells)
                   if all(cell[axis] == value for axis, value in coordinates.items())]
        if not indices:
            rules.append({"rule": zero["rule"], "zero": zero["zero"], "applied": False,
                          "effect": "规则没有匹配到当前可行域中的单元"})
            continue
        if zero["zero"] == "impossible":
            rows.append({"kind": "structural", "table": None,
                         "label": "结构零 " + zero["rule"],
                         "coef": {index: 1 for index in indices},
                         "low": 0, "high": 0, "value": 0, "tolerance": 0,
                         "coordinates": dict(coordinates), "rule": zero["rule"]})
            rules.append({"rule": zero["rule"], "zero": zero["zero"], "applied": True,
                          "effect": "该交叉单元的户数被强制为 0", "cells": len(indices)})
        else:
            rules.append({"rule": zero["rule"], "zero": zero["zero"], "applied": False,
                          "effect": "语义为“" + zero["zero"] + "”，不当作已确认的零，仅作核对提示",
                          "cells": len(indices)})
    if not info:
        raise ValueError("没有可用表")
    return {"axes": axes, "levels": levels, "cells": cells, "index": cell_index,
            "rows": rows, "tables": info, "rules": rules,
            "period": period, "year": year, "universe": universe,
            "integer": all(item["unit"] == "persons" for item in info),
            "cell_upper": max(0.0, float(cell_upper or 0.0))}


def _columns(grid, terms):
    conditions = [(term["axis"], term["level"]) for term in terms
                  if term["axis"] in grid["axes"]]
    return {index: 1 for index, cell in enumerate(grid["cells"])
            if all(cell[axis] == level for axis, level in conditions)}


def _solve(grid, coefficients, direction):
    """direction = 1 求最小，-1 求最大。返回状态、目标值和解向量。

    整数表先在连续松弛上判定可行与界，仅当松弛解不整时转为整数规划；加权
    表用连续 LP，并显式带上单元格的非负上界，避免无界解被误读为“真实人头”。
    """
    import numpy as np
    from scipy.optimize import linprog, milp, Bounds, LinearConstraint
    from scipy.sparse import csc_matrix

    n = len(grid["cells"])
    sparse_rows, sparse_columns, sparse_values, upper = [], [], [], []
    row = 0
    for constraint in grid["rows"]:
        if constraint["high"] is not None:
            for variable, coefficient in constraint["coef"].items():
                sparse_rows.append(row)
                sparse_columns.append(variable)
                sparse_values.append(coefficient)
            upper.append(constraint["high"])
            row += 1
        if constraint["low"] is not None:
            for variable, coefficient in constraint["coef"].items():
                sparse_rows.append(row)
                sparse_columns.append(variable)
                sparse_values.append(-coefficient)
            upper.append(-constraint["low"])
            row += 1
    if row == 0:
        return {"status": "infeasible", "value": None, "solution": None}
    matrix = csc_matrix((np.asarray(sparse_values, dtype=float),
                         (sparse_rows, sparse_columns)), shape=(row, n))
    objective = np.zeros(n, dtype=float)
    for variable, coefficient in coefficients.items():
        objective[variable] += coefficient * direction
    cell_bound = max(1.0, grid["cell_upper"])

    def observed(result, ok, integral=False):
        return {"status": "ok" if ok else ("infeasible" if result.status == 2 else "failed"),
                "value": float(result.fun) if ok else None,
                "solution": result.x if ok else None,
                "message": result.message, "integral": integral}

    def relaxed():
        outcome = linprog(objective, A_ub=matrix, b_ub=np.asarray(upper, dtype=float),
                          bounds=[(0, cell_bound)] * n, method="highs")
        if outcome.status == 2:
            return observed(outcome, False)
        if outcome.status != 0:
            return observed(outcome, False)
        # LP 最优值是整数解的合法界；若解本身全为整数，它就是整数最优解。
        values = outcome.x
        integral = all(abs(value - round(value)) <= 1e-6 for value in values)
        return observed(outcome, True, integral)

    if grid["integer"]:
        answer = relaxed()
        if answer["status"] == "infeasible":
            return answer
        if not (answer["status"] == "ok" and answer["integral"]):
            result = milp(objective, integrality=np.ones(n),
                          bounds=Bounds(np.zeros(n), np.full(n, cell_bound)),
                          constraints=LinearConstraint(matrix, -np.inf,
                                                        np.asarray(upper, dtype=float)),
                          options={"time_limit": 20})
            answer = observed(result, result.status == 0)
    else:
        answer = relaxed()
    if answer["status"] != "ok":
        return answer
    answer["value"] *= direction
    if abs(answer["value"]) < 1e-6:
        answer["value"] = 0.0
    return answer


def _bounds(grid, coefficients):
    if not coefficients:
        return {"feasible": True, "low": 0.0, "high": 0.0, "unique": True}
    low = _solve(grid, coefficients, 1)
    high = _solve(grid, coefficients, -1)
    if low["status"] == "infeasible" or high["status"] == "infeasible":
        return {"feasible": False, "reason": "infeasible"}
    if low["status"] != "ok" or high["status"] != "ok":
        return {"feasible": False, "reason": "solver-failed",
                "message": low.get("message") or high.get("message")}
    low_value, high_value = low["value"], high["value"]
    if grid["integer"]:
        low_value = math.ceil(low_value - 1e-6)
        high_value = math.floor(high_value + 1e-6)
    else:
        low_value = max(0.0, low_value - 1e-9)
        high_value = max(0.0, high_value + 1e-9)
    low_value = max(0.0, low_value)
    high_value = max(low_value, high_value)
    return {"feasible": True, "low": low_value, "high": high_value,
            "unique": high_value - low_value <= EPS}


def _clean(value):
    if value is None:
        return None
    if abs(value) < 1e-6:
        return 0
    rounded = round(float(value), 6)
    return int(rounded) if float(rounded).is_integer() else rounded


# ---------------------------------------------------------------- 冲突核对

def _row_value(model, table, coordinates):
    for margin in model["margins"]:
        if margin["table"] == table and margin["coordinates"] == coordinates:
            return margin["value"]
    return None


def _projection(model, release, target):
    low = high = 0.0
    count = 0
    dims = release["dimensions"]
    for combination in product(*[model["axes"][axis] for axis in dims]):
        coordinates = dict(zip(dims, combination))
        if not all(coordinates.get(axis) == value for axis, value in target.items()):
            continue
        value = _row_value(model, release["table"], coordinates)
        if value is None:
            continue
        low += value - release["tolerance"]
        high += value + release["tolerance"]
        count += 1
    return {"low": low, "high": high, "count": count}


def _disjoint(a, b):
    return a["high"] < b["low"] - 1e-6 or b["high"] < a["low"] - 1e-6


def _pair_conflict(model, left, right):
    shared = [axis for axis in left["dimensions"] if axis in right["dimensions"]]
    details = []
    targets = []
    if shared:
        for combination in product(*[model["axes"][axis] for axis in shared]):
            targets.append(dict(zip(shared, combination)))
    else:
        targets.append({})
    for target in targets:
        a = _projection(model, left, target)
        b = _projection(model, right, target)
        if not a["count"] or not b["count"] or not _disjoint(a, b):
            continue
        details.append({
            "coordinates": target,
            "sources": [
                {"table": left["table"], "implied_low": _clean(a["low"]),
                 "implied_high": _clean(a["high"])},
                {"table": right["table"], "implied_low": _clean(b["low"]),
                 "implied_high": _clean(b["high"])}],
            "message": ("共同维度 " + terms_text(
                [{"axis": axis, "level": value} for axis, value in target.items()]) +
                " 上两表合计区间不相交；需核对公开值、总体或取整容差") if target else
                "两表在共同总体上的合计区间不相交；需核对总体、期间或取整容差",
        })
    if not details:
        return None
    return {"tables": [left["table"], right["table"]], "kind": "implied-total",
            "details": details}


def _structural_conflict(model, release, zero):
    if zero["zero"] != "impossible":
        return None
    if not set(zero["coordinates"]) <= set(release["dimensions"]):
        return None
    target = dict(zero["coordinates"])
    value = _row_value(model, release["table"], target)
    if value is None or value - release["tolerance"] <= 1e-6:
        return None
    return {"tables": [release["table"]], "kind": "structural-zero",
            "details": [{"coordinates": target,
                         "message": "结构零规则 " + zero["rule"] + " 声明该组合不可能，但表 " +
                                    release["table"] + " 报出 " + str(value) + "；需核对规则或数值"}]}


def _subgrid_feasible(model, releases, grid):
    if not releases:
        return True
    try:
        trial = build_grid(model, releases, grid["period"], grid["year"], grid["universe"])
        return _bounds(trial, _columns(trial, []))["feasible"]
    except ValueError:
        # 表本身不完整或超出网格上限时不能断言相容，交由联合冲突说明处理。
        return False

def diagnose_conflicts(model, releases, grid):
    """整体不可行时，给出可核对的冲突组合。

    先找两表之间可直接核对的分组合计；若没有，则用删除法找出必须联立后
    才暴露矛盾的最小表集合。不会把某一张表的结果当成真实人头。
    """
    found = []
    for left, right in combinations(releases, 2):
        entry = _pair_conflict(model, left, right)
        if entry:
            found.append(entry)
    for release in releases:
        for zero in model["zeros"]:
            entry = _structural_conflict(model, release, zero)
            if entry:
                found.append(entry)
    if found:
        return found
    current = list(releases)
    for release in list(releases):
        trial = [item for item in current if item != release]
        if trial and _subgrid_feasible(model, trial, grid):
            current = trial
    if len(current) >= 2:
        return [{"tables": [item["table"] for item in current], "kind": "joint",
                 "details": [{"message": "两两核对未直接发现矛盾；至少这几张表联立后无可行解，需一并核对其口径、结构规则与取整约定"}]}]
    if len(current) == 1:
        return [{"tables": [current[0]["table"]], "kind": "joint",
                 "details": [{"message": "该表自身约束联立后无可行解，需核对公开值的取整容差或结构零规则"}]}]
    return [{"tables": [], "kind": "joint",
             "details": [{"message": "当前材料联立后无可行解，但未能定位到更小的冲突组合"}]}]


# ---------------------------------------------------------------- 对外分析

def _confidence(grid):
    if grid["integer"]:
        return "整数户数格；取整容差已计入上下界"
    return "加权小数格；按连续松弛计算，取整容差为公开半宽"


def _share_bounds(result, grid):
    numerator, denominator = result["numerator"], result["denominator"]
    den_low, den_high = denominator["low"], denominator["high"]
    num_low, num_high = numerator["low"], numerator["high"]
    if den_high <= EPS:
        return {"low": None, "high": None, "unique": False, "defined": False}
    if den_low <= EPS:
        if num_high <= EPS:
            return {"low": 0, "high": 0, "unique": True, "defined": True}
        if grid["integer"]:
            low = 0
            high = min(1.0, num_high / 1.0)
            return {"low": _clean(low), "high": _clean(high),
                    "unique": high - low <= EPS, "defined": True,
                    "caveat": "分母最小可能为 0；区间按整数格的最小正分母 1 计"}
        return {"low": None, "high": None, "unique": False, "defined": False,
                "caveat": "加权分母可任意接近 0，比例未定义"}
    low = max(0.0, min(1.0, num_low / den_high))
    high = max(low, min(1.0, num_high / den_low))
    unique = (num_high - num_low <= EPS and den_high - den_low <= EPS) or num_high <= EPS
    return {"low": _clean(low), "high": _clean(high), "unique": unique, "defined": True}


def _excluded_candidates(cands, extra):
    excluded = []
    for item in cands:
        if not item["eligible"]:
            excluded.append({"table": item["table"], "reasons": item["reasons"]})
    for item in extra:
        excluded.append({"table": item["table"], "reasons": [item["reason"]]})
    return excluded


def _evidence_used(grid, query_axes):
    used = []
    for info in grid["tables"]:
        direct = sorted(set(info["dimensions"]) & query_axes)
        used.append({**info,
                     "role": "直接约束 " + "、".join(direct) if direct
                     else "约束总体规模（查询未涉及该维度）",
                     "why": "同单位、同户数计数、同总体、同期间，可并入同一可行域"})
    return used


def _unsupported(query, selection, period, evidence, notes):
    return {"status": "unsupported", "query": query, "selection": selection,
            "period": period, "numerator": None, "denominator": None, "share": None,
            "evidence": evidence, "conflicts": [], "notes": notes,
            "alternatives": []}


def identify(data, query, selection, universe=None):
    """对一份材料执行一次交叉人群识别性分析。"""
    model = prepare(data)
    normalized = validate_query(model, query)
    selection = validate_selection(dict(selection, **({"universe": universe} if universe else {})))
    cands = candidates(model, selection)
    eligible = [item for item in cands if item["eligible"]]
    empty_evidence = {"used": [], "excluded": _excluded_candidates(cands, []),
                      "rules": [], "period": None}
    if not eligible:
        return _unsupported(normalized, selection, None, empty_evidence,
                            ["当前统计单位与轮次下没有可用的户数汇总表，不能给出区间。"])
    window, other_window, window_excluded = choose_window(eligible)
    if window is None:
        return _unsupported(normalized, selection, None, empty_evidence,
                            ["当前材料没有可共同使用的期间组，不能给出区间。"])
    releases = [item["release"] for item in window["items"]]
    excluded = _excluded_candidates(cands, window_excluded)
    for item in other_window:
        if not any(entry["table"] == item["table"] for entry in excluded):
            excluded.append({"table": item["table"], "reasons": ["期间组与本次分析不同"]})
    query_axes = {term["axis"] for term in normalized["population"] + normalized["outcome"]}
    covered_axes = {axis for release in releases for axis in release["dimensions"]}
    missing = sorted(query_axes - covered_axes)
    if missing:
        evidence = {"used": [{"table": release["table"], "release": release["release"],
                              "unit": release["unit"], "counting": release["counting"],
                              "universe": release["universe"], "tolerance": release["tolerance"],
                              "period": window["period"], "dimensions": list(release["dimensions"]),
                              "role": "未覆盖查询维度",
                              "why": "该表与其余表可共用，但不含查询维度"} for release in releases],
                    "excluded": excluded, "rules": [], "period": window["period"]}
        return _unsupported(normalized, selection, window["period"], evidence,
                            ["材料中没有覆盖维度 " + "、".join(missing) + " 的可用表，无法给出区间。"])
    grid = build_grid(model, releases, window["period"], window["year"], selection["universe"])
    numerator = _bounds(grid, _columns(grid, normalized["population"] + normalized["outcome"]))
    denominator = _bounds(grid, _columns(grid, normalized["population"]))
    evidence = {"used": _evidence_used(grid, query_axes), "excluded": excluded,
                "rules": grid["rules"], "confidence": _confidence(grid),
                "cells": len(grid["cells"]), "period": window["period"]}
    result = {"status": "possible", "query": normalized, "selection": selection,
              "period": window["period"], "year": window["year"],
              "numerator": None, "denominator": None, "share": None,
              "evidence": evidence, "conflicts": [], "notes": [], "alternatives": []}
    if not numerator["feasible"] or not denominator["feasible"]:
        result["status"] = "conflict"
        result["conflicts"] = diagnose_conflicts(model, releases, grid)
        result["notes"] = [
            "现有材料联立后没有可行解，因此不给出“最小/最大”区间。",
            "下方冲突组合列出可直接核对的表与合计；请先核对材料，不要把任何单表结果当作真实人头。",
        ]
        return result
    result["numerator"] = {"low": _clean(numerator["low"]), "high": _clean(numerator["high"]),
                           "unique": numerator["unique"], "unit": "户"}
    result["denominator"] = {"low": _clean(denominator["low"]),
                             "high": _clean(denominator["high"]),
                             "unique": denominator["unique"], "unit": "户"}
    result["share"] = _share_bounds(result, grid)
    if not result["share"]["defined"]:
        result["status"] = "undefined"
    elif result["share"]["unique"]:
        result["status"] = "unique"
    else:
        result["status"] = "possible"
    result["notes"] = _notes(result, grid)
    result["alternatives"] = _alternatives(model, releases, normalized, selection, window, grid)
    return result


def _notes(result, grid):
    notes = [
        "区间来自同一可行域的最小与最大值；未假定各维度独立，也不是把边际相乘。",
        "这些是汇总户数或占比的可能范围，不是任何家庭的人头识别；区间内单点不等于真实补表结果。",
    ]
    units = {item["unit"] for item in grid["tables"]}
    if "weighted" in units:
        notes.append("加权表按小数连续松弛求解，公开取整容差已计入；区间可能比整数格更宽。")
    else:
        notes.append("整数表按整数格求解，公开取整容差已计入上下界。")
    if result["evidence"]["rules"]:
        notes.append("结构零只对语义为“不可能”的单元强制为零；“空”和“未知”不冒充零。")
    if result["evidence"]["excluded"]:
        notes.append("未并入的表及原因列在证据范围中；只有真正兼容的约束参与求解。")
    notes.append("本次只用同一期间口径的表（" + str(grid["period"]) +
                 "）；覆盖或口径不同的表未并入同一可行域。")
    if len(grid["tables"]) > 1:
        notes.append("本次联立了 " + str(len(grid["tables"])) +
                     " 张表的约束；任何单表的结果都不能代替联立区间。")
    return notes


def _alternatives(model, releases, query, selection, window, grid):
    """逐张表的贡献：去掉一张表后区间如何变化，用于说明哪些约束在起作用。

    网格较大时跳过逐表重解，避免一次查询触发过多求解。
    """
    if len(releases) < 2 or len(grid["cells"]) > 600:
        return []
    full = _bounds(grid, _columns(grid, query["population"] + query["outcome"]))
    if not full["feasible"]:
        return []
    rows = []
    query_axes = {term["axis"] for term in query["population"] + query["outcome"]}
    for release in releases:
        trial_releases = [item for item in releases if item["table"] != release["table"]]
        covered = {axis for item in trial_releases for axis in item["dimensions"]}
        if query_axes - covered:
            rows.append({"removed": release["table"], "numerator": {"low": None, "high": None},
                         "effect": "失去该表后查询维度不再被覆盖，问题不可答"})
            continue
        try:
            trial = build_grid(model, trial_releases, window["period"], window["year"],
                               selection["universe"])
        except ValueError:
            continue
        bounds = _bounds(trial, _columns(trial, query["population"] + query["outcome"]))
        rows.append({"removed": release["table"],
                     "numerator": {"low": _clean(bounds["low"]) if bounds["feasible"] else None,
                                   "high": _clean(bounds["high"]) if bounds["feasible"] else None},
                     "effect": "失去该表后可继续求解" if bounds["feasible"] else "失去该表后无可行解"})
    return rows


# ---------------------------------------------------------------- 比较

def _width(result):
    share = result.get("share")
    if result["status"] not in {"unique", "possible"} or not share or not share.get("defined"):
        return None
    if share["high"] is None:
        return None
    return share["high"] - share["low"]


def _summary(result):
    return {"status": result["status"], "period": result["period"],
            "numerator": result["numerator"], "denominator": result["denominator"],
            "share": result["share"],
            "tables": [item["table"] for item in result["evidence"]["used"]],
            "conflicts": [{"tables": entry["tables"], "kind": entry["kind"]}
                          for entry in result["conflicts"]]}


def _change(before, after):
    before_status, after_status = before["status"], after["status"]
    before_width, after_width = _width(before), _width(after)
    if before_status == "conflict" and after_status in {"unique", "possible"}:
        return "冲突已解除"
    if before_status in {"unique", "possible", "undefined"} and after_status == "conflict":
        return "新增冲突"
    if before_status == "unsupported" and after_status != "unsupported":
        return "新表使问题可答"
    if after_status == "unsupported" and before_status != "unsupported":
        return "当前选择下不可答"
    if before_width is None or after_width is None:
        return "无变化" if before_status == after_status else "状态改变"
    if after_width < before_width - EPS:
        return "范围缩小"
    if after_width > before_width + EPS:
        return "范围扩大"
    if after_status == "unique" and before_status != "unique":
        return "变为唯一可确定"
    return "无变化"


def compare(queries, baseline, current):
    """同一组问题在两份材料上的识别范围对比。

    baseline / current 各含 revision 对应的 data、selection 与可选 universe。
    """
    rows = []
    for query in queries:
        if not isinstance(query, dict) or set(query) - {"population", "outcome", "label"}:
            raise ValueError("每个问题应只含 population、outcome 与可选 label")
        before = identify(baseline["data"], query, baseline["selection"], baseline.get("universe"))
        after = identify(current["data"], query, current["selection"], current.get("universe"))
        rows.append({"query": after["query"], "label": query.get("label", ""),
                     "baseline": _summary(before), "current": _summary(after),
                     "change": _change(before, after)})
    return {"rows": rows,
            "notes": ["比较只反映现有材料下识别区间的变化；范围缩小不等于接近真实值。",
                      "历史记录仍以保存时的材料与原区间打开，不随后续补表重算。"]}
