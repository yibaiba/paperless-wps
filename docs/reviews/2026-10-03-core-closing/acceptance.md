# 核心业务闭环收口验收（2026-10-03）

本轮三个阶段的代码已交付，软件回归与隔离试点通过；真实业务知识仍未全部确认。所有计数以本次数据库盘点为准。真实客户方案认证、桌面 Excel/WPS 重算，以及 WPS 插件不包含在通过结论中。

## 1. 基线与提交

- 业务数据库：PostgreSQL。459 条来源，410 条已关联、49 条明确阻塞；242 个产品/配置；209 条知识，其中 115 已确认、92 草稿、2 停用；4 个资料包均为草稿，已确认共享知识 0 条。原始计数、ID、修订见 [inventory.json](inventory.json)。
- `40d9294`：共享计算准备与固定版本上下文。
- `4eb4f95`：网页/MCP 共享编辑、独立设备复制、导出事务一致性。
- `7b95774`：统一字段级知识缺口、维护入口、真实证据引用。
- 最终复核追加：MCP 明确业务错误、消除数量验证平方级遍历、精简分支可变字段复制、业务化改单对比、重试成功清除侧栏旧错误。
- 同分支存在并行 WPS 提交；本轮提交不包含 WPS 文件。阶段记录见 [progress.md](progress.md)。

## 2. 问题与修复记录

| 复现条件 | 影响 | 修复与回归 |
| --- | --- | --- |
| 候选请求只提供项目配置，系统 Windows 输入没有重复传给候选接口 | 同一候选在项目通过、候选却资料不足 | 候选和项目共用角色环境/数量/用途准备；Python、ZEN 失败回归均转为通过 |
| 分配、用途检查及方案分支各自准备临时角色 | 分支输入可能不同，临时 ID 难定位 | 共享 RoleContext、固定定义/包/编译版本，保留真实角色映射；分支隔离回归 |
| 前端复制设备直接扩展配置 | 容易带入用途、供货、价格与配套抵扣 | `device_clone` 后端操作；仅创建独立设备和图纸引用，供货/报价待确认 |
| 导出两个文件时第二个失败，或数据库提交响应丢失 | 残留文件或错误删除已提交文件 | 回滚清理未提交产物；用新事务核对幂等回执后处理；文件失败、提交确认丢失回归 |
| MCP 查询不存在修订/并发冲突 | SDK 只返回泛化错误，Agent 无法判断下一步 | 明确的业务失败转 ToolError；真实 stdio 验证修订不存在及 VERSION_CONFLICT |
| 各页分别判断生成/数量/共享缺口 | 维护、项目、Agent 展示不一致 | 同一结构化缺口投影，固定对象修订、字段、依据和处理入口；shared 缺口不阻塞 independent |
| 500 行配置逐设备遍历全部角色计数 | O(设备×角色) 验证开销 | 一次 Counter 汇总；语义不变 |
| 改单预览直接输出完整 JSON | 用户难看到数量改了什么 | 复用“对象/修改前/修改后”表格，详细字段及依据仍可展开 |
| 浏览器离线编辑，顶端重试同步成功 | 侧栏仍显示旧 Failed to fetch | 错误绑定失败时的配置上下文；自动化先失败，修复后通过，并实测重试 |

错误回归证据分别见 context-before、export/clone 阶段日志、mcp-errors-before、inspector-error-before。不能把测试脚手架错误计为业务缺陷。

## 3. 入口、服务、测试与资料缺口

| 业务步骤 | 网页 / MCP | 共享服务与回归 | 真实资料边界 |
| --- | --- | --- | --- |
| 产品更新 | 更新核对台 / catalog_get | catalog_updates、价格并发/修订测试 | 生效日期、规格纠错仍需维护者依据 |
| 知识维护发布 | 产品/系统工作区 / systems_list | definitions、knowledge、gap contract | 发布状态、角色数量、推荐、容量缺口可定位 |
| 需求提交 | 系统需求抽屉 / requirements_patch | setup、requirements | 未提供的客户参数保持未知 |
| 候选/方案 | 候选/方案抽屉 / list_plan | evaluation_context、calculation/context、planning | 只用已选固定包；未发布资料不能正式生成通过 |
| 配套/共享 | 检查与分配 / list_update | demands、allocations、device_usages | 无已确认共享依据时资料不足 |
| 供货报价 | 供货/报价页 / list_get、list_update | editing、quotation Decimal | 已有设备零采购；缺价不等于零价 |
| 改单草稿 | 表单/Univer/导入 / list_update | edit_draft、incremental、web drafts | 人工锁定、旧价、旧版本保护 |
| 保存导出 | 保存/下载 / list_save、list_export | repository、facade、FileArtifacts | 正式保存完整检查；业务确认独立 |

## 4. 双入口对账

浏览器使用生产构建 `5188`、隔离 API `8032`；真实 stdio MCP 直接读取相同隔离数据库。未操作用户原来的 `5176` 页面和业务 API。数据库、测试价格及测试共享依据均在 `outputs/core-closing` 隔离文件中。

