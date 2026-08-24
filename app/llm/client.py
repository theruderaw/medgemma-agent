import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from ..core.config import settings
from ..core.logging import get_logger
from ..prompts.composed import GUARD_PROMPT, TRIAGE_PROMPT
from ..prompts.formats import GUARD_FORMAT, SPECIALIST_FORMAT, TRIAGE_FORMAT

logger = get_logger("app.llm.client")


def _log_usage(model: str, data: dict) -> None:
    """Best-effort structured log of Ollama usage counters (native /api/chat)."""
    eval_count = data.get("eval_count")
    prompt_eval_count = data.get("prompt_eval_count")
    if eval_count is not None or prompt_eval_count is not None:
        logger.info(
            "llm.usage",
            model=model,
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
        )


@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict]


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
        """Single-shot chat completion (OpenAI-compatible /v1/chat/completions).

        Returns the full reply text; used for synthesis when no token
        streaming is requested and for routing without tools.
        """
        model = model or settings.model_name
        logger.info("llm.chat", model=model, temperature=temperature)
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

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat completion (OpenAI-compatible /v1/chat/completions).

        Yields content deltas as the model generates them (``stream: true``).
        """
        model = model or settings.model_name
        logger.info("llm.chat_stream", model=model, temperature=temperature)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "enable_thinking": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content

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
        logger.info("llm.chat_with_tools", model=model, temperature=temperature)
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

    async def chat_with_images(
        self,
        messages: list[dict],
        images: list[str],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> str:
        """Chat with base64 image attachments via Ollama's native /api/chat.

        Images ride on the last user message as an ``images`` array of base64
        strings — the format Ollama's multimodal models (e.g. medgemma1.5:4b)
        accept.
        """
        model = model or settings.specialist_model_name
        logger.info("llm.chat_with_images", model=model, temperature=temperature, images=len(images))
        payload_messages = self._attach_images(messages, images)
        payload = {
            "model": model,
            "messages": payload_messages,
            "stream": False,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return data["message"]["content"]

    async def chat_with_images_stream(
        self,
        messages: list[dict],
        images: list[str],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a multimodal chat completion (native /api/chat, ``stream: true``).

        Yields content deltas as the model generates them, so long specialist
        (vision) calls surface token-by-token instead of blocking silently.
        """
        model = model or settings.specialist_model_name
        logger.info("llm.chat_with_images_stream", model=model, temperature=temperature, images=len(images))
        payload_messages = self._attach_images(messages, images)
        payload = {
            "model": model,
            "messages": payload_messages,
            "stream": True,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = (chunk.get("message") or {}).get("content")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break

    async def specialist_stream(
        self,
        messages: list[dict],
        *,
        images: list[str] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
        output_format: dict | None = None,
    ) -> AsyncIterator[str]:
        """Stream a format-constrained structured assessment while it is generated.

        Native /api/chat with BOTH ``stream: true`` and the ``format``
        constraint: the model emits the JSON object incrementally (the longest
        stage of every turn), so raw deltas surface token-by-token instead of
        blocking silently. The caller accumulates deltas; the completed text
        is still a format-constrained JSON document ready for parsing.
        Optional base64 ``images`` ride on the last user message.
        ``output_format`` lets an Addon supply its own constraint; it
        defaults to the clinical-assessment specialist schema.
        """
        model = model or settings.specialist_model_name
        logger.info(
            "llm.specialist_stream",
            model=model,
            temperature=temperature,
            has_image=images is not None,
        )
        payload_messages = self._attach_images(messages, images or [])
        payload = {
            "model": model,
            "messages": payload_messages,
            "stream": True,
            "temperature": temperature,
            "format": output_format or SPECIALIST_FORMAT,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = (chunk.get("message") or {}).get("content")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break

    @staticmethod
    def _attach_images(messages: list[dict], images: list[str]) -> list[dict]:
        payload_messages = [dict(m) for m in messages]
        for message in reversed(payload_messages):
            if message.get("role") == "user":
                message["images"] = list(images)
                break
        return payload_messages

    async def guard(
        self,
        *,
        message: str,
        urgency: str,
        response: str,
    ) -> str:
        """Judge a draft reply against the output-guardrail rules.

        Uses the small guard model with Ollama's native ``format``
        constraint, so the verdict is always the expected JSON object
        regardless of model drift.
        """
        prompt = (
            GUARD_PROMPT.replace("{message}", message)
            .replace("{urgency}", urgency)
            .replace("{response}", response)
        )
        logger.info("llm.guard", model=settings.guard_model_name)
        payload = {
            "model": settings.guard_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0,
            "format": GUARD_FORMAT,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        _log_usage(settings.guard_model_name, data)
        return data["message"]["content"]

    async def triage(
        self,
        message: str,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> str:
        """Classify urgency with the extended triage schema.

        Text-only turns use the tiny triage model; turns with an attached
        image are dispatched to the multimodal vision triage model. Both are
        constrained to the same JSON schema via Ollama's native `format`
        parameter, so the output shape never drifts between tiers. An explicit
        ``model`` overrides both tiers (used by evals/benchmarks).
        """
        model = model or settings.triage_model_name
        prompt = TRIAGE_PROMPT.replace("{message}", message)
        payload_message = {"role": "user", "content": prompt}
        logger.info("llm.triage", model=model, temperature=temperature)
        payload = {
            "model": model,
            "messages": [payload_message],
            "stream": False,
            "temperature": temperature,
            "format": TRIAGE_FORMAT,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        _log_usage(model, data)
        return data["message"]["content"]


llm = LLMClient()