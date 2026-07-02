from __future__ import annotations

import json

import httpx
from pydantic import BaseModel

from scireview.llm.base import LLMBackend, LLMGenerationError, LLMMessage, LLMUnavailableError


class OllamaBackend(LLMBackend):
    """Ollama chat backend with optional structured JSON output."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: int,
        temperature: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    def generate(
        self,
        messages: list[LLMMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if response_schema is not None:
            payload["format"] = response_schema.model_json_schema()
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(f"Ollama is unavailable at {self.base_url}") from exc
        except httpx.HTTPError as exc:
            raise LLMGenerationError(f"Ollama request failed: {exc}") from exc
        data = response.json()
        content = data.get("message", {}).get("content")
        if not isinstance(content, str):
            raise LLMGenerationError(f"Unexpected Ollama response: {json.dumps(data)[:500]}")
        return content
