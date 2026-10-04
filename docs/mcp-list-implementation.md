# 清单与公司模板报价 MCP

本机其他 Agent 现在可以查询产品、建立持久草稿、选择搭配和供货、采用报价价格、检查、保存项目版本并导出 Excel。HTTP 和 MCP 调用同一个 `ListApplication`，复用项目配置、知识快照、配套分配、设备使用投影及 ZEN 数量与决策引擎。新增功能不调用模型。

## 连接本机 Agent

在项目根目录安装现有后端依赖：

```sh
.venv/bin/python -m pip install -e './backend[dev]'
```

支持标准 `mcpServers` 配置的客户端可使用：

```json
{
  "mcpServers": {
    "aisuo-presales": {
      "command": "/Users/yibaiba/Code/RustProject/pi/presales-platform/.venv/bin/presales-mcp",
      "args": []
    }
  }
}
```

入口使用官方 Python MCP SDK 2.2.0 的 stdio 传输。每个客户端启动自己的进程，数据库共享。标准输出仅用于 MCP 协议，日志使用标准错误。命令行直接运行时会等待 MCP 输入，不是 HTTP 服务。

- 自动读取项目 `.env` 中的 `DATABASE_URL`，无需把数据库密码复制到客户端配置。
- `PRESALES_ARTIFACT_DIR` 可指定本机导出目录；默认 `data/exports`。HTTP 和 MCP 必须配置为同一目录。
- `PRESALES_WEB_ORIGIN` 默认 `http://127.0.0.1:5176`，用于返回完整查看和下载地址。改端口时，两个入口使用相同值。
- MCP 本身不依赖前端进程；打开网页或通过网页下载时需要现有前后端运行。
- 本轮没有自动修改任何其他 Agent 的客户端配置。

## 十一个工具

除 `catalog_get`、`list_search` 使用平铺参数外，其余工具参数包在 `request` 中。例如 `systems_list({"request": {}})`。

| 工具 | 输入重点 | 返回内容 |
| --- | --- | --- |
| `systems_list` | offset、limit；可选 definition_id、knowledge_package_id、快照 ID、features | 系统、角色、知识包、未映射旧系统；指定系统时增加需求描述 |
| `catalog_search` | query；可选 draft_id + requirement_id | 分页配置摘要、来源 ID、候选结论与依据；项目候选附组合检查、输入检查和待确认说明 |
| `catalog_get` | variant_id；可选 draft_id | 指定配置、参数、来源原文、原始价格列和相关知识 |
| `list_search` | query；或 project_id | 项目当前修订；指定项目后分页读取历史保存版本 |
| `list_create` | name、actor、evidence、operation_id | 草稿 ID、修订、固定产品与知识版本 |
| `list_get` | draft_id；或 project_id + revision；view | 按视图分页返回设备、报价、问题、差异等 |
| `list_update` | 草稿写入信息、operations | 原子执行明确业务操作，返回新草稿修订 |
| `list_plan` | 草稿写入信息；可选 proposal_id、option_offset、deployment | 生成持久方案提案与按需替代方案，不修改实际清单 |
| `list_check` | 草稿写入信息 | 保存本次检查、两个计算指纹、报价摘要 |
| `list_save` | 草稿写入信息、项目预期修订、检查指纹 | 项目保存修订、完整网页地址；仍是业务草稿 |
| `list_export` | project_id、revision、output、operation_id | 文件 ID、校验值、实际路径、下载地址 |

`list_get.view` 支持：`summary`、`requirements`、`devices`、`procurement`、`allocations`、`quotation`、`issues`、`evidence`、`changes`、`template`。报价视图的 `total` 是金额，`total_items` 是明细总数。采用价格和调整依据在逐行 `price_selection` 中。`check_current=false` 表示尚未明确检查当前修订，不能拿旧检查保存或应用配套。

### 草稿写入信息

```json
{
  "request": {
    "draft_id": "list_create 返回的 ID",
    "expected_revision": 1,
    "operation_id": "客户端生成的唯一操作 ID",
    "operations": []
  }
}
```

