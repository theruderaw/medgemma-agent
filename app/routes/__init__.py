"""LLM function-calling / routing-decision logic — not HTTP routes.

HTTP endpoints live in ``app/main.py``. This package parses the router
model's tool calls into typed routing decisions. A future step may rename
it to ``app/routing`` so real HTTP route modules can live under ``app/routes``.
"""

from .function_calling import (
    RouteCategory,
    RouteDecision,
    parse_tool_calls,
)

__all__ = [
    "RouteCategory",
    "RouteDecision",
    "parse_tool_calls",
]
