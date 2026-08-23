"""Live smoke suite: N iterations of every turn type against a running stack.

Usage:
    .venv/bin/python scripts/smoke_suite.py [BASE_URL] [N]

Requires the full stack (`make up`) with real Ollama models. Runs N rounds of:
general, symptom+triage, emergency, image-attached, /v1/triage endpoint,
features toggle round-trip, and chat-history round-trip. Exits non-zero if
any iteration lands off its expected pipeline path.
"""

import base64
import io
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
# Comma-separated subset of CHECKS names to run (default: all).
ONLY = [s.strip() for s in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
POLL_TIMEOUT = 300.0

SPECIALIST_TOOL = "call_medical_specialist"


def tiny_png_b64() -> str:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=(200, 100, 100)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def wait_result(client: httpx.Client, job_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        r = client.get(f"/v1/jobs/{job_id}")
        r.raise_for_status()
        body = r.json()
        if body["status"] == "success":
            return body["result"]
        if body["status"] == "failure":
            raise RuntimeError(f"job failed: {body.get('error')}")
        time.sleep(1)
    raise RuntimeError(f"job timed out after {POLL_TIMEOUT}s")


def turn(client: httpx.Client, message: str, **kwargs) -> dict:
    r = client.post("/v1/chat", json={"message": message, **kwargs})
    if r.status_code == 200:
        return r.json()
    if r.status_code == 202:
        return wait_result(client, r.json()["job_id"])
    raise RuntimeError(f"unexpected status {r.status_code}: {r.text[:200]}")


def event(result: dict, event_type: str) -> dict | None:
    return next((e for e in result.get("events", []) if e["event_type"] == event_type), None)


# ---------------------------------------------------------------------------
# Turn-type checks: each returns an error string or None.


def check_general(client: httpx.Client) -> str | None:
    result = turn(client, f"General question {time.time()}: what is hydration?")
    if result.get("path") != "qwen_direct":
        return f"path={result.get('path')}"
    return None


def check_symptom_triage(client: httpx.Client) -> str | None:
    result = turn(
        client,
        "I've had a dull headache behind my right eye for two days, worse in bright light.",
        triage=True,
    )
    if result.get("path") != "medical_specialist":
        return f"path={result.get('path')}"
    if not event(result, "specialist_output"):
        return "missing specialist_output event"
    return None


def check_emergency(client: httpx.Client) -> str | None:
    result = turn(client, "I am having crushing chest pain and cannot breathe")
    if result.get("path") != "emergency_override" or result.get("urgency") != "emergency":
        return f"path={result.get('path')} urgency={result.get('urgency')}"
    return None


def check_image_turn(client: httpx.Client, png: str) -> str | None:
    result = turn(
        client,
        "What do you see in this skin photo?",
        image_b64=png,
        image_mime="image/png",
    )
    if result.get("path") != "medical_specialist":
        return f"path={result.get('path')}"
    return None


def check_triage_endpoint(client: httpx.Client) -> str | None:
    r = client.post("/v1/triage", json={"message": "Mild sore throat since yesterday."})
    if r.status_code != 200:
        return f"status={r.status_code}"
    body = r.json()
    if body.get("urgency") not in ("emergency", "urgent", "routine", "self_care"):
        return f"urgency={body.get('urgency')}"
    return None


def check_features_toggle(client: httpx.Client) -> str | None:
    # A completed turn first so the session row exists (toggle rows are FK'd).
    seed = turn(client, f"Hello {time.time()}, just saying hi.")
    session_id = seed["session_id"]

    listed = client.get(f"/v1/features?session_id={session_id}").json()["features"]
    names = [f["name"] for f in listed]
    if SPECIALIST_TOOL not in names:
        return f"specialist missing from feature list: {names}"

    # Disable the specialist: reflected in the list AND in the router tool set.
    r = client.post(
        f"/v1/features/{SPECIALIST_TOOL}?session_id={session_id}",
        json={"enabled": False},
    )
    if r.status_code != 200 or r.json()["enabled"]:
        return f"toggle-off failed: {r.status_code} {r.text[:120]}"

    result = turn(client, "My elbow hurts when I lift anything.", session_id=session_id)
    tools = (event(result, "routing_decision") or {}).get("payload", {}).get("tools")
    if tools is None:
        return "routing_decision event carries no tools list"
    if SPECIALIST_TOOL in tools:
        return f"disabled specialist still offered to router: {tools}"

    # Re-enable and confirm it returns.
    r = client.post(
        f"/v1/features/{SPECIALIST_TOOL}?session_id={session_id}",
        json={"enabled": True},
    )
    if r.status_code != 200 or not r.json()["enabled"]:
        return f"toggle-on failed: {r.status_code}"

    result = turn(client, "My knee hurts after a fall.", session_id=session_id)
    tools = (event(result, "routing_decision") or {}).get("payload", {}).get("tools", [])
    if SPECIALIST_TOOL not in tools:
        return f"re-enabled specialist still hidden: {tools}"

    unknown = client.post(
        f"/v1/features/no_such_feature?session_id={session_id}", json={"enabled": True}
    )
    if unknown.status_code != 404:
        return f"unknown feature returned {unknown.status_code}"
    return None


def check_history(client: httpx.Client) -> str | None:
    message = f"History probe {time.time()}: tell me about sleep."
    result = turn(client, message)
    session_id = result["session_id"]

    r = client.get(f"/v1/sessions/{session_id}/messages")
    if r.status_code != 200:
        return f"history status={r.status_code}"
    messages = r.json()["messages"]
    roles = [m["role"] for m in messages]
    contents = [m["content"] for m in messages]
    if "user" not in roles or "assistant" not in roles:
        return f"incomplete roles: {roles}"
    if message not in contents:
        return "sent user message not persisted"
    if result.get("response") not in contents:
        return "assistant reply not persisted"

    missing = client.get("/v1/sessions/does-not-exist/messages")
    if missing.status_code != 404:
        return f"unknown session returned {missing.status_code}"
    return None


CHECKS = [
    ("general", lambda c, png: check_general(c)),
    ("symptom_triage", lambda c, png: check_symptom_triage(c)),
    ("emergency", lambda c, png: check_emergency(c)),
    ("image", lambda c, png: check_image_turn(c, png)),
    ("triage_endpoint", lambda c, png: check_triage_endpoint(c)),
    ("features_toggle", lambda c, png: check_features_toggle(c)),
    ("history", lambda c, png: check_history(c)),
]


def main() -> None:
    png = tiny_png_b64()
    failures: dict[str, list[str]] = {}
    timings: dict[str, float] = {}
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        health = client.get("/health").json()
        print(f"stack health: {json.dumps(health)}\n")
        for name, check in CHECKS:
            if ONLY is not None and name not in ONLY:
                continue
            failures[name] = []
            started = time.monotonic()
            for i in range(ROUNDS):
                try:
                    err = check(client, png)
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                if err:
                    failures[name].append(f"round {i + 1}: {err}")
                    print(f"[{name}] round {i + 1}/{ROUNDS} FAIL: {err}")
                else:
                    print(f"[{name}] round {i + 1}/{ROUNDS} ok")
            timings[name] = time.monotonic() - started

    print("\n=== SMOKE SUMMARY ===")
    total_fail = 0
    for name, _ in CHECKS:
        if ONLY is not None and name not in ONLY:
            continue
        bad = len(failures[name])
        total_fail += bad
        status = "PASS" if bad == 0 else f"FAIL ({bad}/{ROUNDS})"
        print(f"{name:>16}: {status}   [{timings[name]:.0f}s]")
        for line in failures[name]:
            print(f"                  - {line}")
    if total_fail:
        raise SystemExit(f"\nSMOKE FAILED: {total_fail} failing round(s)")
    print(f"\nSMOKE PASSED: {len(CHECKS)} types x {ROUNDS} rounds, all as expected.")


if __name__ == "__main__":
    main()
