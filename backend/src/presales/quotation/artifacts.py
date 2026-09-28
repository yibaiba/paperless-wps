from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from presales.configuration.common import Entities, view
from presales.lists.queries import saved_revision
from presales.lists.receipts import once

from .calculation import with_quotation
from .template import TEMPLATE_SHA256


class FileArtifacts:
    """Local artifact storage; filenames are server-generated UUIDs only."""

    def __init__(self, root):
        self.root = Path(root)

    def path(self, identity):
        return self.root / (str(UUID(identity)) + ".xlsx")

    def write(self, identity, content):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(identity)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return str(path.resolve())

    def verified_path(self, artifact):
        path = self.path(artifact["id"])
        if not path.is_file():
            raise ValueError("导出文件缺失，请重新导出")
        if sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("导出文件校验失败，文件已变化")
        return path


class ListExports:
    def __init__(self, session, *, repository, renderer, files, web_origin):
        self.session, self.repository = session, repository
        self.renderer, self.files = renderer, files
        self.web_origin = web_origin.rstrip("/")

    def export(self, request):
        result = once(
            self.session,
            namespace="list_export",
            request=request,
            perform=lambda: self._export(request),
        )
        for artifact in result["artifacts"]:
            self.files.verified_path(artifact)
        return result

    def _export(self, request):
        saved = with_quotation(
            saved_revision(
                self.repository, project_id=request.project_id, revision=request.revision
            )
        )
        kinds = ("configuration", "quotation") if request.output == "both" else (request.output,)
        if "quotation" in kinds and saved["configuration"].get("quotation") is None:
            raise ValueError("该保存版本尚未填写报价信息")
        rendered = [(kind, getattr(self.renderer, kind)(saved)) for kind in kinds]
        artifacts = []
        for kind, content in rendered:
            identity = str(uuid5(NAMESPACE_URL, f"presales-export:{request.operation_id}:{kind}"))
            filename = (
                "设备清单" if kind == "configuration" else "报价单"
            ) + f"-v{request.revision}.xlsx"
            path = self.files.write(identity, content)
            artifact = Entities(self.session).save(
                "list_artifact",
                dict(
                    project_id=request.project_id,
                    project_revision=request.revision,
                    output=kind,
                    filename=filename,
                    sha256=sha256(content).hexdigest(),
                    path=path,
                    template_sha256=TEMPLATE_SHA256 if kind == "quotation" else None,
                    download_path=f"/api/list-artifacts/{identity}",
                    download_url=f"{self.web_origin}/api/list-artifacts/{identity}",
                ),
                create_id=identity,
            )
            artifacts.append(artifact)
        return dict(project_id=request.project_id, revision=request.revision, artifacts=artifacts)

    def download(self, identity):
        artifact = view(Entities(self.session).get(identity, kind="list_artifact"))
        return artifact, self.files.verified_path(artifact)