每次成功写入、检查、保存都返回新的草稿 `revision`。`list_save` 还返回 `project_revision`，它才是 `list_export.revision` 需要的项目保存修订；二者不能混用。下一次新操作使用这个修订。网络中断后重试保留原 `operation_id` 和完整请求，包括原 `expected_revision`；数据库回执返回原结果。不能只保留幂等键却修改内容。

错误会明确返回：`VERSION_CONFLICT`（读取后比较再修改）、`CHECK_STALE`（重新检查）、`IDEMPOTENCY_CONFLICT`（同一操作标识被用于不同内容）。事务失败不会留下部分设备或项目版本。

## Agent 工作顺序

1. 查系统定义及角色。缺失数量、版本、环境或供货条件时记录问题，不自行补成已确认条件。
2. `list_create` 新建草稿；改单时同时指定 `project_id` 和确切的 `revision`，保留原配置快照。
3. 通过 `room_put`、`system_put`、`requirement_put` 建立业务需求。对象 ID 由调用方生成并稳定复用。
4. 带草稿及角色查候选，必要时 `include_other_products=true` 查看其他产品。读取来源原文后选择具体 `variant_id` 和 `source_id`。
5. `device_put` 明确设备 ID、数量、类型和来源；用需求的 `device_id` 关联设备。同一服务器给两个角色引用只计一台，两个设备 ID 计两台。
6. `supply_set` 明确采购、客户已有、供货待定及依据。已有设备参与检查，不进入采购金额。数量变化后供货未匹配会显示待确认。
7. `list_check` 后读 `issues`，明确选用配套、候选或已有设备，再应用；配套链逐步检查和应用。
8. 填写报价元数据、价格列或人工单价，重新检查，并查看 `quotation`、`issues`、`changes`。
9. `list_save` 使用当前草稿修订、`expected_project_revision`（新项目为 0，改单为基线修订）和 `check_fingerprint`。
10. `list_export` 使用返回的项目 ID 和保存修订，`output` 可选 `configuration`、`quotation`、`both`。

### 业务操作

| action | 含义 |
| --- | --- |
| room_put / system_put / requirement_put | 按稳定 ID 新增或替换需求对象 |
| system_setup | 一批建立或修改房间、系统及所选角色需求；重复调用复用角色，保留已选设备 |
| device_clone | 传 source_device_id、new_device_id 复制为独立设备；可选 supply_allocations。不继承用途、配套抵扣、生成锁定或已采用价格；未明确供货保持待确认 |
| device_put | 新增或替换实际设备；数量和 hardware/software/license/accessory 类型必填 |
| remove | 删除明确的房间、系统、角色或设备；删除设备同步删除其供货、分配、报价和图纸引用 |
| supply_set | 替换指定设备的供货分配，各分配必须属于该设备 |
| accessory_choice | 显式选用或取消推荐、可选配套需求 |
| accessory_apply | 选择候选新增配套，或关联已有设备及分配数量 |
| accessory_remove | 根据 allocation_id 解除配套分配，设备及采购项保留 |
| included_link | 使用已确认的产品已含内容，显式抵扣对应配套需求，不创建采购项 |
| included_remove | 根据 allocation_id 移除已含抵扣 |
| quotation_set | 只更新所提供的报价字段；未提供的人工价格保留 |
| price_set | 设置单个设备的来源价格或有依据的人工单价 |
| price_readopt | 明确对指定设备重新采用报价选择的来源价格列 |

`accessory_apply.fingerprint` 使用 `list_check` 返回的 **calculation_fingerprint**；`list_save.fingerprint` 使用 **check_fingerprint**。前者由既有配套计算服务校验；后者绑定完整草稿及本次检查。不要互换。

`quotation_set` 最小示例：

```json
{
  "action": "quotation_set",
  "value": {
    "customer": "客户名称",
    "project_name": "项目名称",
    "price_column": "甲方指导价",
    "design_date": "2026-09-27"
  }
}
```

`price_set` 的 value 需要 `device_id`、`variant_id`、`source_id`、`mode`。人工价另需 `unit_price`（十进制字符串）和 `evidence`。必须从产品资料或维护者获得价格依据，测试价格不得用于真实项目。修改型号或来源后旧价格标为过期，重新采用后才能形成完整金额。

### 需求描述与批量建立（2026-09-29）

