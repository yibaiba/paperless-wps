# 售前产品助手 WPS 加载项

首版支持 WPS 表格。插件负责工作簿交互，产品匹配、业务检查、项目版本和同步事务由现有 FastAPI 后端处理。

## 当前使用方式

按 2026-10-04 的用户选择，先完善原有单元格旁的 **WebDialog 灰字浮层**，暂停原生编辑探针验证。它不是 WPS 原生单元格编辑器，也不依赖原生探针服务。

在「售前产品助手」中连接账号、映射模板并确认产品来源后，选中受管的型号、名称或说明单元格。浮层关闭后，可在助手点击「打开当前单元格补全」重新打开。

- 当前行明确、可直接接受的产品显示灰字，`Tab` 接受；有歧义时展开候选，明确选择。
- 业务候选展开后显示配置说明、来源工作表和目录批次；悬停查看完整身份。方向键切换时选中项自动滚入视口，不抢走输入焦点。
- 修改位于其他行时先显示位置和原因，`Tab` 只定位。数量、供货、用途关联等修改必须预览，再点「确认应用本组修改」，或在预览获得焦点后按 `Ctrl/Cmd+Enter`。
- 明确选中的配置在跨行定位后保留，并在目标位置重新校验；不会重新跳回第一候选。新输入、目标会话或本地业务修订变化后，这次临时选择失效。
- 预览中按 `Esc` 或「返回补全，不应用」返回输入；查询失败后可重试查询，不会自动重试工作簿写入。
- 浮层输入区拥有焦点时，`Ctrl/Cmd+Z` 撤销最近一组插件修改，并刷新受影响行的补全上下文；它不接管 WPS 全局撤销。若提示「已撤销，但补全刷新失败」，重试只重新读取和查询，不重复撤销。
- 业务上下文需要先绑定项目和配置业务区；旧工作簿保留基本产品补全。产品接受只改本地工作簿，服务端项目仍须显式同步。

本轮行状态、问题入口、异步诊断与性能结果见 [红盾与 Tab 实施记录](../docs/wps-redshield-tab-2026-10-05.md)；资料依据及未验收项见 [红盾资料复核](../docs/wps-redshield-review-2026-10-05.md)。此前浮层交互记录见 [浮层补全验证记录](../docs/wps-overlay-completion-2026-10-04.md)。

## 本地调试

先启动数据库与后端：

```sh
cd ..
.venv/bin/pip install -e './backend[dev]'
.venv/bin/uvicorn presales.main:app --host 127.0.0.1 --port 8016
```

真机调试由 `wpsjs` 同时注册加载项、启动资源服务并打开 WPS，不要另行占用 3889 端口：

```sh
cd wps-addin
npm install
PRESALES_API_TARGET=http://127.0.0.1:8016 npx wpsjs debug -p 3889
```

仅在浏览器检查静态页面时使用 `npm run dev`；它不会提供 WPS 宿主对象。

签发十分钟内单次有效的个人配对码：

```sh
cd ..
.venv/bin/presales-wps-pair "售前人员姓名"
```

## 构建与发布

```sh
npm test
npm run build
npm audit --audit-level=high
```

后端 WPS 回归与 40 例目录序列回归使用整批 60 秒硬超时。目录序列不计作真实业务准确率：

```sh
cd ..
env LC_ALL=C PYTHONPATH=backend/src perl -e 'alarm 60; exec @ARGV' .venv/bin/pytest -q \
  backend/tests/configuration/test_wps_addin.py \
  backend/tests/configuration/test_wps_suggestion_ranking.py \
  backend/tests/configuration/test_wps_completion_benchmark.py
```

`dist/` 必须与 `/api/wps` 通过同一个内网 HTTPS 域名提供。WPS 发布清单使用 `dist/manifest.xml`、`dist/ribbon.xml` 和 `dist/main.js`；生产注册地址通过官方命令生成：

```sh
npx wpsjs publish --serverUrl https://presales.example.internal/wps/
```

插件令牌持久化在加载项同源 `localStorage`，并在启动时镜像到 WPS `PluginStorage`，供任务窗格和内联窗口共享。工作簿隐藏页只保存模板、项目、草稿和产品行绑定，不保存令牌；服务器数据库只保存令牌摘要。

0.1.1 须先部署支持未解析行、问题导航、`response_detail` 及阶段耗时事件的服务端，再更新加载项。不要只更新插件资源。隔离的完整目录、1,000 行内联 API 预热 p95 为 443.61ms，最大响应 21,786 字节；真实网络、双平台真机、业务准确度和两周试点仍未验收，不能据此扩大试点。

模板首次映射还必须明确选择一次产品目录批次与来源工作表。来源选择属于模板修订；修改来源会创建新修订，旧工作簿继续引用旧修订。未确认来源的历史模板可以查询候选，但空白行上下文不会直接 Tab 写入。

诊断事件只包含匿名安装/会话 ID、WPS 版本、补全状态、候选数量、耗时和错误码，不上传输入文字、客户名称、工作表内容或备注。服务端写入时自动删除超过 30 天的事件；长期无请求环境可执行：

```sh
cd ..
.venv/bin/presales-wps-purge-diagnostics
```

诊断队列改为逐事件异步 IndexedDB 事务，不在按键时同步重写 localStorage。旧队列只有持久化及读回核对成功后才清理；存储失败在任务窗格显示，不阻塞产品写入、不静默丢弃或降级。IndexedDB 的 WPS 宿主持久性仍须真机验证。

## 兼容性验收

加载项启动时会检查 `OnKey`、WebDialog、`ExecuteJavaScript` 所需入口、工作表事件、`PluginStorage` 和 `localStorage`。缺少关键能力时明确阻止运行，不切换到行为不同的降级模式。

发布前必须分别验证 macOS WPS `12.1.28496` 和售前实际 Windows WPS 构建：Ribbon、任务窗格、`SheetChange`、`SheetSelectionChange`、`Application.OnKey("{TAB}")`、隐藏页、另存副本与卸载。自动化测试不能替代这些宿主级检查，完整步骤见 [试点运行手册](../docs/wps-pilot-runbook.md)。
