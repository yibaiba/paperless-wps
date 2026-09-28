# 本机浏览器 Office

ONLYOFFICE Docs Community 9.4.0.1 提供 Excel（XLSX）、Word（DOCX）和演示文稿的浏览器编辑。此部署用于本机编辑与导出验收，独立于产品知识、配套计算和项目数据库。

## 启动与停止

在项目根目录执行。首次创建本机私有密钥，不写入代码或业务库：

该镜像已固定版本与校验值。官方建议单独为 Office 提供至少 4GB 内存；本机若同时运行两个智能检索模型，应先为 Docker 配置足够内存。2026-09-27 检查时 Docker 总内存约 8GB、剩余约 500MB，暂不能据此宣称编辑器已稳定运行。

```sh
python3 - <<'PY'
from pathlib import Path
from secrets import token_urlsafe

directory = Path('data/private')
directory.mkdir(parents=True, exist_ok=True)
directory.chmod(0o700)
target = directory / 'office.env'
if not target.exists():
    with target.open('x') as stream:
        stream.write('JWT_SECRET=' + token_urlsafe(48) + '\n')
target.chmod(0o600)
PY
docker compose -f compose.office.yaml up -d
```

打开 <http://127.0.0.1:8087/example/>。点击上传，选择 `.xlsx` 或 `.docx`，进入编辑器；也可从首页新建文档。使用原文件副本验证，不直接覆盖注册报价模板。

```sh
docker compose -f compose.office.yaml ps
docker compose -f compose.office.yaml logs --tail 50 office
docker compose -f compose.office.yaml stop
```

再次运行 `up -d` 即可恢复。上传文件与编辑器数据存放在此 Compose 项目的命名卷，停止容器不会删除它们。不要使用 `down -v`，该命令会删除文档卷。

服务只绑定 `127.0.0.1:8087`；JWT 保持开启。官方示例应用用于本机文件验证，没有接入业务项目版本或用户权限，不能直接作为公司的正式文档管理系统。

## 与业务平台的关系

目前从项目下载报价单，再上传到本机 Office 编辑。这里的修改保存在 Office 文档副本中，不会反向改变项目设备、价格来源、知识检查或已经保存的报价版本。

将编辑器嵌入项目页面时，仍需要由业务后端提供文件地址、签名配置和保存回调，并为修改后的文件生成独立修订；不能把 Excel 手工改价当成已经通过业务检查。这次只部署可用的本机编辑环境。

ONLYOFFICE 的显示与重算验证单独记录，不能等同于 Microsoft Excel 或 WPS 桌面端兼容性验收。

官方参考：[Docker 镜像](https://github.com/ONLYOFFICE/Docker-DocumentServer)、[文件保存回调](https://api.onlyoffice.com/docs/docs-api/get-started/how-it-works/saving-file/)。
