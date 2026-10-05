# 设备用途与分配统一收口

日期：2026-10-05。实施基线：`5cca761`。只修改核心业务文件，排除并行 WPS 改动。

## 第一阶段：计算基础

在项目计算模块建立请求内不可变用途投影。实际分配、耗用配套、单台共用和角色引用分别表达；角色引用保留所有匹配的上级需求，不新增占量。过期配套关联作为未解决分配显示，不能当作可用库存。已含内容保持独立满足来源。

投影提供按设备查询及统一可用量查询，不写数据库、不修改输入；序列化后得到独立视图。设备、系统、角色、配套和分配 ID 沿用原值。

第一阶段 12 项纯业务用例覆盖共同数量预算、分数数量、角色引用去重、多上级和多需求、资源分摊缺口、单台共用、单用途不误标共用、碎片关联、深层不可变、记录排列不影响结果，以及过期分配追溯。尚未切换运行入口，后续阶段接入同一投影并移除重复计算。

## 同机性能基线

复用既有隔离场景与脚本，每组合 9 次，表中为中位数。脚本全批设置 60 秒硬超时；不使用业务库。

| 行数 | 决策路径 | 完整检查 ms | 查询数 | 备注编辑 ms |
| --- | --- | ---: | ---: | ---: |
| 100 | Python | 55.23 | 14 | 64.90 |
| 100 | ZEN | 61.90 | 18 | 65.57 |
| 500 | Python | 278.62 | 14 | 386.16 |
| 500 | ZEN | 309.18 | 18 | 416.05 |

原始数据：`data/verification/usage-unification-20261005/performance-before.json`。备注编辑不调用完整检查、响应不包含知识快照，作为后续性能验收约束。

后续阶段记录如下。以上数据是开工时的测量，最终比较使用后文同机重新测量的基线，不混用不同轮次。

## 第二阶段：运行入口收口与复核

完整检查、保存、配套应用、候选试查和生成分支已接入同一用途投影。删除当前语义 3 的旧角色数量汇总、单独容量分摊内核；语义 1/2 原路径保留。生成分支使用自身配置重建投影；已有服务器复用时同时考虑直接用途和配套占量。候选适用通过与相关用途检查分开返回，不表示整套认证。

修复前后差异均为已复现的缺陷：

| 原行为 | 当前结果与依据 |
| --- | --- |
| 直接用途与配套分别占满同一批设备 | 共同预算，返回 `device_quantity_overallocated` 与所有分配组 |
| 3 台批次、两个需求各分配 1 台时借用全批容量 | 各组只用实际分配的 1 台容量；增加库存不改变它们的容量 |
| 角色引用只保留最后匹配需求 | 保留所有匹配、实际承载组和引用量，不重复计量 |
| 同一资源复制到多个独立承载组 | `resource_split_missing`，保留原需求与对象，不猜测分摊 |
| 已有关联但需求用途缺失时遗漏占量 | 保留分配记录和占量，同时返回资料不足 |
| 旧结果缺少新明细时临时用另一算法补算 | 原记录不改写，明确标为待重新检查 |

复核同时修正了物理分配组 ID 与已有页面问题分组 ID 的命名冲突；新增 `allocation_group_id(s)`，避免覆盖 `group_id`。前端与 MCP 用结构化动作定位，不解析消息文字。

本次干净回归为三批 40/41/51 项，共 132 项通过（各项与各批 60 秒硬超时）；覆盖真实业务 API、草稿、旧快照、配套容量、Python/ZEN、生成分支、保护人工项与候选。日志位于 `data/verification/usage-unification-20261005/entrypoints-tests.log`、`regression-1.log`、`regression-2.log`。未计入旧轮次重复测试。

真实 stdio MCP 的隔离容量流程通过：读取原结果、3 台改 5 台不改变两个需求容量、修改需求、删除服务器后两个缺项重现、恢复检查点、保存 v2、读取 v1/v2、导出真实清单 XLSX。每步与 HTTP 对账；回执重复提交无重复设备。测试配置和确认知识仅存在隔离 SQLite，未写业务库。报告 `data/verification/usage-unification-20261005/alias-stdio.json`。

轻量编辑复用未变化用途，移除检查结果全量深拷贝；不可变投影序列化采用单次调用缓存。完整检查的明细增加了计算成本，后续阶段以相同数据记录成本，不以代码改动推断性能改善。

## 第三阶段：用途明细、历史采用与复核

设备详情增加“用途与分配”，使用服务端结果显示部署量、独立分配、共用占量、未分配、超量、实际消费者、所有角色引用和容量承担范围。供货分配单独展示；引用标为“不重复计量”。问题使用现有结构化动作打开需求、配套、供货及知识维护入口。清单、图纸选中设备复用同一详情。

