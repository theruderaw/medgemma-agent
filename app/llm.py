import re

import httpx
from dataclasses import dataclass

from .config import settings
from .prompts.triage import TRIAGE_FORMAT, TRIAGE_PROMPT


@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict]


def extract_answer(content: str) -> str:
    """Extract the model's actual reply from a Qwen3 response.

    Qwen3 sometimes precedes its real answer with a reasoning preamble and
    wraps the reply in `<response>...</response>` tags. When the tags are
    present the inner text is returned; otherwise the content is returned
    unchanged (trimmed).
    """
    text = content.strip()
    match = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


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
            "enable_thinking": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> ChatResult:
        """Chat with tool-calling enabled (OpenAI-compatible /v1/chat/completions).

        Returns both the reply text and any tool calls the model requested, so
        the caller can decide whether to execute a tool (e.g. the specialist).
        """
        model = model or settings.model_name
        print(f"[llm] calling model with tools: {model}")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": "auto",
            "enable_thinking": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        message = data["choices"][0]["message"]
        return ChatResult(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
        )

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