`systems_list.request` 增加可选 `definition_id`、`knowledge_package_id`、`definition_snapshot_id`、`knowledge_snapshot_id` 和 `features`。指定系统后，`requirement_description` 返回固定修订的角色、功能条件、输入名称／类型／单位／作用范围和资料覆盖缺口。已有项目应传入自身快照 ID；不传表示读取当前资料，不能据此静默升级已有项目。网页 `/api/configuration/requirement-description` 复用同一投影。

`list_update.operations` 可以提交 `action: "system_setup"`，同层字段为 `system`、可选 `new_room`、`role_ids`、`role_environment`。`system` 使用现有系统 DTO，`new_room` 使用现有房间 DTO；`role_ids` 来自需求描述，`role_environment` 按角色 ID 分配环境参数。已有房间通过 `system.room_id` 指定，不按名称合并；角色需求按系统 ID 和角色 ID 复用。这个操作不选择产品、不创建采购项，也不因取消功能删除原角色或设备。

网页 `/api/configuration/system-setup-preview` 只返回预览配置，正式应用仍进入既有草稿操作、幂等回执和修订检查。知识包的 `/api/configuration/knowledge-packages/{id}/change-preview` 同样只预览选定成员／定义修订，保存仍使用原接口和预期修订。

检查结果增加 `code`、`check_id`、`group_id`、`category` 和 `objects`；保留原文说明与 `action.missing_fields`。Agent 根据结构化动作处理，不能解析中文提示判断行为。网页合并展示共同原因时保留全部检查 ID、对象和依据；展示分组不会减少原始检查数量。

## 计算与持久化

- 新增 `list_draft`、`list_catalog_snapshot`、`list_operation`、`list_artifact` 四种实体，使用现有实体表及修订机制，没有重建数据库。不可变产品目录快照按内容复用，不把整个产品库返回 Agent。
- 创建草稿固定候选产品版本及知识。普通读取、检查不会更新版本；`list_check.refresh_knowledge=true` 才在草稿中明确更新，并提供修改差异。项目保存版本及已导出文件保持不变。
- MCP 与网页未保存草稿相互独立。保存后网页可以打开并编辑；网页沿用已有统一撤销、重做和配置保存流程。
- Python 固定资料版本、准备角色及用途、分配数量并汇总检查。`zen-v1` 项目由真实 ZEN 执行条件、必选/互斥/至少一项组合及容量比较，数量公式也由 ZEN 执行；旧 `python-v3` 项目保持原语义，需明确升级。金额由 Decimal 逐行四舍五入到分后合计，不额外加税、运费或折扣。
- 候选仅汇总与当前角色相关的组合，包括该角色配套触发的组合和其他设备对该角色施加的约束；全项目检查继续保留其他设备的缺口。`combination_checks`、`input_checks`、`combination_notice` 为兼容增加字段，缺少数量时通过说明返回原因，不伪造数量或通过结论。
- 缺价、非数值价格和供货待定保持待确认；完整总额为 `null`，只返回已知金额小计。明确零价有效。
- 价格来自指定原始来源列，不自动切换其他列。客户已有设备可没有报价价格，不计采购金额。
- 图形布局改变不新增采购；清单新增或删除设备由已有图纸投影更新引用。
- HTTP 入口是 `POST /api/list-tools/{tool}`，请求正文为工具业务参数（不再包 request）；查询模板用 `GET /api/quotation-template`。

## 模板与导出

模板副本放在 `backend/src/presales/quotation/templates/meeting-system-v1.xlsx` 并随 Python 包分发。源文件 SHA-256 为：

```text
1209dba11ed73324ef1fbb2e361c9288049f07d8f8d3da9182152b6337d8800e
```

字段映射版本为 1。模板改变而未注册新版本会报错。原用户文件没有修改。

