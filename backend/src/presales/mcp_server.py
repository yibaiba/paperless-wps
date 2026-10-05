"""Local stdio entrypoint. stdout belongs exclusively to the MCP protocol."""

import logging
import os
from pathlib import Path
from typing import Any

import zen
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from presales.lists.facade import ListApplication
from presales.lists.schemas import (
    CatalogSearch,
    CheckList,
    CreateList,
    ExportList,
    GetList,
    PlanList,
    SaveList,
    SystemsList,
    UpdateList,
)
from presales.quotation.artifacts import FileArtifacts
from presales.quotation.excel import ExcelRenderer
from presales.quotation.template import TEMPLATE_PATH
from presales.rules.engine import ZenQuantityEngine
from presales.rules.repository import RuleConflict
from presales.storage import database_factory


def create_server(*, session_factory, engine, renderer, files, web_origin="http://127.0.0.1:5176"):
    server = MCPServer(
        "艾索清单与报价",
        instructions=(
            "先用 systems_list 获取需求字段，以 requirements_patch 提交客户需求，"
            "再 list_plan 生成提案。"
            "用 list_get proposal_questions 区分客户需求与内部知识缺口；缺口不能由模型编造。"
            "proposal_apply 整批采用所选方案，只有采用后才改变实际清单。只采用有出处的配置及价格。"
            "list_update 操作需要稳定对象 ID；配套通过 list_get issues 读取建议及计算指纹。"
            "每次写入提供预期修订与 operation_id，重试保持相同 ID 和内容。"
            "list_check 后用返回的 check_fingerprint 保存；保存是草稿，不是人工认证。"
            "list_save 的 revision 是草稿修订；导出必须使用 project_revision 项目修订。"
            "用 list_get 的 template/quotation/issues/evidence/changes 视图按需读取。"
            "用途与容量用 device_usages 视图分页读取，可按 device_id 定位；"
            "usage_projection.current 为 false 时先显式重新检查，不将历史结果当作当前验证。"
            "价格更新用 price_updates 视图预览，再用 price_versions_adopt 明确采用所选修订。"
        ),
    )

    def call(name, arguments):
        with session_factory() as session:
            try:
                return ListApplication(
                    session, engine=engine, renderer=renderer, files=files, web_origin=web_origin
                ).call(name, arguments)
            except (RuleConflict, ValueError) as error:
                # Expected business failures must reach the Agent, not a generic SDK crash.
                raise ToolError(str(error)) from error

    @server.tool(structured_output=True)
    def systems_list(request: SystemsList) -> dict[str, Any]:
        """查询系统定义、角色、知识包及未映射历史系统；支持分页。"""
        return call("systems_list", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def catalog_search(request: CatalogSearch) -> dict[str, Any]:
        """找产品；指定 draft_id 和 requirement_id 时按草稿知识快照检查候选。"""
        return call("catalog_search", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def catalog_get(
        variant_id: str, draft_id: str | None = None, on_date: str | None = None
    ) -> dict[str, Any]:
        """查看具体配置、原始资料和价格列；草稿上下文下返回固定版本依据。"""
        return call("catalog_get", dict(variant_id=variant_id, draft_id=draft_id, on_date=on_date))

    @server.tool(structured_output=True)
    def list_search(
        query: str = "", *, offset: int = 0, limit: int = 50, project_id: str | None = None
    ) -> dict[str, Any]:
        """查找项目及当前修订；指定 project_id 分页读取保存版本。"""
        return call(
            "list_search", dict(query=query, offset=offset, limit=limit, project_id=project_id)
        )

    @server.tool(structured_output=True)
    def list_create(request: CreateList) -> dict[str, Any]:
        """创建持久草稿，或基于明确的项目保存版本建立改单草稿。"""
        return call("list_create", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def list_plan(request: PlanList) -> dict[str, Any]:
        """按固定草稿生成持久提案，不改变设备；按 next_offset 和 proposal_id 延迟生成替代方案。"""
        return call("list_plan", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def list_get(request: GetList) -> dict[str, Any]:
        """分页读取清单、报价、检查及用途；device_usages 视图可用 device_id 筛选。"""
        return call("list_get", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def list_update(request: UpdateList) -> dict[str, Any]:
        """原子编辑需求、配置、供货、配套和报价；未指定数量不按一台补全。"""
        return call("list_update", request.model_dump(mode="json", exclude_unset=True))

    @server.tool(structured_output=True)
    def list_check(request: CheckList) -> dict[str, Any]:
        """检查草稿并保存计算指纹；明确刷新才采用最新知识。详情由 list_get 查询。"""
        return call("list_check", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def list_save(request: SaveList) -> dict[str, Any]:
        """保存已检查的当前草稿为新项目修订；不自动人工确认。"""
        return call("list_save", request.model_dump(mode="json"))

    @server.tool(structured_output=True)
    def list_export(request: ExportList) -> dict[str, Any]:
        """从明确的保存修订导出清单或公司报价模板，返回文件位置与下载路径。"""
        return call("list_export", request.model_dump(mode="json"))

    return server


def main():
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("缺少 DATABASE_URL，请配置本地业务数据库")
    logging.basicConfig(level=logging.INFO)
    server = create_server(
        session_factory=database_factory(url),
        engine=ZenQuantityEngine(zen.ZenEngine()),
        renderer=ExcelRenderer(TEMPLATE_PATH),
        files=FileArtifacts(os.environ.get("PRESALES_ARTIFACT_DIR", str(root / "data/exports"))),
        web_origin=os.environ.get("PRESALES_WEB_ORIGIN", "http://127.0.0.1:5176"),
    )
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
