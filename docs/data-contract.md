# 资料与统计口径

`axes` 给出全局交叉维度及离散水平，`margins.coordinates` 描述某张表一个交叉单元，不含的维度表示求和边际。`releases` 规定单位、资料轮次、期间、总体和去重方式；人数与人次或不同期间不因维度重合而可拼接。`persons` 的 `value` 是非负整数，`weighted` 为非负实数，`tolerance` 是允许的公开取整误差半宽。`structural_zeros` 是明确不可能的交叉组合，并非未披露格子均为零。`supplement` 累积第一轮可用材料，需先检查兼容性；原始表不保证永远一致。比例指标的分母由查询人群条件决定，不自动取总人数；分母可为零时需解释未定义。现行展示只核对各表总计，未进行可行域求解。

## 原始表

- `releases`：9条示例，主键为 `table`。字段：`table`, `release`, `unit`, `start`, `stop`, `universe`, `counting`, `dimensions`, `tolerance`。
- `margins`：34条示例，主键为 `cell`。字段：`cell`, `table`, `coordinates`, `value`。
- `axes`：4条示例，主键为 `axis`。字段：`axis`, `levels`。
- `structural_zeros`：1条示例，主键为 `rule`。字段：`rule`, `coordinates`。

## 版本与扩展

`fixtures/data.json` 是完整导入材料，`product.json` 是当前浏览器默认选择。全量导入校验后按规范化内容指纹保存，相同内容不重复建版本。原始事实不原地修改；资料修订形成新版本。`null` 表示明确未观测，不因筛选或合计自动变为0。

`margin_bounds/domain.py` 是领域入口，现阶段仅做字段校验及资料描述；`service.py` 连接范围选择、数据版本与服务端计算后的存档；`storage.py` 管理不可变数据和保存材料；`web/app.js` 提供浏览和导出交互。保存的材料同时包含原数据与选择，打开旧材料不重算为新数据。新增分析不限内部组织方式，但不能丢失现有原始记录核对与历史材料读取能力。统计方法、模型选择和业务结论没有预设答案。
