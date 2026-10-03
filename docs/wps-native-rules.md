# WPS 原生补全与业务规则交付记录

日期：2026-10-04。对应本轮批准的“WPS 原生补全与业务规则优化计划”。

## 交付与边界

本轮交付规则、协议、回放评分器及独立能力记录包；未接入新模型，未训练模型，未启用原生补全。既有输入浮层只消费新决策，不新增模拟原生输入的路径。

Cursor 的参考点是根据近期编辑和上下文预测编辑位置，而不是固定跳下一行；参见 [官方 Tab 说明](https://cursor.com/help/ai-features/tab)。WPS 的 [OnKey 文档](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/et/Application/member/OnKey) 明确省略 Procedure 恢复原键行为，[事件文档](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/addin-api/event/et-event) 提供 SheetChange 等事件；这些文档并不能证明可以读取未提交编辑文本、光标、IME 状态或绘制原生灰字。

## 规则和接口

- 当前行明确角色优先；无绑定时从固定知识中的适用角色识别，多个角色给出具体选择。名称、型号、配置名及 `status: confirmed` 的别名参与检索；草稿别名不参与，实时目录变化不穿透固定快照。
- 空白查询先解决最近修改的相关容量/用途/配套问题，再考虑当前系统必要需求。未选可选需求跳过；缺资料返回待确认；必要需求满足后停止。
- 复用仍由共享规划器做环境、容量、用途和供货检查。唯一无需新增采购的适用方案优先；不改变现有库存数，不推断跨房间共享依据。
- `/api/wps/completion/preview` 仍是 Bearer 保护的只读计算。新增 `primary_suggestion_id`、`decision: {status, reason_code}` 和可空 `next_target`。
- `decision.status` 为 `ready`、`choice_required`、`confirmation_required`、`satisfied`、`no_match` 或 `dismissed`。主建议不等于直接写入权限，仍必须检查 `applicable`、`acceptance` 和当前目标。
- `next_target` 来自实际差异，含位置、字段、原值、已存在的行身份、本地修订和上下文指纹。纯业务关联可以无目标。接受后不无条件 `row + 1`；定位前核对版本/原值/身份，移动后重新预览。
- 近期操作记录增加行身份、位置、顺序和前后业务变化。已观察的宿主数量提交进入增量上下文，产品输入文本不伪装成已确认行。手工数量事件仅在当前行索引会话内有效，结构变化清除位置相关记录；持久化接受/撤销事件仍保存在原元数据日志。
- 撤销和明确 Esc 拒绝按业务动作与相关上下文摘要抑制重复建议，普通导航不作为拒绝。业务条件变化后允许重新计算；不依赖仅含光标位置的建议 ID。

## 自动化与可重复检查

后端分批执行，每批硬超时 60 秒。新增测试集中在 `test_wps_typed_intent.py`、`test_wps_edit_decision.py`、`test_edit_decision_rules.py`；保留 next-edits、reuse、business-context、dependency-scope、sync 和目录序列回归。

```sh
env LC_ALL=C perl -e 'alarm 60; exec @ARGV' .venv/bin/pytest -q backend/tests/configuration/test_wps_typed_intent.py backend/tests/configuration/test_wps_edit_decision.py backend/tests/configuration/test_edit_decision_rules.py scripts/test_wps_business_replay.py
# 在 wps-addin 目录
env LC_ALL=C perl -e 'alarm 60; exec @ARGV' npm test
env LC_ALL=C perl -e 'alarm 60; exec @ARGV' npm run build
```

本轮相关后端回归批次通过（64 项/28.60 秒，含规划、供货、上下文及回放；随后主建议精确匹配与评分补测 32 项/6.61 秒）。前端 112 项通过，包括原值、跨列目标、IME、重复事件、日志恢复及原生 Tab 交还的替身测试。构建通过。测试集有交叠，不能把批次数量相加当成独立业务轨迹。

浏览器隔离组件验证：有主建议及其他候选时首次 Tab 判为 apply；同型号多配置判为 expand；异行建议判为 locate，页面明确实际工作簿写入为 0。它不连接 WPS，不证明宿主焦点、原生按键或写入延迟。1,000 行索引回归只证明不增加全表宿主读取，不是 p95 测量。

## 原生能力矩阵

独立包位于 `wps-native-probe/`，复现步骤及 JSON 记录格式见其 README。记录器不会自行把事件存在判为原生能力通过；不使用模拟键入、候选预写后撤回或系统键盘钩子。

| 能力 | macOS WPS 12.1.28496 | Windows WPS（构建未登记） |
|---|---|---|
| 读取原生未提交文本 | 未验证 | 未验证 |
| 读取光标位置、IME 状态 | 未验证 | 未验证 |
| 无写入、无抢焦点的原生灰字 | 未验证 | 未验证 |
| 编辑中一次 Tab 接受并恢复 | 未验证 | 未验证 |
| Esc、公式、中文输入法 | 未验证 | 未验证 |
| 滚动缩放、多窗口 | 未验证 | 未验证 |
| 连续 20 次接受、100 次无候选 Tab | 未验证 | 未验证 |
| API p95 ≤500ms、宿主写入 p95 ≤100ms | 未测量 | 未测量 |

当前自动化环境没有可用的 WPS 原生控制接口，Windows 真机也未提供。此处是“未验证”，不是推断“不支持”。原生接入只能在完整实测通过后提交；失败时交付规则内核并明确宿主阻塞，不切回浮层冒充成功。

## 仍缺的验收材料

尚未建立三类经业务确认的模板及至少 30 条独立轨迹的固定验收集；红盾部署、授权和容量依据尚未在本轮获得业务确认。既有 40 例仍仅算目录序列回归，不能声称 Top-1/Top-3 或真实灰字覆盖率达标。

解除条件：提供确认过的资料、按项目分开的开发/验收轨迹，以及 macOS/Windows 实际构建的原生探针记录和录像。回放脚本现在可核对 `expected_decision`，区分真正满足和缺证据，也不会把“需要选择/定位/预览”计入一次 Tab 成功。