- 保留现有表头、Logo、列宽、格式和税运条款，填入客户、项目、销售、设计、日期、厅堂信息。
- 保留无纸化 10 行、扩声 10 行、辅助设备 5 行的预留空间；超过时扩展，其他系统新增分区。共享设备默认公共设备，备注列出服务系统。
- 长说明按文字长度、列宽估计换行并使用续行，保留全部文本；续行不重复数量、单价或金额。人工展示分组不影响配置检查与采购数量。
- 每行 Excel 公式为 `ROUND(数量*单价,2)`，缺数量或价格保留空金额。完整合计缺依据时显示待确认。
- 工作簿同时写入按同一 Decimal 投影算出的公式缓存，并设置打开时重新计算；缓存验证不能代替 Excel/WPS 实际重算验收。
- 设备清单另列部署、已有、采购和待定数量，以及检查与版本来源。报价单只列本次采购及供货待定项，标为报价草稿。
- 下载前核对文件校验值。导出失败、文件缺失或被改动明确报错，不能返回假成功。

## 验证与剩余验收

自动化覆盖真实 stdio 客户端、HTTP/MCP 同输入查询、进程重启重试、PostgreSQL 并发、冻结目录、金额、缺价与零价、换型号、扩行、新分区、长说明、Logo 字节及模板校验值、旧项目和图纸回归。所有测试使用内存库或隔离 PostgreSQL schema；单项和每批均设 60 秒硬超时。

2026-09-27 验证：配置及清单报价 112 项、原清单/规则/拓扑 85 项、真实无纸化工作簿 18 项，共 215 项通过。Ruff、TypeScript 和生产构建通过；构建仍提示已有依赖包超过 500 kB。业务库复核为 459 条产品来源、242 个配置、201 条知识、0 个项目，测试项目没有写入业务库。

真实资料副本的浏览器验收已完成：Agent 保存的项目在网页读取，调整报价、检查、撤销、重做、保存为新版本、重开及下载两份 Excel。客户已有共享服务器采购为零；缺少共享知识和容量的结论仍为资料不足。隔离测试单价不进入业务产品库。

**尚未完成：实际 Excel/WPS 中的显示、分页和公式重算验收。** 当前会话只允许浏览器控制，不能操作本机 WPS。已经完成文件结构、公式缓存、Logo 和程序预览检查，不将其表述为原生办公软件验收。

业务库缺少的共享、容量、授权依据没有被测试数据补齐。本轮完成软件流程，不代表红盾和会议预约共用服务器的业务方案已经确认。


## 产品已含内容抵扣（2026-09-28）

`catalog_get.variant.included_items` 是版本化的配置事实，不是自动补料规则。先读取 `list_get(view="issues")` 中配套需求的 `included_offers`，核对 `status`、`reason`、`available`、`evidence` 以及宿主配置修订，再通过 `list_update` 提交：

```json
{
  "action": "included_link",
  "value": {
    "id": "客户端稳定分配 ID",
    "demand_id": "配套需求 ID",
    "device_id": "宿主设备 ID",
    "included_item_id": "包含事实 ID",
    "host_variant_id": "offer 返回的宿主配置 ID",
    "host_variant_revision": 2,
    "quantity": "1",
    "evidence": "本次采用已含内容的依据"
  }
}
```

修订、ID 和数量均须采用当前草稿的实际结果；例子不是业务数据。新分配不得超过当前缺量或可用已含数量。相同请求仍遵循幂等键规则。`list_get(view="allocations")` 返回 `allocation_type="included"` 的关联；需求结果分别返回 `separately_allocated`、`included_quantity`、总 `existing` 及剩余 `missing`。

同一宿主包含项的数量跨需求合计，超量时不计入有效抵扣。未确认事实、目标不符、修订失效均明确报告。既有采购项不会被删除，多余数量交售前处理。此功能只抵扣明确关联的配套需求，不把包含项自动转成独立设备、角色选型或跨设备可转移授权。实际资料的包含数量、授权范围和匹配配置需要维护者确认。

需求结果的 `included_allocation_checks` 提供每条抵扣的 `allocation_id`、状态、原因、`counted_quantity`、`allocated_quantity`、`capacity`、当前宿主修订和当前包含依据。修改数量或重新确认修订时，在**同一** `list_update.operations` 中先 `included_remove`、再 `included_link`（可沿用原分配 ID），整批成功才替换。失败则原关联保留。不要用两个独立请求做替换，也不要把新修订自动当作已确认。采用修订取自当前项目的 `included_offers`；更新产品库不会自动改变项目快照。


## 需求驱动方案生成（2026-09-29）

