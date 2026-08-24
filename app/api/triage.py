import httpx
from fastapi import APIRouter, HTTPException
from uuid import uuid4

from ..audit import audit, trim_llm_payload
from ..chat.triage import run_triage
from ..core.config import settings
from ..core.images import persist_image
from ..core.logging import get_logger
from ..domain.triage import TriageResult, Urgency
from ..safety import detect_emergency
from .images import image_meta, prepare_image
from .schemas import TriageRequest, TriageResponse

logger = get_logger("app.api.triage")

router = APIRouter(tags=["triage"])


@router.post("/v1/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    """Stateless structured triage over text plus an optional image.

    Runs the deterministic red-flag floor first (a match short-circuits to a
    structured emergency result with no model calls), then classifies the
    message text with the text-only MedGemma triage model. Images are stored
    and audited but never influence urgency. Never mutates session state.
    """
    turn_id = uuid4().hex
    image = prepare_image(request.image_b64, request.image_mime)
    image_meta_ = None
    if image is not None:
        persist_image(image, turn_id)
        image_meta_ = image_meta(image)
        await audit.append(
            module="image",
            event_type="image_received",
            payload={
                "path": image.path,
                "sha256": image.sha256,
                "mime": image.mime,
                "size_bytes": image.size_bytes,
            },
            turn_id=turn_id,
        )

    category = detect_emergency(request.message)
    if category is not None:
        result = TriageResult(
            urgency=Urgency.EMERGENCY,
            red_flags=[category],
            reasoning="Hardcoded red-flag rule matched; no model evaluation performed.",
        )
        await audit.append(
            module="safety",
            event_type="safety_override",
            payload={"category": category, "message": request.message},
            turn_id=turn_id,
        )
        logger.info("triage.completed", source="rules", urgency=result.urgency.value)
        return TriageResponse.from_result(result, model="hardcoded_rules", source="rules", image=image_meta_)

    try:
        result = await run_triage(request.message)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Model server unreachable: {exc}")

    model = settings.triage_model_name
    source = "text"
    await audit.append(
        module="triage",
        event_type="triage_result",
        payload=trim_llm_payload(
            {**result.to_dict(), "model": model, "source": source},
            settings.audit_llm_cap_chars,
        ),
        turn_id=turn_id,
    )
    logger.info("triage.completed", source=source, urgency=result.urgency.value)
    return TriageResponse.from_result(result, model=model, source=source, image=image_meta_)
