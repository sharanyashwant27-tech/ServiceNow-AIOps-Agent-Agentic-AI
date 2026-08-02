from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """Unified LLM adapter for GPT / Claude / Llama (Ollama) / local heuristic."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider(self) -> str:
        return (self.settings.llm_provider or "local").lower()

    async def complete(self, prompt: str, system: str = "You are an AIOps assistant.") -> dict[str, Any]:
        provider = self.provider
        try:
            if provider == "openai" and self.settings.openai_api_key:
                return await self._openai(prompt, system)
            if provider == "anthropic" and self.settings.anthropic_api_key:
                return await self._anthropic(prompt, system)
            if provider == "ollama":
                return await self._ollama(prompt, system)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM provider %s failed, using local: %s", provider, exc)
        return self._local(prompt)

    async def _openai(self, prompt: str, system: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": self.settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return {"provider": "openai", "model": self.settings.llm_model, "text": text}

    async def _anthropic(self, prompt: str, system: str) -> dict[str, Any]:
        model = self.settings.llm_model if "claude" in self.settings.llm_model else "claude-3-5-sonnet-latest"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []))
            return {"provider": "anthropic", "model": model, "text": text}

    async def _ollama(self, prompt: str, system: str) -> dict[str, Any]:
        model = self.settings.llm_model or "llama3"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"provider": "ollama", "model": model, "text": data.get("message", {}).get("content", "")}

    def _local(self, prompt: str) -> dict[str, Any]:
        snippet = prompt.strip().replace("\n", " ")
        text = (
            "Local heuristic response (configure OPENAI_API_KEY / ANTHROPIC_API_KEY / Ollama for full LLM). "
            f"Context digest: {snippet[:280]}"
        )
        return {"provider": "local", "model": "heuristic", "text": text}


llm_provider = LLMProvider()
