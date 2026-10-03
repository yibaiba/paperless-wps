# 知识与 ZEN 统一决策独立代码复核

## 复核结论

首轮结论为 `gaps_found`：审查确认六项违反当前批准范围的实现缺陷。共享工作树随后修复全部六项，修复后的独立代码复核结果为 `pass`，当前没有开放的代码验收缺口。正式任务结论仍为 `limited_review`，原因是 humanizer-zh 缺失，正式 handoff 无法生成和通过合同检查。

## 可执行发现及处理状态

### 1. 组合角色数量没有采用显式分配量

原调用链把一个角色的多项显式分配拆成计算切片，组合检查却把每个切片按设备总库存和完整角色需求比较。需求为2、库存为2、只分配1时原结果为pass；两台设备分别分配1时原结果为conflict。修复在 `projects/role_allocations.py:77` 重新聚合逻辑需求，由 `calculation/combinations.py:174` 对聚合结果计算。两个反向用例通过。

### 2. 项目候选可混用不同固定版本

候选原来读取请求中的知识快照，却只按另一请求字段加载固定bundle，没有证明二者属于同一项目版本。修复后 `projects/schemas.py:177` 从configuration继承并校验版本和知识包，`services/candidate_versions.py:9` 比较相同知识包范围的规则签名并加载固定bundle。版本错配、混合包、旧式系统和显式错包回归通过。

### 3. Python 项目候选静默忽略组合

原来只有ZEN候选进入 `CandidateCombinations`，Python候选直接返回适用条件结果，造成候选pass而项目检查要求升级。现在计算版本3的项目候选均进入组合投影；Python运行时只在候选真实触发组合时明确失败。

### 4. 旧项目及工作草稿差异基线静默使用ZEN

全局空配置曾默认ZEN，历史Project和旧清单导入会跳过显式升级。修复后新项目写入ZEN出生标记，没有标记的旧项目默认Python。`ListService._check` 对base revision 0也读取同一出生标记，不再虚报decision_runtime差异。修正后的公开WebDrafts revision 0路径已通过五文件41项回归。

### 5. 已发布知识包试查绕过固定bundle

发布包保存 `decision_bundle_id`，试查却曾使用当前请求级ZEN服务重新编译。隔离复现中，即使固定bundle引擎版本被改成不可用，原试查仍返回200/pass。现在已发布包试查先resolve/load固定bundle，engine、compiler和hash三类损坏均明确失败；草稿包继续保留既有纯条件试查合同。

### 6. 无关组合阻断旧API和Python项目

原来知识快照只要存在任意未禁用组合，运行时门禁就在计算真实触发范围前报错。现在门禁位于selector、角色和作用域真实触发且启用条件未全部失败之后；无项目纯条件试查和未触发Python项目保持兼容，相关组合仍要求ZEN。

## 回归与证据

独立复核先后执行39项核心测试、75项扩展测试以及GAP-04尾项修正后的41项测试。 `legacy-baseline-regression.txt` 另保留初次无效测试入口的失败记录，并记录改用公开WebDrafts revision 0入口后的官方尾项结果：16 passed，8.88秒。每项和每批均设置60秒硬上限。`git diff --check`、Python编译和Ruff通过。

`final-regression.txt` 记录20个成功批次，合计620 passed、0 skipped。原六文件重负载合批超过60秒后被硬中止，未计成功；拆分后 `test_zen_combinations.py` 15项、`test_zen_protocol.py` 1项、paperless真实工作簿4+5+9项以及其余普通测试均通过。前端81/81通过。

浏览器在最新服务重启后验证保存v2恢复、检查接口HTTP 200完整响应体和操作按钮非loading类。辅助功能树里的残留loading节点来自Ant Design宽度0、透明度0的退出图标，不是请求仍在进行。

## 非阻断项

<!-- deferred:DF-001 -->
知识包试查后端已返回 `package_status`，但页面结果没有直接展示它。现有文案和返回字段已经明确单产品通过不批准整个知识包，草稿规则也保持unknown，因此这是界面表达改进，不是本轮代码验收缺口。

图编辑器、真实客户方案和桌面Excel/WPS验收均不在本轮批准范围内。