新增 `list_plan`、`requirements_patch`、`proposal_apply` 和提案查询视图。调用方式、知识维护、网页入口及软件／业务验收边界见 [实施与验收记录](mcp-proposal-generation-implementation-2026-09-29.md)。


## 2026-10-03 核心收口

- readiness、需求描述和 `systems_list` 的 `generation.gaps` 共用同一固定版本投影；每项包含 code、object_id/object_revision、missing_fields、scenario、evidence_refs、action、maintenance_url。旧文字字段继续保留。
- `scenario=shared` 只表示共享部署的缺口；独立生成不受共享缺证阻塞。`sharing_evidence_present` 仅表示登记了确认关系，仍须在具体项目检查条件及容量。
- 网页草稿与 MCP 编辑共用原子操作服务；备注不触发完整适配/ZEN 判断。正式保存仍完整检查。
- 预期业务错误以 MCP `is_error` 和具体原因返回；冲突时按原幂等键读回或重新比较，不能当作成功。未知运行错误继续记录失败。
- 导出产物与事务回执关联。回滚清理本次未提交文件；提交确认丢失时读取回执后保留已提交产物。
- 软件验证、现有业务资料缺口及复现命令见 [验收记录](reviews/2026-10-03-core-closing/acceptance.md)。

## 工作簿依据与参考案例对账（2026-10-04）

`systems_list` 可增加 `catalog_snapshot_id`。需求描述在未选型时沿候选配套链返回 `inputs`，包含业务名称、作用范围、`project_input` 用途、消费者、候选、条件和固定依据；`shared_inputs` 合并同口径的非角色输入，`input_gaps` 明确返回类型/单位/用途冲突和循环路径。条件性输入不是已确认的必填项；关闭功能不产生采购。

系统兼容增加 `served_room_ids`，用于明确跨房间服务范围。`room_id` 仍表示部署/展示房间；服务范围不自动推定采集、字幕或授权数量。网页和 MCP 复用同一系统 DTO。

`list_get.view="case_comparison"` 按原案例行分页，返回固定案例、每行映射、部署/采购/已有/已含数量、`mapped_quantity`（用于此行的数量）、数量差、问题及动作。无关联案例时返回可选择的案例摘要。多行可引用同一设备，采购仍按设备 ID 计一次；不要汇总对账表的重复用途行充当采购清单。

`list_update` 支持下列操作，预期草稿修订、幂等键和撤销机制不变：

```json
{
  "action": "reference_case_set",
  "value": {
    "id": "参考案例ID",
    "revision": 1,
    "bindings": [{
      "row_id": "row-141",
      "device_ids": ["实际设备ID"],
      "requirement_ids": [],
      "demand_ids": [],
      "included_allocation_ids": [],
      "disposition": "compare",
      "evidence": "明确核对的配置及本项目采用理由"
    }]
  }
}
```

`value=null` 解除案例关联，不删除设备。`disposition` 为 `compare`、`unresolved` 或 `not_enabled`；后者须填写 `feature_system_id`、`feature`，并且属于固定系统定义、功能选择已确认且当前未启用。后续功能或设备变化会重新形成差异，原映射保留以便定位。

资料接口（均在 `/api/configuration` 下）：

- `POST /extraction/materials/xlsx/preview`：上传 XLSX，返回校验值、工作表和范围原文预览。
- `POST /extraction/materials/xlsx`：上传同一文件，`options` 包含名称、digest、ranges（sheet/range）、actor、evidence、operation_id；新修订另需 material_id、expected_revision。
- `GET /extraction/materials/{id}/revisions/{revision}`：读取固定资料片段。
- `POST /reference-cases`：保存案例原文与显式配置映射；更新需 case_id、expected_revision、operation_id。
- `GET /reference-cases`、`GET /reference-cases/{id}/revisions/{revision}`：摘要和固定修订。
- `POST /reference-cases/compare`：接收 Configuration，只读对账，不保存项目。

依据兼容产品 `source_id` 引用；工作簿说明使用 `material_id + material_revision + segment_id + locator + quote`。原文必须存在于指定修订片段，公式只作原文。材料、参考案例不增加产品来源，也不是采购规则。
