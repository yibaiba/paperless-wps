# 核心流程继续 review

审查基线：`5414029`。本轮只检查和复现，未修改业务代码、真实资料或数据库。

## 已复现问题

### R1 / P1：通过配套满足的角色会覆盖人工设备关联

两套系统分别生成服务器后，用正常 `requirement_put` 将第一个服务器角色改为关联第二台服务器。写入后读取正确；重新 `list_plan` 并 `proposal_apply` 后，关联恢复成第一台，未保留人工选择。

位置：`backend/src/presales/configuration/projects/planning/accessories.py:207-223`。`bind_fulfilled_roles` 仅保护没有 `generated_origin` 的设备，把“设备最初由生成器创建”当成“该角色关联仍可自动改写”。角色的人工用途关联与设备型号锁定应分别追踪；不一致时保留选择并提示配套关联冲突。

### R2 / P1：提案的待确认需求理解未进入正式检查

在有完整价格的 32 席方案中，记录未确认的 Agent 理解“客户可能要求 48 席”。提案正确返回 `interpretation_unconfirmed`，也未把席位改成 48。但采用后，项目检查 `unknowns=0`、`ready_for_confirmation=true`，保存后的正式确认接口返回 HTTP 200。待确认理解尚未被确认、修正或不采用，却已不影响确认状态。

位置：`backend/src/presales/configuration/projects/planning/generator.py:83-95`；确认入口 `services/lifecycle.py:35-42`。该待办只附在提案 questions 上，没有进入采用后共用检查和确认判断。应持续暴露这个未解决事项，保存草稿与正式确认分开。

### R3 / P2：沿用原分配 ID 的人工修改被认作自动分配而重置

通过支持的 `accessory_remove` + `accessory_link` 原子批次重建同一关联，保留原 ID，改变数量及维护依据。写入和读取成功；重新生成后数量、依据恢复成自动生成值。隔离用例从 `0.5` 恢复成 `1`，维护者依据变成默认说明；这验证接口语义，不作为真实服务器分配口径。

位置：`backend/src/presales/configuration/projects/planning/generator.py:62-77`。当前仅凭 ID 是否等于生成算法的结果决定删除，没有核对该记录之后是否由人工重建。应区分自动生成状态与人工修订，不凭 ID 格式抹掉分配结论。同样的判定也用于 included allocations，但本轮只复现 accessory 路径，不把未验证路径算成额外发现。

## 验证与范围

- 从 `git archive 5414029` 建立 `/tmp/presales-review-5414029`，排除工作区 WPS 开发改动。
- 使用项目真实 HTTP 业务入口和隔离 SQLite、产品、知识、价格；无运行时替身或业务数据库写入。
- `probes.py` 复制到隔离副本 `backend/tests/configuration/test_followup_review.py` 后运行，预期安全行为断言失败，说明问题存在；不是测试通过记录。完整输出见 `reproduction.log`。
- 每项 `pytest --timeout=60`，每批 `subprocess.run(timeout=60)`。
- 本轮没有运行浏览器、全套回归或 Excel/WPS 验收，也未修复上述问题。
