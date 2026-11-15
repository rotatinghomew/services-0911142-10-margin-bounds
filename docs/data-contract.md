# 资料与统计口径

`axes` 给出全局交叉维度及离散水平，`margins.coordinates` 描述某张表一个交叉单元，不含的维度表示求和边际。`releases` 规定单位、资料轮次、期间、总体和去重方式；人数与人次或不同期间不因维度重合而可拼接。`persons` 的 `value` 是非负整数，`weighted` 为非负实数，`tolerance` 是允许的公开取整误差半宽。`structural_zeros` 是明确不可能的交叉组合，并非未披露格子均为零。`supplement` 累积第一轮可用材料，需先检查兼容性；原始表不保证永远一致。比例指标的分母由查询人群条件决定，不自动取总人数；分母可为零时需解释未定义。

## 原始表

- `releases`：10条示例，主键为 `table`。字段：`table`, `release`, `unit`, `start`, `stop`, `universe`, `counting`, `dimensions`, `tolerance`；可选 `period`（`aggregate` 或 `annual`）与 `level_map`（表内水平到全局水平的映射）。
- `margins`：38条示例，主键为 `cell`。字段：`cell`, `table`, `coordinates`, `value`。
- `axes`：4条示例，主键为 `axis`。字段：`axis`, `levels`；可选 `level_map`。
- `structural_zeros`：1条示例，主键为 `rule`。字段：`rule`, `coordinates`；可选 `zero`（`impossible`、`empty` 或 `unknown`）。

## 识别性分析的共用条件

只有同时满足下列条件的表才进入同一个可行域，其余表在证据范围中列出具体排除原因：

- 统计单位相同（`persons` 与 `weighted` 不混用）。
- 计数对象为去重户数；`visits`、`distinct-person` 等不能与户汇总表相加。
- `universe` 相同。
- 期间口径相同。`aggregate` 表要求起止一致；`annual` 表要求存在共同年份。不同期间口径或不同覆盖不混合，也不会取共同年份以外数据的近似值。

`persons` 表的单元格变量取整数；`weighted` 表按带公开容差的连续变量求解。`structural_zeros` 只有 `zero` 为 `impossible`（缺省）时才强制为零；`empty` 与 `unknown` 仅作为核对提示，避免把“空”或“未知”误读为已确认的零。区间内任一点都不是真实人头，也不是补表后的实际结果。

## 版本与扩展

`fixtures/data.json` 是完整导入材料，`product.json` 是当前浏览器默认选择。全量导入校验后按规范化内容指纹保存，相同内容不重复建版本。原始事实不原地修改；资料修订形成新版本。`null` 表示明确未观测，不因筛选或合计自动变为0。

`margin_bounds/domain.py` 是字段校验与描述入口；`margin_bounds/identification.py` 负责可行域、识别区间、冲突核对与补表比较；`service.py` 连接版本、选择、求解与存档；`storage.py` 管理不可变数据和保存材料；`web/app.js` 提供浏览、分析与导出交互。保存的材料同时包含原数据、选择与当次求解结果，打开旧材料不重算为新数据。
