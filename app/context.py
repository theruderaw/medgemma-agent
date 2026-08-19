def trim_context(
    messages: list[dict],
    *,
    max_context_messages: int,
    max_context_chars: int,
) -> list[dict]:
    """Return the context window to send to the model.

    Caps the message count (keeping user/assistant pairs intact) and then
    applies a back-to-front character budget so a single very long turn cannot
    blow up the context. At least one message is always kept.
    """
    window = messages[:]
    count = len(window)
    if count > max_context_messages:
        count = max_context_messages
        if count % 2 == 1:
            count -= 1
        window = window[-count:]
    total = sum(len(m.get("content", "")) for m in window)
    while len(window) > 1 and total > max_context_chars:
        window.pop(0)
        total = sum(len(m.get("content", "")) for m in window)
    while len(window) > 2 and window[0]["role"] != "user":
        window.pop(0)
    return window