# 托位汇总证据推理台

这是供服务规划人员核对资料、查看业务范围和留存讨论依据的本地应用。当前提供分口径汇总约束与未披露单元，并支持导入、图表、原始记录、保存与重新打开，不将描述值解释为新增分析已经完成。示例为独立生成的虚构数据，不含真实家庭、医疗资料或对外服务凭据。

## 使用环境

使用 Python 3.11.14。页面为原生浏览器界面，数据处理通过本地 HTTP 服务完成，持久化使用应用内置数据库。基础浏览不依赖数值库；研究扩展所需的数值计算和建模库已按 `requirements.txt` 固定所有传递版本。依赖安装及镜像构建只在环境准备时做，启动和检查不访问网络。

```bash
python3 -m pip install -r requirements.txt
python3 -m margin_bounds --host 127.0.0.1 --port 8080
```

浏览器打开本地8080端口。容器方式先准备镜像，运行时不需要其他服务：

```bash
docker build -t margin_bounds:local .
docker run --rm -p 8080:8080 -v margin_bounds-state:/app/.state margin_bounds:local
```

## 验证

```bash
python3 -m unittest discover -s tests -v
```

检查包含真实领域字段、非法导入、边界数据保留、HTTP交互、版本指纹及重启后存档。现有检查只验证已实现的资料浏览行为，不把将来要开发的推断功能冒充现有能力。新增能力需要补充针对统计识别、支持范围和页面一致性的回归。运行检查使用临时状态，不改动资料。

字段语义与现有接口分别见 `docs/data-contract.md` 和 `docs/http.md`。短时操作见 `docs/walkthrough.md`，环境准备不包含在正式操作中。
