# WPS 接通统一 ZEN 搭配引擎（2026-10-08）

## 交付边界

WPS 的下一步编辑现在复用项目配置内核的固定定义、知识包、ZEN 决策包、组合检查和分支生成，不维护 WPS 专用配套顺序。明确输入先完成当前产品；之后的空白行才处理由该产品触发的第一个未完成组合。

本轮没有发布知识、没有自动升级历史项目、没有引入模型，也没有把覆盖式浮层描述为原生单元格补全。`python-v3` 项目仍可按明确型号或名称完成基础补全；空白行业务搭配不会接管 Tab，并提示先显式预览 ZEN 升级。

## 决策链

```text
工作簿本地状态
  -> 临时项目配置（不落库）
  -> 固定 definition / knowledge / decision bundle
  -> ZEN combination_checks
  -> 第一个相关未完成组合
  -> 共享 group_branches
  -> WPS 行定位、灰字、选择或差异预览
```

`require_all` 每次补一个尚未满足的目标；`require_any` 返回候选分支并要求明确选择；`exclude` 只报告冲突，不生成写入。草稿规则、未知作用范围和证据不足返回问题。已有设备仍必须通过共享规划器的用途、容量、环境与供货检查；需求量不会改写库存量。

每个组合建议都带 `planning_origin=zen_combination`、检查 ID、规则 ID/修订、作用范围和目标 ID。任务窗格同时显示计算版本、决策运行时、固定 bundle 和本次组合检查。内联响应只带当前建议引用的组合，面板响应带当前业务范围的完整组合检查。

## 历史项目显式升级

同步请求新增 `upgrade_decisions`，默认 `false`。只有任务窗格“预览升级 ZEN”会发送 `true`：

1. 预览基于当前固定知识编译 bundle，返回运行时、bundle、业务差异和问题，不修改项目或草稿修订。
2. 确认同步携带原预览指纹、绑定/草稿/项目期望修订及 `operation_id`。
3. 服务端重新生成并核对同一 bundle，随后检查、保存项目并更新工作簿绑定。
4. 同一 `operation_id` 重试返回原回执；补全接口显式拒绝升级标记。

服务端必须先部署，插件后升级。旧插件不发送字段，保持原同步语义。

## 红盾组合维护预览

`scripts/wps_redshield_review_bundle.py` 的 `review.json` 新增 `zen_combination_review`：

- 带话筒升降器、话筒模块和会议主机形成 `require_all` 草稿；会议主机数量、容量、级联和主席/代表分配仍列为待确认。
- Windows 服务端软件与目录 Ubuntu 主机的关系保持阻塞，不生成确定采购组合。
- 终端到客户端等单一配套继续使用现有 accessory，不为 ZEN 重复建规则。
- 草稿携带固定规则 ID、预期修订、来源定位与证据哈希；脚本仍只生成维护差异并回滚验证，不提供发布入口。

运行只读审计：

```sh
PYTHONPATH=backend/src:scripts .venv/bin/python scripts/zen_business_audit.py \
  --output /tmp/zen-business-audit.json
```

生成红盾复核包：

```sh
PYTHONPATH=backend/src:scripts .venv/bin/python scripts/wps_redshield_review_bundle.py \
  --output /tmp/wps-redshield-zen-review
```

当前数据库审计时若仍为 0 条 combination、历史项目仍为 `python-v3`，代码接通不等于红盾硬件推荐已经获得业务确认。必须由业务人员复核草稿、通过现有维护流程显式应用和发布，再逐项目预览升级。

## 验收状态

自动化覆盖组合增量、固定运行时摘要、升级预览不改草稿修订、升级提交、重复提交和补全接口禁止升级。浏览器组件与构建通过不替代真机。

以下仍保持未验收：红盾组合草稿的业务确认、三类模板至少 30 条独立轨迹、macOS WPS `12.1.28496`、售前 Windows 实际构建、真实网络 p95、输入至灰字 800ms 及宿主写入 100ms。
