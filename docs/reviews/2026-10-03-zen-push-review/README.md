# ZEN 提交后复核

## 范围与结论

复核提交范围：`28c244d..6490b65`，重点检查决策编译与固定版本、必选和互斥组合、候选检查、方案生成、旧项目兼容以及知识包试查状态展示。本次为实现者代码复核，不是新增独立审计。

发现并复现 1 项问题，已修复。修复后在上述重点范围内未发现其他需要阻断交付的问题；本记录不代表全仓库无缺陷或真实业务方案已认证。

## [P2] 固定旧组合修订的知识包在全局规则更新后无法生成方案

触发：知识包发布时固定组合规则 v1（必选），随后全局规则更新到 v2（互斥），项目继续采用原知识包。

项目检查正确返回包内的 v1，但 `projects/planning/combinations.py` 随后从全局知识快照查找同一旧修订。快照只有 v2，导致 `StopIteration` 被生成器转换成 `RuntimeError`，`list_plan` 无法返回提案。直接从最新规则取值还会错误改变旧包的业务含义。

修复：组合展开直接使用检查结果携带的组合类型。该结果已按项目选择的知识包解析固定修订，无需再次查找全局关系，也不添加回退或改写历史快照。

回归：扩展原必选角色生成测试，对比全局规则未变化及已更新为互斥两种情况。实际调用清单工具接口生成、采用、读取提案，验证最终组合仍为 `combination_require_all`、修订 1、状态 pass，且配件设备数量为 1。修复前新增场景失败、原场景通过；修复后均通过。

## 本轮验证

所有后端用例设置 `--timeout=60`，每批另由 `subprocess.run(timeout=60)` 设置硬超时；使用隔离测试库。

| 批次 | 结果 |
| --- | --- |
| `test_zen_combinations.py` | 16 passed，4.87 秒 |
| `decisions/test_runtime.py`、`test_decision_versions.py`、`test_package_trials.py` | 56 passed，4.78 秒 |
| `test_zen_protocol.py`、`test_package_knowledge_scope.py`、`test_proposal_generation.py` | 10 passed，8.03 秒 |

合计 82 项通过，无跳过。协议批次包含现有真实 stdio MCP 回归。

`npm run build` 在 60 秒命令超时内通过 TypeScript 检查与生产构建。仍保留既存的报价工作表 chunk 大包提示。本次后端修复未变更界面，未重新执行浏览器流程；此前试查页面的隔离浏览器证据见 `../2026-10-03-package-trial-status/README.md`。

修改的 Python 文件通过 Ruff；补丁通过 `git diff --check`。真实客户清单及桌面 Excel/WPS 未纳入本轮验收。

## 提交与推送

原三个提交已推送至 `origin/main`：`c509627`、`ef8b904`、`6490b65`。本次修复、回归测试及此记录作为后续提交推送。此前已有的四个未跟踪 review 目录未纳入提交，也未修改。
