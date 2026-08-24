from ..domain.triage import TriageResult, parse_triage_result
from ..llm import llm


async def run_triage(message: str) -> TriageResult:
    """Run the triage classification and parse it into a typed result."""
    raw = await llm.triage(message)
    return parse_triage_result(raw)
