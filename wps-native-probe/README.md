# 独立 WPS 原生能力验证包

此包与售前加载项分离。不创建 WebDialog、不模拟键入、不写单元格，不连接业务 API。
先关闭售前加载项及其他 Tab 绑定插件，用空白测试工作簿运行，避免覆盖其他加载项的快捷键。

安装现有 wps-addin 开发依赖后，在本目录运行 `npm run debug`（使用项目锁定的 wpsjs）。
本命令启动 WPS，会改变开发加载项注册；仅供开发验收。退出后停止 debug 并移除测试加载项。

## 复现步骤

1. 记录系统、WPS 完整构建号、输入法；点击“开始记录”。
2. A1 输入 abc，先不提交，再 Tab 提交。记录 SheetChange 的实际触发时点；通过宿主调试器调用 `probe` 不可行，调试全局入口可用 `Application.ActiveCell.Value2` 比较编辑前后。Ribbon 按钮可能结束编辑，不能把按钮读取结果当作未提交输入证据。
3. 点击“测试下一次 Tab”，进入单元格原生编辑再按 Tab，记录回调是否触发。测试键只记录回调和恢复绑定，不接受产品、不回放按键；下一次 Tab 是否恢复须手测。点“停止并恢复 Tab”可清理。
4. 分别重复中文组合输入、Esc、公式编辑、滚动缩放、多窗口及关闭工作簿；记录键盘及焦点行为。
5. 导出 JSON。下载若被宿主阻止，在加载项调试器记录异常；不宣称导出成功。

## 判定与证据

导出结果的各能力默认 `not_verified`，事件存在不自动代表能力通过。验收人员在报告副本逐项填写 `status: passed | failed | not_verified`、`steps`、`evidence`（录像或日志路径、公开接口名、构建号）。不能只根据 OnKey 存在给 edit_tab 或 native_restore 判通过。

`uncommitted_text`、`caret`、`ime`、`native_ghost` 没有已确认的公开实现接口，本包不会虚构对应探针。没有真实实现与实测证据时保持未验证；只有证实失败才能写 failed。全部能力通过前原生集成不启用。

截至本包交付，macOS 12.1.28496 和 Windows 均未完成本轮真机验证；Windows 构建号未提供。Node 测试只证明记录器的逻辑，不证明宿主能力。

依据：[表格事件](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/addin-api/event/et-event)、[OnKey](https://open.wps.cn/documents/app-integration-dev/wps365/client/wpsoffice/jsapi/et/Application/member/OnKey)。
