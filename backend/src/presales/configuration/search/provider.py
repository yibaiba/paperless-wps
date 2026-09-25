import httpx


class SearchModelClient:
    def __init__(self, client: httpx.Client, settings):
        self.client = client
        self.settings = settings

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        settings = self._settings()
        payload = {"model": settings.embedding_model, "input": texts}
        body = self._request(url=settings.embedding_url, payload=payload, label="Embedding")
        try:
            rows = sorted(body["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in rows]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Embedding 服务返回格式错误") from error
        if len(vectors) != len(texts):
            raise ValueError("Embedding 服务返回的向量数量与输入不一致")
        self._validate_vectors(vectors, settings.embedding_dimensions)
        return vectors

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        settings = self._settings()
        payload = {
            "model": settings.reranker_model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }
        body = self._request(url=settings.reranker_url, payload=payload, label="Reranker")
        scores = [None] * len(documents)
        try:
            for item in body["results"]:
                scores[item["index"]] = float(item["relevance_score"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError("Reranker 服务返回格式错误") from error
        if any(score is None for score in scores):
            raise ValueError("Reranker 服务没有返回全部候选的分数")
        return scores

    def _settings(self):
        if self.settings is None:
            raise ValueError("尚未配置智能检索模型，请先在产品整理中配置")
        return self.settings

    def _request(self, *, url, payload, label):
        headers = {}
        if self.settings.api_key:
            headers["Authorization"] = "Bearer " + self.settings.api_key
        try:
            response = self.client.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ValueError(f"{label} 请求超时，请检查本地模型服务") from error
        except httpx.RequestError as error:
            raise ValueError(f"无法连接 {label} 服务，请检查地址和网络") from error
        if response.status_code >= 400:
            raise ValueError(f"{label} 服务返回 HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise ValueError(f"{label} 服务没有返回有效 JSON") from error

    @staticmethod
    def _validate_vectors(vectors, dimensions):
        if any(not isinstance(vector, list) or len(vector) != dimensions for vector in vectors):
            raise ValueError(f"Embedding 向量维度必须为 {dimensions}")
        if any(not isinstance(value, int | float) for vector in vectors for value in vector):
            raise ValueError("Embedding 向量包含非数字内容")
