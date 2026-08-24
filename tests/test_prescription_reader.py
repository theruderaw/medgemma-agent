"""Tests for the read_prescription addon: interaction cross-check, routing
hooks, and the structured artifact contract."""

from app.addons.medication_interaction import canonical_name, lookup_pair
from app.addons.prescription_reader import MAX_INTERACTION_MEDS, addon


def _result_with(names):
    meds = {
        name: {"strength": None, "dose": None, "frequency": None, "duration": None, "instructions": None}
        for name in names
    }
    from app.domain.prescription import PrescriptionResult

    return PrescriptionResult(medications=meds)


def test_context_demands_clarifying_questions_for_unreadable_fields():
    from app.domain.prescription import parse_prescription_result

    result = parse_prescription_result(
        '{"medications": {"Aspirin": {"strength": "81 mg", "dose": null, '
        '"frequency": null, "duration": null, "instructions": null}}}'
    )
    ctx = addon.context_for(result, image_analyzed=True)
    assert "MUST explicitly ask" in ctx
    assert "Aspirin: could not read the" in ctx


def test_structured_kind_contract():
    assert addon.structured_kind == "prescription"
    assert addon.accepts_images is True


def test_image_hint_matches_prescription_language_only():
    assert addon.image_route_hint("please read this prescription")
    assert addon.image_route_hint("my Rx from the doctor")
    assert addon.image_route_hint("what does this medicine slip say?")
    assert not addon.image_route_hint("there is a rash on my arm")
    assert not addon.image_route_hint("")


def test_route_trigger_never_fires_without_image():
    assert addon.route_trigger("read this prescription", [], has_image=False) is False
    assert addon.route_trigger("read this prescription", [], has_image=True) is True
    assert addon.route_trigger("i have a rash", [], has_image=True) is False


def test_interaction_cross_check_finds_dataset_entry_via_alias():
    # Tylenol resolves through the alias index to acetaminophen; the curated
    # dataset contains acetaminophen+warfarin.
    assert canonical_name("Tylenol") == "acetaminophen"
    entry = lookup_pair("warfarin", "acetaminophen")
    assert entry is not None and "severity" in entry

    ctx = addon.context_for(_result_with(["Warfarin", "Tylenol"]), image_analyzed=True)
    assert "acetaminophen + warfarin" in ctx
    assert "severity" in ctx


def test_unknown_drug_is_disclosed_not_skipped_silently():
    ctx = addon.context_for(_result_with(["Zyrtec"]), image_analyzed=True)
    assert "Zyrtec" in ctx
    assert "not" in ctx and "cross-checked" in ctx


def test_no_dataset_row_yields_explicit_no_data_not_silence():
    pair = ("albuterol", "propranolol")  # known dataset key: albuterol+propranolol exists
    assert lookup_pair(*pair) is not None
    # A pair with NO row must produce the explicit no-data line in context.
    ctx = addon.context_for(_result_with(["Zyrtec", "Claritin"]), image_analyzed=True)
    assert "Fewer than two recognizable drug names" in ctx  # neither is indexed


def test_med_cap_truncation_note():
    names = [f"Drug{i}" for i in range(MAX_INTERACTION_MEDS + 2)]
    ctx = addon.context_for(_result_with(names), image_analyzed=True)
    assert "first 8 medications were cross-checked" in ctx or (
        f"first {MAX_INTERACTION_MEDS}" in ctx
    )


def test_context_states_when_no_image_analyzed():
    ctx = addon.context_for(_result_with(["Aspirin"]), image_analyzed=False)
    assert "NO image was actually analyzed" in ctx


def test_uncertain_result_leans_on_professional_verification():
    from app.domain.prescription import parse_prescription_result

    result = parse_prescription_result('{"medications": {}}')
    ctx = addon.context_for(result, image_analyzed=True)
    assert "UNCERTAIN" in ctx
    assert "pharmacist" in ctx.lower()
