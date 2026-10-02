# ZEN 实际接入与角色别名重复占用复审

> 以下为修复前的历史审查记录；修复与最终验收见 [修复报告](../2026-10-02-role-alias-fix/README.md)。

基线 `0acd93a`。本轮只读检查应用代码，隔离复现并记录问题，未修改业务逻辑或业务库。此前 422 问题仍未修复。

## ZEN 已实际使用

- HTTP：`backend/src/presales/main.py:57` 初始化真实 `ZenQuantityEngine(zen.ZenEngine())`，通过依赖注入进入项目、清单和编辑服务。
- stdio MCP：`backend/src/presales/mcp_server.py:126` 同样初始化该真实引擎。
- 角色数量：`configuration/projects/planning/quantities.py:56` 调用 `engine.calculate`。
- 配套数量：计算语义 v3 的 `calculation/demands.py` 调用 `accessory_demands.calculated_demand`；后者调用同一数量引擎。
- `rules/engine.py:47` 执行真实 GoRules 决策图，开启 trace。当前只包含每单位乘系数、容量向上取整、非零输入下固定数量三种受控表达式，不是让任意知识关系都经过 ZEN。
- 候选、环境、共享、分配等由 Python 业务代码判断；报价金额由 Decimal 计算。

本机已安装 `zen-engine 0.53.0`。`zen-runtime.json` 保存直接运行真实引擎的结果与 trace 存在性：32×2=64、ceil(33/16)=3、固定量1、小数0.1×0.2=0.02。不是模拟执行，也没有连接生产业务数据库。

`zen-regression.log`：真实规则引擎与方案生成测试 **18 passed**。默认测试应用没有注入假数量引擎。以上确认代码及隔离运行接通；未对用户正在运行的常驻进程作请求跟踪。

## 新确认问题：[P2] 已确认角色别名仍重复占用批量设备

这是此前生成 422 之后的第二层错误，不能只改角色关联表示而忽略它。

复现用合法的 `allocations` 数量分配字段，两个角色均通过已确认的 fulfilled_by 指向同一配套需求。实际只有一笔配套分配，共2件，配套分配检查未报超量；`/api/configuration/check` 返回200，但角色设备总量检查把两个别名各自的2件累加为4件，误报“角色分配总量超过设备数量，不能重复抵扣”。数量为1的对照组不报错。

根因：`backend/src/presales/configuration/projects/calculation/role_allocations.py:15-18` 先把角色分配计入 `counts`，到第28-30行才跳过已确认、实际满足的角色别名。虽然跳过了单个角色的数量检查，最后的 `device_allocation_checks` 仍用已重复累计的数量判断冲突。

ZEN 对本需求的计算仍为2，错误发生在后续 Python 设备占用汇总。

## 验证与边界

- `reproduction.py` 复制为隔离副本中的 `backend/tests/configuration/test_alias_quantity_checks.py`。
- 依赖上一轮 `docs/reviews/2026-10-02-role-alias-quantity/reproduction.py`，复制为同一隔离副本中的 `backend/tests/configuration/test_fulfilled_role_quantity_review.py`。
- 仅执行新用例：`alias-reproduction.log` 为 **1 passed、1 failed**；失败点是多算数量的断言，不是输入校验或资料建立失败。
- 基于 `git archive HEAD` 的冻结源码副本、隔离 SQLite fixtures；每项 `pytest --timeout=60`，每批 `subprocess.run(timeout=60)`。
- 没有修改常规测试目录，没有修改应用代码，两个问题均未修复。没有执行全量后端、浏览器、PostgreSQL 并发或桌面 Excel/WPS 验收。
