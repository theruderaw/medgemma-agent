import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AUDIT_FILE_DEFAULT = str(Path(__file__).resolve().parent.parent / "logs" / "audit.jsonl")


class Settings:
    model_name: str = os.getenv("MODEL_NAME", "qwen3:4b")
    specialist_model_name: str = os.getenv("SPECIALIST_MODEL_NAME", "medgemma1.5:4b")
    triage_model_name: str = os.getenv("TRIAGE_MODEL_NAME", "medgemma1.5:4b")
    guard_model_name: str = os.getenv("GUARD_MODEL_NAME", "qwen3:0.6b")
    guard_min_chars: int = int(os.getenv("GUARD_MIN_CHARS", "200"))
    image_max_bytes: int = int(os.getenv("IMAGE_MAX_BYTES", str(5 * 1024 * 1024)))
    image_allowed_mime: tuple[str, ...] = tuple(
        m.strip()
        for m in os.getenv(
            "IMAGE_ALLOWED_MIME",
            "image/jpeg,image/png,image/webp,application/pdf",
        ).split(",")
        if m.strip()
    )
    image_upload_dir: str = os.getenv(
        "IMAGE_UPLOAD_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "uploads"),
    )
    image_max_dimension_px: int = int(os.getenv("IMAGE_MAX_DIMENSION_PX", "1024"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.5"))
    database_url: str = os.getenv("DATABASE_URL", "postgresql:///medgemma-agent")
    audit_file: str = os.getenv("AUDIT_FILE", AUDIT_FILE_DEFAULT)
    audit_llm_cap_chars: int = int(os.getenv("AUDIT_LLM_CAP_CHARS", "1000"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "40"))
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "16000"))
    job_result_expire_seconds: int = int(os.getenv("JOB_RESULT_EXPIRE_SECONDS", "3600"))
    job_max_retries: int = int(os.getenv("JOB_MAX_RETRIES", "3"))
    job_concurrency: int = int(os.getenv("JOB_CONCURRENCY", "1"))


settings = Settings()