新增展示、类型及映射放入项目模块内的独立文件。现有项目页和草稿同步 Hook 已超过目标行数，本轮保留其状态编排结构，只复用原动作处理和补齐检查点历史；没有为了行数将耦合状态拆成另一套管理层。业务分配判断全部留在统一后端投影，前端映射仅处理名称与显示。

`list_get` 增加分页 `device_usages` 视图及设备过滤，摘要包含投影版本与指纹。当前语义 3 旧结果缺少明细时，网页和 MCP 都要求显式重新检查；历史语义 1/2 保持原路径。

复核修复三处历史行为：

1. 新增用途追溯字段原本被误列为采购变化。采购比较现在忽略纯追溯字段，并按角色、用途和配套需求 ID 稳定排序，记录排列不制造采购变化；实际数量、产品、供货和资料变化仍显示。
2. 配置未变、检查已变时，原网页不产生草稿检查点，刷新会丢失采用结果且不能撤销。现在创建工作草稿保留原检查；显式采用预览调用 `/work-drafts/{id}/recheck`，复用幂等、版本及固定资料检查，保存独立检查点。撤销和重做恢复整个检查点，前端会话历史标识不进入 `Configuration`。普通检查入口发现旧用途版本时也先进入差异预览。
3. 保存或检查等待期间发生检查点采用/撤销，配置文字可以保持相同。原请求只比较配置，可能将早先检查覆盖到后来检查点。现在同时比较发起时的配置及检查点标识；保存回执只确认发起时的标识，后续修改仍保持未发布。新增三项请求竞态回归，修复前失败，修复后通过。

这三项均先复现，再补回归。拒绝过期预览、重复请求、响应丢失重试、无事实变化的撤销和重做均已测试。不通过回退算法修补旧结果。工作草稿读取只增加版本状态，不重新计算。

最终复核还修正了旧语义 1/2 的说明：这些历史计算本来就不产生新版用途明细，不能提供一个重新检查后仍无明细的按钮。页面现在明确说明历史限制及现有升级预览入口，保留原计算；语义 3 缺少明细仍提供显式预览。该差异补了失败回归及当前语义的正常入口回归。

第三阶段首轮后端回归 33 项通过；其中 PostgreSQL 用例首次因未传连接跳过，随后在独立随机 schema 执行相关批次，6 项全部通过，包括该用例及真实并发保存/进程重开幂等。最后新增消费者记录顺序的失败回归，修复后重跑历史用例 5 项通过。日志为 `usage-stage3-tests.log`、`usage-postgres.log`、`usage-history-final.log`。最终前端两批 53/10 项，共 63 项通过（`frontend-tests-final.log`、`frontend-sheet-final.log`）；TypeScript 与生产构建通过（`frontend-build-final.log`），保留既有 Univer 大包告警，未改依赖或插件。相关后端文件使用 `backend/pyproject.toml` 的 Ruff 配置检查通过。

### 浏览器与真实 stdio 对账

全部操作在隔离 SQLite 或 PostgreSQL schema 中完成，未写入业务库。

| 验收 | 实际结果 |
| --- | --- |
| 浏览器分配与容量 | 批次 3 台、两个需求各 1 台；改为 5 台后分配仍 2，未分配 3，每需求容量仍 128GB；150GB 需求冲突，改为 100GB 后通过该容量检查 |
| 删除、撤销、重做与恢复 | 删除服务器后两处配套缺项重现，撤销恢复引用；数量修改撤销/重做一致，刷新恢复草稿；网页继续明确选择报价资料，保存并重开 v3，真实 stdio 读取与网页 HTTP 对账一致 |
| 历史检查采用 | 旧 v4 显示待检查；预览 8 项用途变化，显式采用、撤销、重做、刷新恢复新检查；旧保存记录与原隔离副本 SHA256 相同 |
| MCP 分页与过滤 | 同一保存/草稿输入，分页及按设备查询与 HTTP 完全一致；消费者、分配组、容量、检查、采购及金额一致 |
| 已有、采购、待定 | 部署 5 台，已有 1、采购 2、待定 2；单价 12.345，采购金额 24.69；整单仍因未完成项为待确认，不能冒充完整总价 |
| 轻量编辑 | 价格/供货更新复用用途指纹，不改变产品或知识；保存重开、导出两种实际 XLSX 通过 |
| 37 行参考案例 v1 | 真实 MCP 执行需求、部分生成、采用、案例映射、20→21 话筒、检查、保存、导出；27 个设备，两系统分线盒需求分别 11/10，缺量分别 1/0；网页显示相同结果 |
| 37 行网页改单 v2 | 网页从保存版本建立独立草稿，生成并明确采用部分方案；选择 BE6/T 补 1 个并明确供货为本次采购。28 个设备，两组缺量均为 0；撤销恢复 27 个/缺量 1，重做恢复 28 个/缺量 0。保存 v2、刷新、真实 stdio 与原生 HTTP 对账，导出两种文件并下载报价通过 |

