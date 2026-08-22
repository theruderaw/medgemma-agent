"""Ollama client wrapper plus reply parsing / live stream extraction."""

from .client import LLMClient, llm
from .parsing import StreamExtractor, extract_answer

__all__ = ["LLMClient", "llm", "StreamExtractor", "extract_answer"]
