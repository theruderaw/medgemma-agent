import os


class Settings:
    model_name: str = os.getenv("MODEL_NAME", "qwen3:4b")
    specialist_model_name: str = os.getenv("SPECIALIST_MODEL_NAME", "medgemma1.5:4b")
    triage_model_name: str = os.getenv("TRIAGE_MODEL_NAME", "qwen3:0.6b")
    triage_enabled: bool = os.getenv("TRIAGE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    session_store_type: str = os.getenv("SESSION_STORE", "memory")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    session_timeout_seconds: float = float(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "40"))
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "16000"))


settings = Settings()