| 场景 | 浏览器实际操作 | stdio / 自动化 |
| --- | --- | --- |
| 32→48→16 席 | 填规模、生成、采用、保存 v2、刷新、两文件导出 | 三次改单、每次幂等重试、保存 v5、导出；旧已保存修订不变 |
| 两台独立服务器 | 2 软件 + 2 硬件分别展示 | 两台硬件采购，容量通过；HTTP 与 MCP 检查结果完全一致 |
| 一台共享，无依据 | 2 软件 + 1 硬件，共享资料不足 | sharing=unknown，不冒充通过 |
| 测试共享依据完整 | 1 硬件服务两个系统；删除后两项配套缺失，撤销恢复 | sharing=pass、capacity=pass；仅隔离规则 |
| 客户已有服务器 | 供货面板显示已有 1 台，软件独立采购 | 硬件采购 0；检查与 HTTP 一致 |
| 共享超容量 | memory 160GB > 128GB，明确冲突 | capacity=conflict；有共享依据也不抵消容量冲突 |
| 复制与图纸 | 复制新设备 1→2，撤销/重做；普通图形复制后设备仍 3 项 | 保存 v2 XML 两个图形引用同一 shared 设备，实际硬件仍 1 台 |
| 断网重试 | CDP 断网，保留输入、显示失败，恢复网络后重试同步 | 请求幂等、响应丢失、并发、过期响应另有隔离回归 |
| 报价缺口 | 已知小计与完整总价待确认分别展示 | Decimal/零价/缺价/小数/过期价/价格采用与历史保护回归 |
| 模板导出 | 网页提供设备清单及报价下载链接 | 两份文件哈希匹配；报价 Logo=1、合并区域及 13% 条款保留；扩行/长说明/金额公式测试 |

[protocol-readback.json](protocol-readback.json) 保存实际调用耗时、场景结果、精确 HTTP 对比与产物 ID。`revision` 是草稿修订，导出使用 `project_revision`，文档与 MCP instructions 已写明。

浏览器截图：

- [32/48 改单业务预览](browser-readable-changes.png)
- [生成、保存及模板导出](browser-generation-export.png)
- [独立部署](browser-independent.png)、[共享缺依据](browser-sharing-unknown.png)、[容量冲突](browser-capacity-conflict.png)、[客户已有](browser-existing.png)
- [删除共享设备后的缺件](browser-deleted-server.png)、[拓扑重开](browser-drawing-reopened.png)、[离线失败](browser-offline.png)、[重试恢复](browser-retry-recovered.png)

组合互斥、至少一项、配套循环、换型价格过期、异步响应乱序、服务端提交后响应丢失等边界通过自动化验收；未声称这些边界全部逐个在浏览器手点。真实浏览器覆盖主流程、共享矩阵、撤销恢复、图纸复制及离线重试。

## 5. 自动化结果与复现

- 后端 **576 passed、0 skipped、0 failed**，16 个批次；每项 pytest timeout=60，每批 subprocess timeout=60。真实 PostgreSQL 并发在隔离 schema 中执行并清理。
- 前端 **82 passed**；TypeScript、生产构建通过；现有 Univer 大块构建提示保留。
- 源码 Ruff 检查通过。没有新增依赖、数据库重建或旧快照改写。
- 前端投影 100/500 行均为单值修改 1 个单元格、1 次提交，相同数据 0 次提交。
- 原模板校验值未变，真实导出哈希/Logo/合并/公式记录见 [artifact-validation.json](artifact-validation.json)。桌面 Excel/WPS 显示重算未执行。

从仓库根目录执行 ` .venv/bin/python docs/reviews/2026-10-03-core-closing/verify_backend.py`，读取本地 `.env` 的 PostgreSQL 连接，输出16批记录。前端命令为 `node --test frontend/tests/*.test.mjs` 及 `npm --prefix frontend run build`，外层执行超时60秒。协议核心回归可单独执行 `test_mcp_protocol.py`、`test_proposal_protocol.py`、`test_zen_protocol.py`、`test_mcp_error_contract.py`。本次已启动隔离库的 HTTP/stdio 对账入口为 `verify_protocol.py`，读取本机 browser.json；不会连接业务库。

## 6. 真实知识整理与尚未验收

仅给6条已有关系补充原工作簿单元格引用，经批量预览、修订校验和指纹应用；确认状态不变、固定包不自动升级。资料原文仍可追溯，测试规则未写入业务库。

- 红盾：PCS-1516N/15110N 的 I6/I7 为 Ubuntu 和终端容量描述；RS-MSC100 为 Windows 软件。能否安装/运行及授权范围未获证实，继续待确认。
- 预约：CRIR-1516N F17 支持 Linux、16GB；CRIR-GL20S F18 支持 Linux 部署。这不证明两系统共用成立。
- NF5280M5/M6/A6 的容量区间存在原文，但容量适用哪个业务负载、操作系统和共用条件仍需依据。
- 历史 PCS-GL20S/GL30S、32席/12席报价只作为历史线索，不推导当前红盾必配或兼容结论。
- 可定位缺口清单见 [knowledge-gaps.json](knowledge-gaps.json)，包含配置/角色/关系/字段及维护入口。目标包当前分别31项、67项字段级缺口，不等于98个软件缺陷。

**结论：软件主流程和上述隔离验收通过；真实资料不足仍如实阻止“完整方案已验证”的结论。**真实客户逐项对账和桌面 Excel/WPS 重算保留为独立未验收事项。
