from ..core.config import settings
from ..llm import llm
from ..triage import TriageResult, parse_triage_result


def triage_model_for(image: bool) -> str:
    """Model that run_triage will use for a text-only vs image turn."""
    return settings.vision_triage_model_name if image else settings.triage_model_name


async def run_triage(message: str, *, image_b64: str | None = None) -> TriageResult:
    """Run the extended triage classification and parse it into a typed result.

    Text-only turns go to the tiny triage model; image turns are dispatched to
    the multimodal vision tier. Both emit the same extended JSON schema.
    """
    raw = await llm.triage(message, image_b64=image_b64)
    return parse_triage_result(raw)
