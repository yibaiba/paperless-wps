import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from ..common import Input, Text
from ..models import SEARCH_EMBEDDING_DIMENSIONS


class SearchSettings(Input):
    embedding_url: Text
    embedding_model: Text
    reranker_url: Text
    reranker_model: Text
    api_key: str = ""
    embedding_dimensions: int = Field(default=SEARCH_EMBEDDING_DIMENSIONS, gt=0)
    timeout_seconds: int = Field(default=60, gt=0)
    batch_size: int = Field(default=16, gt=0, le=128)

    @model_validator(mode="after")
    def valid_settings(self):
        for name, value in (
            ("Embedding", self.embedding_url),
            ("Reranker", self.reranker_url),
        ):
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"{name} 地址须为 http 或 https URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"{name} 地址不能带账号、密码、查询参数或片段")
        if self.embedding_dimensions != SEARCH_EMBEDDING_DIMENSIONS:
            raise ValueError(f"当前搜索索引维度固定为 {SEARCH_EMBEDDING_DIMENSIONS}")
        return self


class PrivateSearchSettings:
    def __init__(self, path: Path):
        self.path = path

    def read(self):
        if not self.path.exists():
            return None
        try:
            return SearchSettings.model_validate_json(self.path.read_text())
        except ValueError:
            raise ValueError("本地智能检索配置格式无效，请检查私有配置文件") from None

    def public(self):
        settings = self.read()
        if settings is None:
            return dict(
                configured=False,
                embedding_url="",
                embedding_model="",
                reranker_url="",
                reranker_model="",
                has_key=False,
                embedding_dimensions=SEARCH_EMBEDDING_DIMENSIONS,
                timeout_seconds=60,
                batch_size=16,
            )
        return dict(
            configured=True,
            has_key=bool(settings.api_key),
            **settings.model_dump(exclude={"api_key"}),
        )

    def write(self, data: SearchSettings):
        previous = self.read()
        values = data.model_dump()
        same_endpoints = (
            previous
            and data.embedding_url == previous.embedding_url
            and data.reranker_url == previous.reranker_url
        )
        if not data.api_key and same_endpoints:
            values["api_key"] = previous.api_key
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(values, file)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.public()
