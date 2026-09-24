import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, model_validator

from ..common import Input, Text


class ModelSettings(Input):
    base_url: Text
    model: Text
    api_key: str = ""
    timeout_seconds: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def valid_address(self):
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("服务地址须为 http 或 https URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("服务地址不能带账号、密码、查询参数或片段")
        return self


class PrivateSettings:
    """Local-only deployment; keys are stored outside source in a mode-0600 file."""

    def __init__(self, path: Path):
        self.path = path

    def read(self):
        if not self.path.exists():
            return None
        try:
            return ModelSettings.model_validate_json(self.path.read_text())
        except ValidationError:
            raise ValueError("本地模型配置格式无效，请检查私有配置文件") from None

    def public(self):
        settings = self.read()
        if settings is None:
            return dict(configured=False, base_url="", model="", has_key=False, timeout_seconds=60)
        return dict(
            configured=True,
            has_key=bool(settings.api_key),
            **settings.model_dump(exclude={"api_key"}),
        )

    def write(self, data: ModelSettings):
        previous = self.read()
        values = data.model_dump()
        if not data.api_key and previous and data.base_url == previous.base_url:
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