37 项全部返回明确原因；v1 有 27 个实际设备对象，网页改单 v2 有 28 个，对账结论均为 **35 项资料不足、2 项功能未启用**。这是对账软件流程通过，不能说 37 项业务搭配已确认。缺口包括旧三代 C5 无唯一当前配置、部分系统角色/候选、容量、价格、供货及共享依据，保留实际原因，不从旧案例共同出现推断必配或兼容。

报告位于本次隔离目录：`alias-stdio.json`、`usage-stdio-final.json`、`browser-stdio.json`、`reference37-report/stdio-report.json`、`reference37-usage.json`、`reference37-browser-stdio.json`、`browser-reference37-steps.json`、`history-protection.json`。原始文件和导出保留在该目录；截图为本文同目录的 `usage-details.png`、`usage-summary.png`、`usage-history-restored.png`、`usage-history-preview.png`、`usage-reference37.png`、`usage-reference37-export.png`、`usage-export.png`。

`export-structure.json` 核对协议 v4 与网页 v3 的实际导出；公司模板校验值保持 `1209dba11ed73324ef1fbb2e361c9288049f07d8f8d3da9182152b6337d8800e`。`reference37-browser-exports.json` 核对网页 v2：设备清单 29 行（含表头）、报价 65 行/10 列/54 个公式/1 个 Logo/26 个合并区域，下载文件 SHA256 与服务端产物一致。保留缺价合计“待确认”、金额 ROUND 公式与 13% 税运说明；未作为桌面 Excel/WPS 验收。

## 最终性能比较与限制

同机、相同固定输入、每组合 9 次中位数。旧代码来自 `5cca761` 的只读副本。原始数据为 `performance-before-final.json` 与 `performance-after-memo.json`；后台同时存在其他任务，墙钟波动同时记录 CPU 时间，不据单次结果推断提升。

| 行数 / 路径 | 完整检查旧→新 ms | CPU 旧→新 ms | 备注旧→新 ms | 新检查查询数 | 新 DB ms | 新增量投影及编码 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 / Python | 99.12→171.84 | 86.70→135.16 | 134.36→78.41 | 14 | 0.91 | 5.83 |
| 100 / ZEN | 84.80→133.65 | 80.13→115.56 | 80.28→51.65 | 18 | 0.75 | 4.52 |
| 500 / Python | 436.19→722.89 | 353.09→619.03 | 549.12→362.72 | 14 | 0.68 | 30.61 |
| 500 / ZEN | 458.18→841.62 | 415.58→649.76 | 547.47→375.79 | 18 | 1.08 | 28.02 |

备注编辑不触发完整检查/全量 ZEN，查询 1 次，只返回 1 个设备变化及约 390 字节增量，不传知识快照。完整查询数不随相同配置设备从 100 增至 500 增长。

**完整检查变慢，未宣称全流程加速。** 已定位主要新增成本为不可变分配/引用明细、追溯序列化及指纹；数据库查询未增长。剖析还发现轻量编辑原本全量深拷贝检查结果，已移除；序列化在单次投影内复用对象。新完整检查承担原来遗漏的分配核对及详细追溯，保留这些成本，不删检查或截断数据来达成指标。剖析保留在 `profile.stats`、`profile-final.stats`。

生产模式、仅开启现有性能标记的真实浏览器测量：

| 业务行数 | 模块加载 ms | 初始化 ms | 首次渲染 ms | 单值投影 ms | 初始化 / 单值写入 | 实际备注 HTTP ms |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 100 | 1176.70 | 113.20 | 792.70 | 2.70 | 1 次 / 1 单元格 | 588.54 |
| 500 | 855.10 | 85.70 | 585.40 | 19.80 | 1 次 / 1 单元格 | 3384.30 |

页签切回没有新建实例，相同投影零写入。两组包含分区及合计，工作表实际 105/505 行；单次测量受系统负载影响，不能得出 500 行比 100 行加载更快。备注 HTTP 包含草稿持久化及网络，与单元格投影分开，不能拿 19.80ms 当作完整编辑响应。纯差异函数 100/500 行分别 0.062/0.216ms。原始记录仅保存行数、耗时、写入次数与字节数，不保存客户或价格。

