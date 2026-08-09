from __future__ import annotations

import httpx
from super_agent.providers.base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    """
    Minimal adapter for services exposing an OpenAI-compatible chat-completions endpoint.
    Keeps vendor HTTP details outside the orchestrator.
    """

    def __init__(self, api_base: str, api_key: str, model: str, timeout: float = 90.0):
        if not model:
            raise ValueError("AGENT_MODEL is required.")
        if not api_key:
            raise ValueError("AGENT_API_KEY is required.")
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(self, prompt: str, system: str = "") -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]
