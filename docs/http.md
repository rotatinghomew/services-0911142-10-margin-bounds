# 应用接口

服务绑定本地地址，输入输出为 UTF-8 JSON。错误输入为400，未找到对象为404，超过8MB请求为413。页面与服务端共用口径，前端不另算一份统计答案。

- `GET /health`：检查启动是否成功。
- `GET /api/context`：产品配置、默认数据和已保存材料目录。
- `GET /api/data?revision=版本`：查看完整原始表。
- `GET /api/axes?revision=版本`：查看维度水平与表的单位、期间等口径，供页面构造问题。
- `POST /api/datasets`：传入 `label` 与完整 `data`，校验后返回不可变 `revision`。
- `POST /api/explore`：传入可选的 `revision` 和 `selection`，返回实际选择、资料指纹与描述 `view`。
- `POST /api/analyze`：传入 `revision`、`selection` 和 `query`，返回交叉人群的识别范围。`query` 由 `population`（分母人群条件）与 `outcome`（至少一项结果条件）组成，每项为 `{axis, level}`。响应包含：
  - `status`：`unique`（唯一可确定）、`possible`（仍有多种可能）、`conflict`（材料互相冲突）、`undefined`（分母可为零）、`unsupported`（材料不足以回答）。
  - `numerator`、`denominator`、`share`：各自的 `low`、`high` 与 `unique`；`share` 另有 `defined`。
  - `evidence`：`used`（参与求解的表及作用）、`excluded`（未并入的表与原因）、`rules`（结构零是否生效）、`confidence`（整数格或加权连续格）。
  - `conflicts`：不可行时给出可核对的表组合与共同维度上的分组合计。
  - `alternatives`：逐表去掉后的分子范围，说明哪些约束在起作用。
- `POST /api/compare`：传入 `queries` 与 `baseline`、`current`（各含 `revision` 和 `selection`），返回逐问题的补表前后范围与 `change`（范围缩小、扩大、变为唯一可确定、冲突解除或新增、无变化等）。每行同时列出两边的依赖表。
- `POST /api/notebooks`：传入选择与 `title`；`kind` 为 `identification` 或 `comparison` 时由服务端重新求解后保存证据或比较记录，否则保存描述记录。不接受客户端伪造结果。
- `GET /api/notebooks` 与 `GET /api/notebooks/编号`：目录以及冻结资料、选择和结果。

已有导入、描述和历史读取接口继续供业务使用，含义不变。识别性分析不假定各属性独立，不把边际相乘，也不把区间内某点当成真实人头。
