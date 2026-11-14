from .validation import require_tables, unique, finite, references


SCHEMA = {'releases': {'table': ['str'], 'release': ['str'], 'unit': ['str'], 'start': ['number'], 'stop': ['number'], 'universe': ['str'], 'counting': ['str'], 'dimensions': ['list'], 'tolerance': ['number']}, 'margins': {'cell': ['str'], 'table': ['str'], 'coordinates': ['dict'], 'value': ['number']}, 'axes': {'axis': ['str'], 'levels': ['list']}, 'structural_zeros': {'rule': ['str'], 'coordinates': ['dict']}}
OPTIONS = {'release': ['first', 'supplement'], 'unit': ['persons', 'weighted']}


def validate_structure(data, schema):
    require_tables(data, list(schema))
    for table, fields in schema.items():
        for row in data[table]:
            if not isinstance(row, dict) or any(field not in row for field in fields):
                raise ValueError("表字段缺失：" + table)
            for field, kinds in fields.items():
                value = row[field]
                kind = "null" if value is None else ("boolean" if isinstance(value,bool) else ("number" if isinstance(value,(int,float)) else type(value).__name__))
                if kind not in kinds:
                    raise ValueError("字段类型错误：" + table + "." + field)
                if kind == "number":
                    finite(value)


def validate(data):
    validate_structure(data, SCHEMA)
    unique(data['releases'], ['table'])
    unique(data['margins'], ['cell'])
    unique(data['axes'], ['axis'])
    unique(data['structural_zeros'], ['rule'])
    references(data['margins'], 'table', data['releases'], 'table')
    axes = {row["axis"]:set(row["levels"]) for row in data["axes"]}
    releases = {row["table"]:row for row in data["releases"]}
    for row in data["margins"]:
        finite(row["value"], minimum=0)
        if set(row["coordinates"]) != set(releases[row["table"]]["dimensions"]):
            raise ValueError("边际维度与表头不符")
        if any(key not in axes or value not in axes[key] for key,value in row["coordinates"].items()):
            raise ValueError("边际引用未知维度或水平")


def view(rows, measure, note):
    return {"summary":{"明细条数":len(rows),"有数值记录":sum(isinstance(row.get(measure),(int,float)) for row in rows)},
            "rows":rows,"series":[{"label":str(position+1),"y":row.get(measure)} for position,row in enumerate(rows)],
            "notes":[note]}


def explore(data, selection):
    for key, choices in OPTIONS.items():
        if selection.get(key) not in choices:
            raise ValueError("选择范围无效：" + key)
    rows = []
    for release in data["releases"]:
        if release["unit"] != selection["unit"] or (selection["release"] == "first" and release["release"] != "first"):
            continue
        cells = [row for row in data["margins"] if row["table"] == release["table"]]
        rows.append({**release,"cells":len(cells),"table_total":sum(row["value"] for row in cells)})
    return view(rows, "table_total", "各表总数仅用于资料核对，不等于兼容性检查，更不能据此确定未披露交叉人群。")
