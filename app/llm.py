import httpx

from .config import settings
from .prompts.triage import TRIAGE_FORMAT, TRIAGE_PROMPT


class LLMClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout or settings.llm_timeout_seconds

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> str:
        model = model or settings.model_name
        print(f"[llm] calling model: {model}")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]

    async def triage(self, message: str, temperature: float = 0.0) -> str:
        """Classify urgency with the tiny triage model via Ollama's native API.

        Uses the `format` parameter so the model is constrained to emit the
        JSON schema defined by TRIAGE_FORMAT.
        """
        model = settings.triage_model_name
        print(f"[llm] calling triage model: {model}")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": TRIAGE_PROMPT.format(message=message)}],
            "stream": False,
            "temperature": temperature,
            "format": TRIAGE_FORMAT,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["message"]["content"]


llm = LLMClient()