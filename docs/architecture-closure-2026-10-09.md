# 售前平台架构收口记录（2026-10-09）

## 结论

本轮完成了正式业务入口、后端依赖方向和六套知识包状态的收口。系统继续采用模块化单体，`Configuration` 仍是项目业务事实来源；HTTP、stdio MCP 和 WPS 适配层共用应用服务，没有拆分微服务或建立第二套计算内核。

软件流程已经具备产品维护、知识维护、需求选配、方案提案、配套检查、报价、保存和导出能力。六套真实知识包均因定义、数量、配套、推荐或共享依据不足而保持草稿，本轮没有向业务库写入测试结论，也没有为了发布而补造知识。

## 正式业务流程

主导航收口为四组：

1. 产品与价格。
2. 系统与搭配知识。
3. 售前项目。
4. 资料维护。

新建或打开项目统一进入 `/configuration/{projectId}`，项目内按“需求与系统 → 配置与配套 → 报价与导出”推进。清单、拓扑和报价读取同一份配置。旧配套规则、独立拓扑和旧清单编辑保留在“高级与历史”，用于历史查询和显式迁移，不再作为新项目入口。

项目页的业务交互、弹窗宿主和阶段展示已经分离，原 URL 参数和草稿恢复行为保留。真实浏览器已验证项目列表、统一配置页、知识工作区和六包状态表；此前条件调用 Hook 导致的项目页崩溃未复现。

## 后端依赖方向

当前依赖方向为：

```text
HTTP / MCP / WPS 适配层
          ↓
ListApplication 与项目应用用例
          ↓
产品、知识、项目、价格、报价领域
          ↓
presales.application 基础层
          ↓
SQLAlchemy / PostgreSQL / 文件适配器
```

`presales.application` 统一承载应用合同、错误、摘要、修订、幂等和事务。价格查询及采用合同归入 `presales.pricing`。报价产物通过注入的项目修订读取接口获取数据；方案生成使用基础层幂等能力；产品更新调用知识服务，不再调用 HTTP 路由函数。

`configuration`、`quotation`、`catalog_updates` 和 `pricing` 不再反向导入 `presales.lists`。静态依赖测试同时禁止核心领域导入 WPS 适配层，并限制产品更新模块调用路由。旧导入路径保留兼容重导出，现有 HTTP 路径、11 个 MCP 工具、数据库表、JSON 内容及业务 ID 均未改变。

`ProjectConfigurations` 继续作为兼容外观，内部委托快照准备、检查、保存和配套服务。旧 ZEN 规则适配器仍属于历史兼容边界；当前项目语义继续由统一配置计算和 ZEN 决策执行，不新增另一套规则系统。

## 六套知识包状态

以下数据来自 2026-10-09 的只读 readiness 快照。表中“独立/共享问题”是对应场景的结构化问题数量；“候选角色”表示已有已确认候选的角色数，不等于该角色已经可以自动生成。

| 知识包 | 包/定义修订 | 已确认关系 | 候选角色 | 独立问题 | 共享问题 | 状态 |
|---|---:|---:|---:|---:|---:|---|
| 会议预约与信息发布系统 · 试点资料核对 | 3 / 2 | 13 / 15 | 3 / 4 | 48 | 49 | 草稿，未达到发布范围 |
| 分布式无纸化会务系统2.0 · 历史报价资料核对 | 6 / 5 | 20 / 55 | 7 / 28 | 257 | 258 | 草稿，未达到发布范围 |
| 安全无纸化V3.0 · 历史报价资料核对 | 2 / 2 | 4 / 21 | 4 / 13 | 111 | 112 | 草稿，未达到发布范围 |
| EG 有线数字会议系统 · V2.2 待核对 | 1 / 1 | 3 / 7 | 0 / 2 | 19 | 20 | 草稿，未达到发布范围 |
| AI 智能纪要多会议室系统 · V2.2 待核对 | 1 / 1 | 3 / 14 | 0 / 7 | 54 | 55 | 草稿，未达到发布范围 |
| 红盾无纸化会议系统 · Windows · 试点资料核对 | 2 / 2 | 8 / 16 | 3 / 10 | 73 | 74 | 草稿，且有 1 项固定修订差异 |

六套包的 `independent_content_ready` 与 `shared_content_ready` 当前均为 `false`，已确认共享知识为 0。主要阻塞集中在角色定义、角色数量依据、配套候选及数量、容量依据、推荐顺序和共享依据。缺少共享依据会阻止共享场景通过，但 readiness 已将它与独立部署缺口分开，不再用共享缺口笼统代表独立部署状态。

详细核对记录：

- [第一批：红盾 Windows、会议预约、分布式 2.0](knowledge-readiness-2026-10-09-batch-1.md)
- [第二批：安全无纸化 V3.0、EG、AI 智能纪要](knowledge-readiness-2026-10-09-batch-2.md)
- [readiness 原始证据](evidence/knowledge-package-readiness-2026-10-09.json)

## 接口与历史保护

新增只读接口 `GET /api/configuration/knowledge-packages/readiness-summary`，逐包 readiness 继续保留 `scenarios`、`generation_support`、`issues` 和旧字段。知识工作区使用同一投影展示六包状态，没有在前端重新解释发布条件。

知识包固定具体定义和关系修订。当前知识变化不会重写旧项目或旧报价；项目只有明确预览并采用升级后才进入新草稿。旧入口仍能读取历史，统一项目继续使用原项目 ID、设备 ID、草稿修订、检查指纹和导出产物语义。

## 验证结果

- 后端完整回归：910 项通过，33 项跳过。
- 33 项跳过均为显式环境条件，包括需要 `TEST_DATABASE_URL` 的 PostgreSQL 并发/pgvector 测试，以及需要真实产品工作簿路径的纸化资料测试；这些项目未计为通过。
- 真实 stdio MCP 的方案、编辑、分布式场景和 ZEN 协议测试包含在已通过回归中。
- 前端：115 项测试通过，TypeScript 生产构建通过，bundle 预算检查通过。
- 浏览器：项目列表、统一配置页、草稿恢复、系统版本工作区及六包状态表通过实际操作验证。
- 静态依赖测试：核心领域不得反向依赖 `lists`、HTTP 路由或 WPS 适配层。

本轮未执行桌面 Excel/WPS 显示与重算，也未取得业务人员确认的真实客户方案轨迹。因此当前结论是架构和软件流程通过，不能表述为六套产品方案已完成业务认证。

## 对应提交

1. `418c8ee refactor(ui): consolidate primary presales workflow`
2. `cee7a13 refactor(core): establish one-way application dependencies`
3. `a4d0921 feat(knowledge): expose six-package readiness portfolio`
4. `f7d9d94 data(knowledge): review independent deployment packages`
5. `907587b data(knowledge): review remaining package scopes`
