# 六套知识包核对 · 第 2 批

核对日期：2026-10-09（Asia/Shanghai）。数据来源为当前业务库中知识包固定修订及其现有原文引用。本次只读核对，没有写入测试关系、合成兼容结论或发布资料包。

状态口径：独立部署排除“共享依据缺失”后计算；共享部署包含共享依据。发布状态与内容完整性分别展示。

| 知识包 | 包/定义 | 已确认关系 | 有候选角色 | 独立部署 | 共享部署 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 安全无纸化V3.0 · 历史报价资料核对 | r2 / 定义 r2 | 4/21 | 4/13 | 阻塞 111 项 | 阻塞 112 项 | 保持草稿 |
| EG 有线数字会议系统 · V2.2 待核对 | r1 / 定义 r1 | 3/7 | 0/2 | 阻塞 19 项 | 阻塞 20 项 | 保持草稿 |
| AI 智能纪要多会议室系统 · V2.2 待核对 | r1 / 定义 r1 | 3/14 | 0/7 | 阻塞 54 项 | 阻塞 55 项 | 保持草稿 |

## 阻塞明细

### 安全无纸化V3.0 · 历史报价资料核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`accessory_quantity_missing` × 18、`relation_unconfirmed` × 17、`accessory_coverage_missing` × 13、`capacity_basis_missing` × 13、`role_definition_unconfirmed` × 13、`role_quantity_missing` × 13、`accessory_quantity_unconfirmed` × 9、`role_candidates_unconfirmed` × 7、`accessory_incomplete` × 4、`role_candidates_missing` × 2、`published_package_missing` × 1、`recommendation_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`calculation_scope`、`coverage.accessories`、`coverage.resources`、`factor`、`knowledge_package_id`、`members`、`mode`、`quantity_basis`、`quantity_review`、`recommendations`、`sharing`、`status`。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

### EG 有线数字会议系统 · V2.2 待核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`relation_unconfirmed` × 4、`accessory_quantity_unconfirmed` × 3、`accessory_coverage_missing` × 2、`capacity_basis_missing` × 2、`role_candidates_unconfirmed` × 2、`role_definition_unconfirmed` × 2、`published_package_missing` × 1、`role_fulfillment_target_missing` × 1、`role_fulfillment_unconfirmed` × 1、`role_quantity_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`coverage.accessories`、`coverage.resources`、`fulfilled_by`、`fulfilled_by.need_key`、`knowledge_package_id`、`members`、`quantity_basis`、`quantity_review`、`sharing`、`status`。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

### AI 智能纪要多会议室系统 · V2.2 待核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`relation_unconfirmed` × 11、`accessory_coverage_missing` × 7、`capacity_basis_missing` × 7、`role_candidates_unconfirmed` × 7、`role_definition_unconfirmed` × 7、`role_fulfillment_unconfirmed` × 5、`accessory_quantity_unconfirmed` × 4、`role_fulfillment_target_missing` × 3、`role_quantity_missing` × 2、`published_package_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`coverage.accessories`、`coverage.resources`、`fulfilled_by`、`fulfilled_by.need_key`、`knowledge_package_id`、`members`、`quantity_basis`、`quantity_review`、`sharing`、`status`。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

## 核对结论

本批没有任何知识包满足明确发布范围。系统继续允许基于已确认候选生成部分方案，并将数量、配套、容量、授权和共享缺口返回给售前及 MCP 调用方；不得将该结果表述为完整方案已认证。
