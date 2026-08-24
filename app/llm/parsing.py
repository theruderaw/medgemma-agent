import re

# A deliberation preamble ends with a labeled answer marker, e.g.
#   "...should respond directly without triggering the specialist tool.\nResponse: ..."
# Everything up to and including the marker is model reasoning that must never
# reach the user. Matched case-insensitively, optionally bolded, as its own
# line start so ordinary prose containing these words mid-sentence survives.
_ANSWER_MARKER = re.compile(
    r"(?im)^(?:\*\*)?\s*(?:final\s+)?(?:response|answer|reply)\s*(?:\*\*)?\s*:\s*"
)

# A standalone routing-decision announcement, e.g.
#   "No tool call needed."
# Everything up to and including such a line is router meta-reasoning that
# must never reach the user. Matched as its own line so ordinary prose
# mentioning tools mid-sentence survives.
_TOOL_NARRATION_MARKER = re.compile(
    r"(?im)^(?:\*\*)?\s*no tool calls?\s+(?:are\s+|is\s+)?(?:needed|required)[.!\s]*(?:\*\*)?\s*$"
)


def extract_answer(content: str) -> str:
    """Extract the model's actual reply from a Qwen3 response.

    Qwen3 sometimes precedes its real answer with a reasoning preamble and
    wraps the reply in `<response>...</response>` tags. When the tags are
    present the inner text is returned.

    Without tags, two leak classes are stripped: a deliberation preamble
    terminated by an explicit ``Response:``/``Answer:``/``Reply:`` marker,
    and a preamble ending in a standalone "no tool call needed" decision
    announcement — this is how the function-calling router's meta-reasoning
    leaks into user-visible replies when it answers general questions inline.
    Ordinary replies without such markers are returned unchanged (trimmed).
    """
    text = content.strip()
    match = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Strip up to the last leak-class marker that has content after it, so
    # preambles ending in either class are removed wherever they appear.
    markers = [*_ANSWER_MARKER.finditer(text), *_TOOL_NARRATION_MARKER.finditer(text)]
    for marker in sorted(markers, key=lambda m: m.end(), reverse=True):
        remainder = text[marker.end():].strip()
        if remainder:
            return remainder

    # The whole reply is a bare decision announcement ("No tool call
    # needed.") with no actual content anywhere — return nothing rather than
    # let meta-reasoning reach the user.
    if _TOOL_NARRATION_MARKER.search(text):
        return ""

    return text


class StreamExtractor:
    """Strips the Qwen3 ``<response>...</response>`` wrapper from a live stream.

    With ``enable_thinking: false`` the wrapper is consistent: when present it
    leads the content. The extractor holds back only the first few characters to
    detect a leading ``<response>`` tag, then streams every delta through
    untouched and stops at the closing tag — so clients get real incremental
    tokens and never see the wrapper markup.

    A small tail (``len(CLOSE_TAG) - 1`` characters) is held back between
    calls so a closing tag split across two deltas is still detected; the
    tail is flushed by :meth:`finish` when the stream ends without one.

    Deliberation preambles WITHOUT the wrapper cannot be stripped live without
    buffering the whole stream; they are removed from the persisted/final
    response by :func:`extract_answer`, and the UI replaces streamed text with
    the final response on ``turn_completed`` — so any transient leak
    self-corrects when the turn finishes.
    """

    OPEN_TAG = "<response>"
    CLOSE_TAG = "</response>"

    def __init__(self) -> None:
        self._checked_open = False  # one-time: is the stream <response>-wrapped?
        self._tail = ""  # held back so a split closing tag stays detectable
        self.done = False

    def feed(self, delta: str) -> str:
        """Consume one stream delta, returning only user-visible text.

        Holds back a partial opening tag until it can be ruled out, and a
        partial closing tag until the next call resolves it; once the closing
        tag is seen, everything further is suppressed.
        """
        if self.done:
            return ""
        text = self._tail + delta
        self._tail = ""

        if not self._checked_open:
            if len(text) < len(self.OPEN_TAG):
                if self.OPEN_TAG.startswith(text):
                    # Could still grow into the opening tag — keep holding.
                    self._tail = text
                    return ""
                self._checked_open = True
            else:
                self._checked_open = True
                if text.startswith(self.OPEN_TAG):
                    text = text[len(self.OPEN_TAG) :]

        cidx = text.find(self.CLOSE_TAG)
        if cidx >= 0:
            self.done = True
            return text[:cidx]

        hold = min(len(self.CLOSE_TAG) - 1, len(text))
        self._tail = text[len(text) - hold :]
        return text[: len(text) - hold]

    def finish(self) -> str:
        """Flush any held-back text at end of stream if the wrapper never closed.

        Returned verbatim: the tail is ordinary body text whenever the
        open-tag probe resolved, so stripping here would corrupt streamed
        wording (e.g. eat a sentence's separating space).
        """
        tail, self._tail = self._tail, ""
        return "" if self.done else tail
