"""Deterministic fake Ollama server for integration tests.

Runs as a thread inside the pytest process (shared memory for request
recording) while the real Celery worker subprocess talks to it over HTTP —
so the suite exercises the genuine network protocol boundary without any
model downloads.

Dispatch rules mirror app/llm/client.py exactly:
- POST /v1/chat/completions  (OpenAI-compatible)
    * has "tools"          -> router: tool_calls or plain content (router_mode)
    * stream: true         -> SSE data: lines with delta.content + [DONE]
    * otherwise            -> plain content reply
- POST /api/chat             (Ollama native)
    * format is TRIAGE_FORMAT     -> triage verdict JSON
    * format is GUARD_FORMAT      -> output-guardrail verdict JSON
    * format is SPECIALIST_FORMAT -> structured specialist assessment JSON
    * stream: true, no format     -> JSON-lines content chunks, done:true
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.features.medication_interaction import MEDICATION_QUERY_FORMAT
from app.prompts.guard import GUARD_FORMAT
from app.prompts.specialist import SPECIALIST_FORMAT
from app.prompts.triage import TRIAGE_FORMAT

DEFAULT_TOOL_ARGUMENTS = {"reason": "user reports symptoms"}

SPECIALIST_TOOL_CALL = {
    "id": "call_fake_specialist",
    "type": "function",
    "function": {
        "name": "call_medical_specialist",
        "arguments": json.dumps(DEFAULT_TOOL_ARGUMENTS),
    },
}

DEFAULT_CHAT_REPLY = "Stay hydrated and monitor your symptoms."

TRIAGE_ROUTINE_JSON = json.dumps({"urgency": "routine"})
GUARD_CLEAN_JSON = json.dumps(
    {
        "diagnostic_claim": False,
        "missing_disclaimer": False,
        "emergency_bypass": False,
        "triage_contradiction": False,
        "unsafe_wording": False,
        "reasoning": "no violations",
    }
)
SPECIALIST_RESULT_JSON = json.dumps(
    {
        "summary": "Possible mild irritation.",
        "findings": ["mild redness"],
        "visual_findings": [],
        "red_flag_concerns": [],
        "limitations": ["assessment limited to user text"],
        "uncertain": False,
    }
)


class FakeOllama:
    """Configurable stand-in for the Ollama HTTP API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: list[dict] = []
        self._router_mode = "specialist"
        self._router_tool_name = "call_medical_specialist"
        self._chat_reply = DEFAULT_CHAT_REPLY
        self._triage_json = TRIAGE_ROUTINE_JSON
        self._guard_json = GUARD_CLEAN_JSON
        self._specialist_json = SPECIALIST_RESULT_JSON
        self._medication_json = json.dumps({"drug_a": "warfarin", "drug_b": "ibuprofen"})
        self._fail_router_remaining = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread: threading.Thread | None = None

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # silence stderr noise
                pass

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    body = {}

                if self.path == "/__config":
                    outer.configure(**body)
                    return outer._respond(self, 200, {"ok": True})
                if self.path == "/__reset":
                    outer.reset()
                    return outer._respond(self, 200, {"ok": True})

                with outer._lock:
                    outer.requests.append({"path": self.path, "body": body})
                    fail_router = (
                        self.path == "/v1/chat/completions"
                        and "tools" in body
                        and outer._fail_router_remaining > 0
                    )
                    if fail_router:
                        outer._fail_router_remaining -= 1
                if fail_router:
                    return outer._respond(self, 500, {"error": "fake model-server outage"})
                status, payload = outer._dispatch(self.path, body)
                if payload is None:
                    return outer.respond_stream(self, self.path, body)
                return outer._respond(self, status, payload)

        return Handler

    def respond_stream(self, handler: BaseHTTPRequestHandler, path: str, body: dict) -> None:
        """Streaming response: OpenAI SSE for /v1/*, Ollama JSON-lines for native."""
        reply = self._content_for_format(body) if path == "/api/chat" else self._chat_reply
        handler.send_response(200)
        if path == "/v1/chat/completions":
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            for chunk in stream_openai_chunks(reply):
                handler.wfile.write(chunk)
            handler.wfile.flush()
        else:
            handler.send_header("Content-Type", "application/x-ndjson")
            handler.end_headers()
            for line in stream_native_chunks(reply):
                handler.wfile.write(line)
            handler.wfile.flush()

    @staticmethod
    def _respond(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _dispatch(self, path: str, body: dict) -> tuple[int, dict | None]:
        """Return (status, payload); payload None means a streaming response."""
        if path == "/v1/chat/completions":
            if body.get("stream") and "tools" not in body:
                return 200, None
            return 200, self._openai_response(body)
        if path == "/api/chat":
            if body.get("stream"):
                return 200, None
            return 200, self._native_response(body)
        return 404, {"error": f"unknown path {path}"}

    def _openai_response(self, body: dict) -> dict:
        if body.get("tools"):
            if self._router_mode == "specialist":
                tool_call = {
                    "id": "call_fake_feature",
                    "type": "function",
                    "function": {
                        "name": self._router_tool_name,
                        "arguments": json.dumps(DEFAULT_TOOL_ARGUMENTS),
                    },
                }
                message = {"content": "", "tool_calls": [tool_call]}
            else:
                message = {"content": self._chat_reply}
            return {"choices": [{"message": message}]}
        return {"choices": [{"message": {"content": self._chat_reply}}]}

    def _content_for_format(self, body: dict) -> str:
        fmt = body.get("format")
        if fmt == TRIAGE_FORMAT:
            return self._triage_json
        if fmt == GUARD_FORMAT:
            return self._guard_json
        if fmt == SPECIALIST_FORMAT:
            return self._specialist_json
        if fmt == MEDICATION_QUERY_FORMAT:
            return self._medication_json
        return self._chat_reply

    def _native_response(self, body: dict) -> dict:
        content = self._content_for_format(body)
        return {
            "message": {"role": "assistant", "content": content},
            "done": True,
            "eval_count": 11,
            "prompt_eval_count": 22,
        }

    # -- control surface (same-process helpers; /__config mirrors these) ----

    def configure(
        self,
        *,
        router_mode: str | None = None,
        router_tool_call_name: str | None = None,
        chat_reply: str | None = None,
        triage_json: str | None = None,
        guard_json: str | None = None,
        specialist_json: str | None = None,
        medication_json: str | None = None,
    ) -> None:
        with self._lock:
            if router_mode is not None:
                self._router_mode = router_mode
            if router_tool_call_name is not None:
                self._router_tool_name = router_tool_call_name
            if chat_reply is not None:
                self._chat_reply = chat_reply
            if triage_json is not None:
                self._triage_json = triage_json
            if guard_json is not None:
                self._guard_json = guard_json
            if specialist_json is not None:
                self._specialist_json = specialist_json
            if medication_json is not None:
                self._medication_json = medication_json

    def fail_next_router_calls_with(self, status: int = 500, count: int = 999) -> None:
        """Serve `status` for the next `count` router calls (permanent-failure paths)."""
        with self._lock:
            self._fail_router_remaining = count
            self._fail_router_status = status

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self._router_mode = "specialist"
            self._router_tool_name = "call_medical_specialist"
            self._chat_reply = DEFAULT_CHAT_REPLY
            self._triage_json = TRIAGE_ROUTINE_JSON
            self._guard_json = GUARD_CLEAN_JSON
            self._specialist_json = SPECIALIST_RESULT_JSON
            self._medication_json = json.dumps({"drug_a": "warfarin", "drug_b": "ibuprofen"})
            self._fail_router_remaining = 0

    # -- request inspection --------------------------------------------------

    def calls(self, kind: str) -> list[dict]:
        """Recorded request bodies filtered by logical call type."""
        out = []
        with self._lock:
            snapshot = list(self.requests)
        for entry in snapshot:
            body = entry["body"]
            if entry["path"] == "/v1/chat/completions":
                if "tools" in body:
                    matched = kind == "route"
                elif body.get("stream"):
                    matched = kind == "chat_stream"
                else:
                    matched = kind == "chat"
            else:
                fmt = body.get("format")
                if fmt == TRIAGE_FORMAT:
                    matched = kind == "triage"
                elif fmt == GUARD_FORMAT:
                    matched = kind == "guard"
                elif fmt == SPECIALIST_FORMAT:
                    matched = kind == "specialist"
                elif fmt == MEDICATION_QUERY_FORMAT:
                    matched = kind == "medication"
                else:
                    matched = kind == "vision_stream"
            if matched:
                out.append(body)
        return out

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def stream_openai_chunks(reply: str) -> list[bytes]:
    """Encode reply as OpenAI-style SSE data lines terminated by [DONE]."""
    lines = []
    for chunk in (reply[i : i + 8] for i in range(0, len(reply), 8)):
        delta = {"choices": [{"delta": {"content": chunk}}]}
        lines.append(b"data: " + json.dumps(delta).encode() + b"\n\n")
    lines.append(b"data: [DONE]\n\n")
    return lines


def stream_native_chunks(reply: str) -> list[bytes]:
    """Encode reply as Ollama-native JSON-lines chunks ending done:true."""
    lines = []
    for chunk in (reply[i : i + 8] for i in range(0, len(reply), 8)):
        lines.append(json.dumps({"message": {"content": chunk}, "done": False}).encode() + b"\n")
    lines.append(json.dumps({"message": {"content": ""}, "done": True}).encode() + b"\n")
    return lines
