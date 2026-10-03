import pytest
from sqlalchemy import select

from presales.configuration.models import Entity
from presales.quotation.artifacts import FileArtifacts

from .test_list_mcp import call, saved_project


def test_second_file_failure_leaves_no_published_file_or_receipt(client, catalog, tmp_path):
    class FailingFiles(FileArtifacts):
        count = 0

        def write(self, identity, content):
            self.count += 1
            if self.count == 2:
                raise OSError("isolated disk failure")
            return super().write(identity, content)

    client.app.state.artifact_files = FailingFiles(tmp_path)
    saved = saved_project(client, catalog)
    request = dict(project_id=saved["project_id"], revision=1, output="both", operation_id="atomic")
    with pytest.raises(OSError, match="disk failure"):
        client.post("/api/list-tools/list_export", json=request)
    assert list(tmp_path.iterdir()) == []
    with client.app.state.session_factory() as session:
        assert not list(session.scalars(select(Entity).where(Entity.kind == "list_artifact")))
    client.app.state.artifact_files = FileArtifacts(tmp_path)
    result = call(client, "list_export", request)
    assert call(client, "list_export", request) == result
    assert len(list(tmp_path.glob("*.xlsx"))) == 2
    for artifact in result["artifacts"]:
        assert client.get(artifact["download_path"]).status_code == 200


def test_lost_commit_acknowledgment_retains_files_for_original_request_retry(
    client, catalog, tmp_path, monkeypatch
):
    from sqlalchemy.orm import Session

    saved = saved_project(client, catalog)
    client.app.state.artifact_files = FileArtifacts(tmp_path)
    request = dict(project_id=saved["project_id"], revision=1, output="both", operation_id="ack")
    real_commit = Session.commit

    def lost_ack(session):
        real_commit(session)
        raise OSError("isolated lost commit acknowledgment")

    monkeypatch.setattr(Session, "commit", lost_ack)
    with pytest.raises(OSError, match="lost commit"):
        client.post("/api/list-tools/list_export", json=request)
    monkeypatch.setattr(Session, "commit", real_commit)
    result = call(client, "list_export", request)
    assert len(list(tmp_path.glob("*.xlsx"))) == 2
    for artifact in result["artifacts"]:
        assert client.get(artifact["download_path"]).status_code == 200
