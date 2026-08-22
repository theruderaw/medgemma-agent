"""Live-model smoke test against a running MedGemma Agent stack.

Usage:
    .venv/bin/python scripts/smoke_live.py [BASE_URL]

Assumes the full stack is up (`make up`) with real Ollama models pulled.
Fires three turns — general, symptom-related, emergency — and checks each
lands on its expected pipeline path. Exits non-zero on any mismatch.
"""

import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
POLL_TIMEOUT = 300.0


def wait_result(client: httpx.Client, job_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        r = client.get(f"/v1/jobs/{job_id}")
        r.raise_for_status()
        body = r.json()
        if body["status"] == "success":
            return body["result"]
        if body["status"] == "failure":
            raise SystemExit(f"job {job_id} failed: {body.get('error')}")
        time.sleep(2)
    raise SystemExit(f"job {job_id} timed out after {POLL_TIMEOUT}s")


def run(client: httpx.Client, name: str, message: str, **kwargs) -> dict:
    started = time.monotonic()
    r = client.post("/v1/chat", json={"message": message, **kwargs})
    print(f"\n=== {name} ===")
    print(f"message: {message!r}")
    if r.status_code == 200:
        result = r.json()
    elif r.status_code == 202:
        print(f"queued: job_id={r.json()['job_id']} session={r.json()['session_id']}")
        result = wait_result(client, r.json()["job_id"])
    else:
        raise SystemExit(f"{name}: unexpected status {r.status_code}: {r.text}")
    print(json.dumps({
        "path": result.get("path"),
        "urgency": result.get("urgency"),
        "events": [e["event_type"] for e in result.get("events", [])],
        "response": result.get("response"),
    }, indent=2))
    print(f"elapsed: {time.monotonic() - started:.1f}s")
    return result


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        general = run(client, "general", "What is the difference between a cold and the flu?")
        specialist = run(
            client,
            "symptom-related",
            "I've had a dull headache behind my right eye for two days, worse in bright light.",
            triage=True,
        )
        emergency = run(client, "emergency", "I am having crushing chest pain and cannot breathe")

    failures = []
    if general.get("path") != "qwen_direct":
        failures.append(f"general: expected qwen_direct, got {general.get('path')}")
    if specialist.get("path") != "medical_specialist":
        failures.append(f"symptom: expected medical_specialist, got {specialist.get('path')}")
    if emergency.get("path") != "emergency_override" or emergency.get("urgency") != "emergency":
        failures.append(f"emergency: got path={emergency.get('path')} urgency={emergency.get('urgency')}")

    if failures:
        print("\nSMOKE FAILED:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nSMOKE PASSED: all three paths behaved as expected.")


if __name__ == "__main__":
    main()
