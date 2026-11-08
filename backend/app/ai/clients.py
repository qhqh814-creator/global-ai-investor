"""AI clients (P3): local Ollama (experiment) and DeepSeek (formal stage).

Both return raw JSON text; the service validates it against AnalysisResult.
API keys are read from environment or the local settings store (never logged).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx


class AiUnavailable(RuntimeError):
    """Raised when the configured AI backend cannot be used."""


@dataclass
class AiConfig:
    provider: str = "ollama"
    model: str = "qwen3:8b"
    base_url: str = "http://127.0.0.1:11434"
    api_key: str | None = None
    timeout: float = 120.0


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "event_type": {"type": "string"},
        "sentiment": {"enum": ["positive", "negative", "neutral"]},
        "materiality": {"enum": ["L1", "L2", "L3", "L4"]},
        "summary": {"type": "string"},
        "stocks": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string", "minLength": 6},
                    "source_url": {"type": "string"},
                    "published_at": {"type": ["string", "null"]},
                },
                "required": ["quote", "source_url"],
            },
        },
    },
    "required": ["event_type", "sentiment", "materiality", "summary", "stocks", "evidence"],
}
SYSTEM_PROMPT = """你是中国A股公告/新闻分析助手。只依据给定文本输出严格JSON，不得编造。
JSON字段：
- event_type: 字符串（如 业绩预告/重大合同/回购/监管处罚/行业政策/其他）
- sentiment: "positive" | "negative" | "neutral"
- materiality: "L1" | "L2" | "L3" | "L4"（L1关注、L2重要、L3重大、L4紧急）
- summary: 不超过200字中文摘要
- stocks: 涉及的A股代码数组（无法确定则空数组）
- evidence: 数组，至少1条，每条 {"quote": 原文片段（必须来自输入文本）, "source_url": 输入中的链接, "published_at": 输入中的时间或null}
如果输入信息不足以判断，materiality 用 L1，summary 说明信息不足，但 evidence 仍必须引用原文。"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class OllamaClient:
    def __init__(self, config: AiConfig):
        self.config = config

    def available(self) -> bool:
        try:
            resp = httpx.get(f"{self.config.base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def analyze(self, user_prompt: str) -> dict:
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": ANALYSIS_SCHEMA,
            "options": {"temperature": 0.1, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                resp = client.post(f"{self.config.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                content = resp.json().get("message", {}).get("content", "")
        except Exception as exc:  # noqa: BLE001
            raise AiUnavailable(f"ollama request failed: {exc}") from exc
        return _extract_json(content)


class DeepSeekClient:
    def __init__(self, config: AiConfig):
        self.config = config

    def available(self) -> bool:
        return bool(self.config.api_key)

    def analyze(self, user_prompt: str) -> dict:
        if not self.config.api_key:
            raise AiUnavailable("deepseek api key is not configured")
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model or "deepseek-chat",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise AiUnavailable(f"deepseek request failed: {exc}") from exc
        return _extract_json(content)


def make_client(provider: str, model: str | None = None) -> OllamaClient | DeepSeekClient:
    provider = (provider or os.environ.get("GAI_AI_PROVIDER", "ollama")).lower()
    if provider == "ollama":
        return OllamaClient(
            AiConfig(
                provider="ollama",
                model=model or os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            )
        )
    if provider == "deepseek":
        return DeepSeekClient(
            AiConfig(
                provider="deepseek",
                model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
            )
        )
    raise AiUnavailable(f"unknown AI provider: {provider}")


