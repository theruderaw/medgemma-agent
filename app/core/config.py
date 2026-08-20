import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    model_name: str = os.getenv("MODEL_NAME", "qwen3:4b")
    specialist_model_name: str = os.getenv("SPECIALIST_MODEL_NAME", "medgemma1.5:4b")
    triage_model_name: str = os.getenv("TRIAGE_MODEL_NAME", "qwen3:0.6b")
    triage_enabled: bool = os.getenv("TRIAGE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    session_store_type: str = os.getenv("SESSION_STORE", "memory")
    database_url: str = os.getenv("DATABASE_URL", "postgresql:///medgemma-agent")
    audit_enabled: bool = os.getenv(
        "AUDIT_ENABLED",
        "true" if os.getenv("SESSION_STORE", "memory") == "postgres" else "false",
    ).lower() in ("1", "true", "yes", "on")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    session_timeout_seconds: float = float(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "40"))
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "16000"))
    processing_mode: str = os.getenv("PROCESSING_MODE", "sync")
    job_result_expire_seconds: int = int(os.getenv("JOB_RESULT_EXPIRE_SECONDS", "3600"))
    job_max_retries: int = int(os.getenv("JOB_MAX_RETRIES", "3"))
    job_concurrency: int = int(os.getenv("JOB_CONCURRENCY", "1"))


settings = Settings()