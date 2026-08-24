"""Tests for the prescription transcription domain parser.

The wire contract is strict: {"medications": {name: {five nullable fields}}}.
Everything safety-relevant (uncertainty, limitations, placeholder rejection)
is derived here — these tests pin that behavior.
"""

import pytest

from app.domain.prescription import parse_prescription_result


def test_contract_shape_round_trip():
    raw = (
        '{"medications": {"Amoxicillin": {"strength": "500 mg", "dose": "1 capsule", '
        '"frequency": "three times daily", "duration": "7 days", '
        '"instructions": "Take with food"}}}'
    )
    result = parse_prescription_result(raw)
    assert result.to_dict() == {
        "medications": {
            "Amoxicillin": {
                "strength": "500 mg",
                "dose": "1 capsule",
                "frequency": "three times daily",
                "duration": "7 days",
                "instructions": "Take with food",
            }
        },
        # Fully legible transcription -> nothing to ask about.
        "clarifications": [],
    }
    assert result.uncertain is False
    assert result.limitations == []
    assert result.drug_names == ["Amoxicillin"]


def test_unreadable_fields_become_targeted_clarifications():
    raw = (
        '{"medications": {"Ibuprofen": {"strength": "400 mg", "dose": "1 tablet", '
        '"frequency": "every 6-8 hours as needed", "duration": null, '
        '"instructions": "Take after meals"}}}'
    )
    result = parse_prescription_result(raw)
    asks = result.to_dict()["clarifications"]
    assert len(asks) == 1
    assert "Ibuprofen" in asks[0]
    assert "duration" in asks[0]


def test_empty_map_asks_for_a_better_photo():
    result = parse_prescription_result('{"medications": {}}')
    asks = result.clarifications
    assert len(asks) == 1
    assert "sharper" in asks[0] or "type the medicines" in asks[0]


def test_code_fences_and_prose_tolerated():
    raw = '```json\n{"medications": {"Aspirin": {"strength": "81 mg", "dose": null, "frequency": "daily", "duration": null, "instructions": null}}}\n```'
    result = parse_prescription_result(raw)
    assert result.medications["Aspirin"]["strength"] == "81 mg"
    assert result.uncertain is False


def test_null_fields_are_preserved_not_guessed():
    raw = '{"medications": {"Ibuprofen": {"strength": "400 mg", "dose": "1 tablet", "frequency": "every 6-8 hours as needed", "duration": null, "instructions": "Take after meals"}}}'
    result = parse_prescription_result(raw)
    assert result.medications["Ibuprofen"]["duration"] is None
    assert result.uncertain is False


def test_empty_map_is_explicitly_uncertain():
    result = parse_prescription_result('{"medications": {}}')
    assert result.medications == {}
    assert result.uncertain is True
    assert any("No medication entries" in line for line in result.limitations)


def test_missing_medications_key_is_uncertain():
    result = parse_prescription_result('{"something_else": {}}')
    assert result.medications == {}
    assert result.uncertain is True
    assert any("no medications section" in line for line in result.limitations)


def test_placeholder_names_dropped_with_limitation():
    raw = (
        '{"medications": {"unreadable": {"strength": null, "dose": null, '
        '"frequency": null, "duration": null, "instructions": null}, '
        '"Paracetamol": {"strength": "500mg", "dose": "1 tab", "frequency": "tds", '
        '"duration": null, "instructions": null}}}'
    )
    result = parse_prescription_result(raw)
    assert list(result.medications) == ["Paracetamol"]
    assert result.uncertain is True
    assert any("omitted" in line for line in result.limitations)


def test_identity_keys_are_dropped():
    raw = (
        '{"patient": "John Doe", "prescriber": "Dr. Smith", '
        '"medications": {"Aspirin": {"strength": "100 mg", "dose": "1 tab", '
        '"frequency": "daily", "duration": null, "instructions": null}}}'
    )
    result = parse_prescription_result(raw)
    assert result.raw  # raw kept for audit only
    assert list(result.medications) == ["Aspirin"]


def test_list_shaped_output_normalized_into_map():
    raw = (
        '{"medications": ['
        '{"name": "Aspirin", "strength": "100 mg", "dose": "1 tab", '
        '"frequency": "daily", "duration": null, "instructions": null}]}'
    )
    result = parse_prescription_result(raw)
    assert result.medications["Aspirin"]["strength"] == "100 mg"
    assert result.uncertain is False


def test_numeric_fields_coerced_to_strings():
    raw = '{"medications": {"Aspirin": {"strength": 100, "dose": 1, "frequency": "daily", "duration": null, "instructions": null}}}'
    result = parse_prescription_result(raw)
    assert result.medications["Aspirin"]["strength"] == "100"
    assert result.medications["Aspirin"]["dose"] == "1"


@pytest.mark.parametrize(
    "raw",
    ["not json at all", "", '{"medications":'],
)
def test_invalid_output_raises_valueerror(raw):
    with pytest.raises(ValueError):
        parse_prescription_result(raw)
