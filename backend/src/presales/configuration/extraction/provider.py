import json

import httpx


class ModelClient:
    def __init__(self, client: httpx.Client, settings):
        self.client, self.settings = client, settings

    def complete(self, *, instruction, material):
        if self.settings is None:
            raise ValueError("尚未配置模型接口，请先在 AI 资料整理中配置")
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        try:
            response = self.client.post(
                url,
                headers={"Authorization": "Bearer " + self.settings.api_key},
                json={
                    "model": self.settings.model,
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": json.dumps(material, ensure_ascii=False)},
                    ],
                },
                timeout=self.settings.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ValueError("模型请求超时；本段未完成，可检查服务后手动重试") from error
        except httpx.RequestError as error:
            raise ValueError("无法连接模型服务，请检查服务地址和网络") from error
        if response.status_code >= 400:
            raise ValueError(
                f"模型服务返回 HTTP {response.status_code}；请检查模型名、授权和服务状态"
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ValueError("模型返回格式错误，要求纯 JSON；请查看服务的兼容接口能力") from error
