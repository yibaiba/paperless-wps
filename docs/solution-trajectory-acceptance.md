# 真实做单轨迹验收

自动化测试只能证明系统按固定知识和输入稳定计算，不能代替售前人员确认真实方案。业务准确率使用独立的轨迹清单验收：至少 30 条，按项目划分开发集和固定验收集，每条记录核对人、客户需求、标准方案、允许替代项、必要输入、实际方案排序、直接修改次数、资料缺口和可定位证据。

运行：

```bash
PYTHONPATH=scripts .venv/bin/python scripts/solution_trajectory_acceptance.py \
  <轨迹目录>/manifest.json --output <轨迹目录>/report.json
```

清单使用 `schema_version: 1`，`cases` 每项至少包含：

- `id`、`project_id`、`split`（`development` 或 `acceptance`）、`reviewed_by`、`evidence_confirmed`。
- `requirements`：本次客户需求及确认值。
- `expected`：`standard_solution_id`、`alternative_solution_ids`、`required_inputs`、`knowledge_gap`。
- `observed`：`ranked_solution_ids`、`direct_corrections`。
- `evidence`：相对清单目录的 `path`、文件 `sha256` 和工作表／行号／资料段落 `locator`。

校验器拒绝未确认、证据变化、跨集合项目、重复轨迹和改编号补数，并分别输出开发集和固定验收集的可判定率、Top-1、Top-3、错误直接修改率及资料不足率。仓库中的单元测试仅验证门禁行为，不是业务轨迹，不计入 30 条验收。

当前没有收到 30 条经业务人员确认的真实做单轨迹，因此不能公布真实自动生成准确率；软件流程、37 项历史案例对账和隔离规则测试仍按各自报告单独记录。
