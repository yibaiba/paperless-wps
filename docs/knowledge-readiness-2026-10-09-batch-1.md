# 六套知识包核对 · 第 1 批

核对日期：2026-10-09（Asia/Shanghai）。数据来源为当前业务库中知识包固定修订及其现有原文引用。本次只读核对，没有写入测试关系、合成兼容结论或发布资料包。

状态口径：独立部署排除“共享依据缺失”后计算；共享部署包含共享依据。发布状态与内容完整性分别展示。

| 知识包 | 包/定义 | 已确认关系 | 有候选角色 | 独立部署 | 共享部署 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 红盾无纸化会议系统 · Windows · 试点资料核对 | r2 / 定义 r2 | 8/16 | 3/10 | 阻塞 73 项 | 阻塞 74 项 | 保持草稿 |
| 会议预约与信息发布系统 · 试点资料核对 | r3 / 定义 r2 | 13/15 | 3/4 | 阻塞 48 项 | 阻塞 49 项 | 保持草稿 |
| 分布式无纸化会务系统2.0 · 历史报价资料核对 | r6 / 定义 r5 | 20/55 | 7/28 | 阻塞 257 项 | 阻塞 258 项 | 保持草稿 |

## 阻塞明细

### 红盾无纸化会议系统 · Windows · 试点资料核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`accessory_coverage_missing` × 10、`capacity_basis_missing` × 10、`role_definition_unconfirmed` × 10、`role_quantity_missing` × 10、`relation_unconfirmed` × 8、`relation_role_unmapped` × 7、`role_candidates_missing` × 7、`accessory_quantity_unconfirmed` × 6、`accessory_quantity_missing` × 4、`published_package_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`coverage.accessories`、`coverage.resources`、`factor`、`knowledge_package_id`、`members`、`mode`、`quantity_basis`、`quantity_review`、`role_id`、`sharing`、`status`、`system_definition_id`。
- 固定修订与当前资料存在 1 项差异，发布前必须逐项选择是否升级。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

### 会议预约与信息发布系统 · 试点资料核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`accessory_quantity_missing` × 18、`accessory_quantity_unconfirmed` × 9、`accessory_coverage_missing` × 4、`capacity_basis_missing` × 4、`role_definition_unconfirmed` × 4、`role_quantity_missing` × 4、`relation_unconfirmed` × 2、`published_package_missing` × 1、`recommendation_missing` × 1、`role_candidates_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`coverage.accessories`、`coverage.resources`、`factor`、`knowledge_package_id`、`members`、`mode`、`quantity_basis`、`quantity_review`、`recommendations`、`sharing`、`status`。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

### 分布式无纸化会务系统2.0 · 历史报价资料核对

- 当前包状态：`draft`；定义状态：`draft`。
- 独立部署内容未达到可发布范围；共享部署也未达到可发布范围。
- 缺口代码：`accessory_quantity_missing` × 46、`relation_unconfirmed` × 35、`accessory_coverage_missing` × 28、`capacity_basis_missing` × 28、`role_definition_unconfirmed` × 28、`role_quantity_missing` × 26、`accessory_quantity_unconfirmed` × 23、`accessory_incomplete` × 20、`role_candidates_unconfirmed` × 20、`published_package_missing` × 1、`recommendation_missing` × 1、`role_candidates_missing` × 1、`sharing_basis_missing` × 1。
- 阻塞字段：`calculation_scope`、`coverage.accessories`、`coverage.resources`、`factor`、`knowledge_package_id`、`members`、`mode`、`quantity_basis`、`quantity_review`、`recommendations`、`sharing`、`status`、`target_variant_ids`。
- 处理结果：不发布，不补写缺失数量、容量、授权、推荐顺序或共享结论。

## 核对结论

本批没有任何知识包满足明确发布范围。系统继续允许基于已确认候选生成部分方案，并将数量、配套、容量、授权和共享缺口返回给售前及 MCP 调用方；不得将该结果表述为完整方案已认证。
