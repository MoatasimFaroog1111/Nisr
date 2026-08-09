from __future__ import annotations

import httpx


class OpenAICompatibleAdapter:
    def __init__(self, api_base: str, api_key: str, model: str, timeout: float = 90.0):
        if not model:
            raise ValueError("AGENT_MODEL is required")
        if not api_key:
            raise ValueError("AGENT_API_KEY is required")
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def complete(self, prompt: str, system: str = "") -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._api_base}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]
