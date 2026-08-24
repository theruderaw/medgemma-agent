"""Load prompt prose from app/prompts/templates/<name>.txt.

Prompt text lives outside Python so wording can be reviewed and edited
without touching module logic. Templates are read once per process and
cached; editing one requires a service restart.
"""

from functools import cache
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@cache
def load_prompt(name: str) -> str:
    """Return the raw text of ``templates/<name>.txt``."""
    path = _TEMPLATES_DIR / f"{name}.txt"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise KeyError(f"unknown prompt template '{name}'") from exc
