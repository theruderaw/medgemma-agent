"""Routing-level selection: which enabled addon an attached image lands on."""

from app.chat.turn import select_image_addon


class _ImageAddon:
    accepts_images = True

    def __init__(self, name, hint=None):
        self.name = name
        if hint is not None:
            self.image_route_hint = hint


class _TextOnlyAddon:
    accepts_images = False

    def __init__(self, name):
        self.name = name


def test_hinted_addon_wins_over_first_capable():
    clinical = _ImageAddon("call_medical_specialist")
    reader = _ImageAddon(
        "read_prescription",
        lambda text: "prescription" in text.lower(),
    )
    # The reader is offered AFTER the clinical assessment (registration
    # order) but its hint claims the message.
    chosen = select_image_addon([clinical, reader], "read my prescription please")
    assert chosen is reader


def test_falls_back_to_first_capable_without_hint_match():
    clinical = _ImageAddon("call_medical_specialist")
    reader = _ImageAddon("read_prescription", lambda text: False)
    chosen = select_image_addon([clinical, reader], "what is this rash")
    assert chosen is clinical


def test_text_only_addons_are_never_selected():
    text_addon = _TextOnlyAddon("check_medication_interaction")
    assert select_image_addon([text_addon], "read this prescription") is None


def test_no_candidates_returns_none():
    assert select_image_addon([], "anything") is None