## 可复现入口

所有验证命令从项目根目录执行。下列脚本内部有 60 秒硬超时，数据库和 API 必须显式指向隔离副本：

容量/引用合成场景可以从空目录重建，不依赖业务库。以下命令创建新的验收副本，若目标已存在，种子测试会明确拒绝覆盖：

```sh
ALIAS_BROWSER_FIXTURE="$PWD/data/verification/usage-unification-rerun/isolated.sqlite" \
  .venv/bin/python -c 'import subprocess; subprocess.run([".venv/bin/pytest", "backend/tests/configuration/test_alias_capacity_partitions.py::test_seed_optional_alias_database", "--timeout=60", "--timeout-method=signal", "-q"], timeout=60, check=True)'
```

在单独终端启动指向该副本的 HTTP 服务，然后依次执行 `alias_capacity.py` 和 `usage_stdio.py`。首个脚本产生 `alias-stdio.json`，第二个脚本读取它并根据当前已保存修订建立独立改单草稿；重复执行不会固定覆盖某个旧版本。

```sh
DATABASE_URL="sqlite:///$PWD/data/verification/usage-unification-rerun/isolated.sqlite" \
PRESALES_ARTIFACT_DIR="$PWD/data/verification/usage-unification-rerun/artifacts" \
PRESALES_WEB_ORIGIN="http://127.0.0.1:5186" \
  .venv/bin/uvicorn presales.main:create_app --factory --host 127.0.0.1 --port 8033

.venv/bin/python scripts/verification/alias_capacity.py \
  --database data/verification/usage-unification-rerun/isolated.sqlite \
  --artifacts data/verification/usage-unification-rerun/artifacts \
  --api http://127.0.0.1:8033 --web-origin http://127.0.0.1:5186 \
  --output data/verification/usage-unification-rerun/alias-stdio.json

.venv/bin/python scripts/verification/usage_stdio.py \
  --database data/verification/usage-unification-rerun/isolated.sqlite \
  --artifacts data/verification/usage-unification-rerun/artifacts \
  --api http://127.0.0.1:8033 --web-origin http://127.0.0.1:5186 \
  --output data/verification/usage-unification-rerun/usage-stdio.json
```

以上从空目录种子至真实 stdio 的命令已按顺序执行通过；重新建立的隔离目录包含 `alias_capacity.log`、`usage_stdio.log` 及各自 JSON 回执。

本轮已准备的资料副本可直接重跑以下对账。37 项场景依赖本轮固定业务资料副本及报告中列出的项目 ID，不能用合成种子替代这些资料：

```sh
.venv/bin/python scripts/verification/usage_stdio.py \
  --database data/verification/usage-unification-20261005/isolated.sqlite \
  --artifacts data/verification/usage-unification-20261005/artifacts \
  --api http://127.0.0.1:8030 --web-origin http://127.0.0.1:5186 \
  --output data/verification/usage-unification-20261005/usage-stdio-rerun.json

.venv/bin/python scripts/verification/usage_stdio.py \
  --database data/verification/usage-unification-20261005/reference37.sqlite \
  --artifacts data/verification/usage-unification-20261005/reference-artifacts \
  --api http://127.0.0.1:8031 --web-origin http://127.0.0.1:5187 \
  --project-id e35a749e-16e9-4667-949a-e0dff821bfb6 --revision 1 \
  --output data/verification/usage-unification-20261005/reference37-rerun.json

.venv/bin/python scripts/verification/usage_stdio.py \
  --database data/verification/usage-unification-20261005/reference37.sqlite \
  --artifacts data/verification/usage-unification-20261005/reference-artifacts \
  --api http://127.0.0.1:8031 --web-origin http://127.0.0.1:5187 \
  --project-id e35a749e-16e9-4667-949a-e0dff821bfb6 --revision 2 \
  --output data/verification/usage-unification-20261005/reference37-browser-rerun.json
```

`usage_performance.py` 在显式提供的隔离 API 上创建 100/500 行配置；计算测量沿用 `docs/reviews/2026-10-03-core-closing/benchmark.py`。后端 pytest 每项设置 `--timeout=60 --timeout-method=signal`，每批外层 `subprocess.run(timeout=60)`。前端验收包含差异函数、草稿事务和真实浏览器。

尚未验收：真实客户方案逐项认证、桌面 Excel/WPS 显示及重算。本次只核对实际导出的文件结构、公式、Logo 和版本绑定，不将它们计为桌面软件验收。
