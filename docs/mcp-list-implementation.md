# 清单与公司模板报价 MCP

本机其他 Agent 现在可以查询产品、建立持久草稿、选择搭配和供货、采用报价价格、检查、保存项目版本并导出 Excel。HTTP 和 MCP 调用同一个 `ListApplication`，复用项目配置、知识快照、配套分配、设备使用投影及 ZEN 数量引擎。新增功能不调用模型。

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

## 十个工具

除 `catalog_get`、`list_search` 使用平铺参数外，其余工具参数包在 `request` 中。例如 `systems_list({"request": {}})`。

| 工具 | 输入重点 | 返回内容 |
| --- | --- | --- |
| `systems_list` | offset、limit | 系统、角色、知识包、未映射旧系统 |
| `catalog_search` | query；可选 draft_id + requirement_id | 分页配置摘要、来源 ID、候选结论与依据 |
| `catalog_get` | variant_id；可选 draft_id | 指定配置、参数、来源原文、原始价格列和相关知识 |
| `list_search` | query；或 project_id | 项目当前修订；指定项目后分页读取历史保存版本 |
| `list_create` | name、actor、evidence、operation_id | 草稿 ID、修订、固定产品与知识版本 |
| `list_get` | draft_id；或 project_id + revision；view | 按视图分页返回设备、报价、问题、差异等 |
| `list_update` | 草稿写入信息、operations | 原子执行明确业务操作，返回新草稿修订 |
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

每次成功写入、检查、保存都返回新的草稿 `revision`。下一次新操作使用这个修订。网络中断后重试保留原 `operation_id` 和完整请求，包括原 `expected_revision`；数据库回执返回原结果。不能只保留幂等键却修改内容。

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
| device_put | 新增或替换实际设备；数量和 hardware/software/license/accessory 类型必填 |
| remove | 删除明确的房间、系统、角色或设备；删除设备同步删除其供货、分配、报价和图纸引用 |
| supply_set | 替换指定设备的供货分配，各分配必须属于该设备 |
| accessory_choice | 显式选用或取消推荐、可选配套需求 |
| accessory_apply | 选择候选新增配套，或关联已有设备及分配数量 |
| accessory_remove | 根据 allocation_id 解除配套分配，设备及采购项保留 |
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

## 计算与持久化

- 新增 `list_draft`、`list_catalog_snapshot`、`list_operation`、`list_artifact` 四种实体，使用现有实体表及修订机制，没有重建数据库。不可变产品目录快照按内容复用，不把整个产品库返回 Agent。
- 创建草稿固定候选产品版本及知识。普通读取、检查不会更新版本；`list_check.refresh_knowledge=true` 才在草稿中明确更新，并提供修改差异。项目保存版本及已导出文件保持不变。
- MCP 与网页未保存草稿相互独立。保存后网页可以打开并编辑；网页沿用已有统一撤销、重做和配置保存流程。
- Python 决定兼容、共享、供货和配套，ZEN 计算数量。金额由 Decimal 逐行四舍五入到分后合计，不额外加税、运费或折扣。
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
