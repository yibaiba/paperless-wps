# 售前产品助手 WPS 加载项

首版支持 WPS 表格。插件负责工作簿交互，产品匹配、业务检查、项目版本和同步事务由现有 FastAPI 后端处理。

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

`dist/` 必须与 `/api/wps` 通过同一个内网 HTTPS 域名提供。WPS 发布清单使用 `dist/manifest.xml`、`dist/ribbon.xml` 和 `dist/main.js`；生产注册地址通过官方命令生成：

```sh
npx wpsjs publish --serverUrl https://presales.example.internal/wps/
```

插件令牌保存在 WPS `PluginStorage`，工作簿隐藏页只保存模板、项目、草稿和产品行绑定，不保存令牌。服务器数据库只保存令牌摘要。

## 兼容性验收

发布前必须分别验证 macOS WPS `12.1.28496` 和售前实际 Windows WPS 构建：Ribbon、任务窗格、`SheetChange`、`SheetSelectionChange`、`Application.OnKey("{TAB}")`、隐藏页、另存副本与卸载。自动化测试不能替代这些宿主级检查。
