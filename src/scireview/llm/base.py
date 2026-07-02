from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class LLMUnavailableError(RuntimeError):
    """Raised when a configured LLM backend cannot be reached."""


class LLMGenerationError(RuntimeError):
    """Raised when a model response cannot be generated."""


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMBackend(Protocol):
    def generate(
        self,
        messages: list[LLMMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        """Generate a response, optionally constrained by a Pydantic JSON schema."""
