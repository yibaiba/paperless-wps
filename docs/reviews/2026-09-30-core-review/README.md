# 核心流程继续 review

基线：`a05d5c3`。本轮只检查与复现，没有修改业务代码、产品、价格、知识或真实数据库。

## 已复现发现

### R1 / P1：未确认功能只在提案中提示，采用后可以正式确认

隔离系统定义包含由“投票”功能控制的角色，项目 `features_confirmed=False`。提案正确返回 `features_unknown`；采用后 `features_confirmed` 仍未包含该系统，但完整检查 `unknowns=0`、`ready_for_confirmation=true`，保存后正式确认返回 HTTP 200。

位置：`backend/src/presales/configuration/projects/planning/roles.py:146-162`。功能选择的待确认事项没有进入共用检查。与上一轮已修复的 Agent 理解来源是不同字段／路径，当前代码仍把未确认功能仅附在提案问题中。应根据项目固定定义修订产生持续的功能确认待办，允许保存草稿，明确确认功能取舍后才能解除。

### R2 / P2：通过提案删除设备没有清理复用引用，后续需求修改失败

生成 32 席设备后，将其加入角色允许复用列表；席位改为 0，生成提案并明确移除多余设备，采用成功且设备已不存在。但 `generation.preferences[].reusable_device_ids` 仍指向它。随后仅修改房间名称的 `requirements_patch` 返回 HTTP 422：“允许复用的设备不存在”。

位置：`backend/src/presales/configuration/projects/planning/application.py:40-54`。这条删除路径自行过滤设备、供货、分配和价格，没有复用普通删除调用的 `remove_generation_references`。应共享删除清理逻辑，在同一原子操作中清理需求来源及复用引用，保留未删除对象的约束。

### R3 / P2：房间固定数量绕过范围校验

已确认角色数量依据为 `scope=room, mode=per_group, factor=1`。项目有房间记录，但该系统 `room_id=None`，没有指定实际归属。生成器仍生成 1 件，角色数量检查返回 `pass`、`required=1`，整体可确认。

位置：`backend/src/presales/configuration/projects/planning/quantities.py:15-17`。固定数量模式直接使用输入 1，绕过范围输入读取，未验证房间范围能否确定。固定数值不等于计算范围已知。房间范围缺失应返回项目资料不足；这不应影响合法的项目级固定数量。

## 复现与排除项

- 从 `git archive a05d5c3` 创建 `/tmp/presales-review-a05d5c3`，不包含工作区 WPS 改动。
- 使用真实 HTTP 业务入口和隔离 SQLite、产品、知识包、价格。没有绕过业务执行或写入真实库。
- `probes.py` 放入该副本的 `backend/tests/configuration/test_next_review.py` 后执行。三条正确行为断言均失败，耗时 1.80 秒；见 `reproduction.log`。这是复现失败的证据，不是验收通过。
- 每项使用 `pytest --timeout=60`，整批使用 `subprocess.run(timeout=60)`。
- 已排除 `generation` 看似局部更新会清空其他字段的疑点：`docs/mcp-proposal-generation-implementation-2026-09-29.md:28` 明确约定提交该域完整值，因此不按现有契约缺陷计入发现。
- 本轮未修复、未跑全量回归或浏览器／桌面 Excel 验收；上述结论限于已复现路径。

## 后续修复

上述 3 项已在 [修复与验证记录](../2026-09-30-core-fixes/README.md) 中闭环；本页保留修复前的复现证据。
