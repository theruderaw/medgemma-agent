# MedGemma Agent — Milestone 1

Talking Qwen, nothing else. A stateless FastAPI chat backend backed by Qwen3-4B
served via Ollama.

```
User → FastAPI POST /chat → Qwen3-4B (Ollama) → Response
```

## Prerequisites

- Ollama installed and running with `qwen3:4b` pulled:

  ```sh
  ollama pull qwen3:4b
  ```

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```sh
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Use

```sh
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I have a mild headache. Should I worry?"}'
```

Response:

```json
{"response": "..."}
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Send a message, get Qwen's response. Stateless. |
| `GET` | `/health` | Liveness check. |

`POST /chat` accepts:

```json
{
  "message": "string (required)",
  "temperature": 0.7
}
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `qwen3:4b` | Model served by Ollama. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server. Uses its OpenAI-compatible `/v1` API. |
| `LLM_TIMEOUT_SECONDS` | `120` | Timeout for model calls. |

## System boundary

The system prompt pins the assistant's role:

> I'm not a diagnostic tool; for anything urgent, contact emergency services.

## Test

```sh
.venv/bin/python -m pytest tests/ -q
```

## Scope

This milestone intentionally has no MedGemma, routing, session state, triage
logic, or prescription reading.