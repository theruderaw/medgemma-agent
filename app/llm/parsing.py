import re


def extract_answer(content: str) -> str:
    """Extract the model's actual reply from a Qwen3 response.

    Qwen3 sometimes precedes its real answer with a reasoning preamble and
    wraps the reply in `<response>...</response>` tags. When the tags are
    present the inner text is returned; otherwise the content is returned
    unchanged (trimmed).
    """
    text = content.strip()
    match = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


class StreamExtractor:
    """Strips the Qwen3 ``<response>...</response>`` wrapper from a live stream.

    With ``enable_thinking: false`` the wrapper is consistent: when present it
    leads the content. The extractor holds back only the first few characters to
    detect a leading ``<response>`` tag, then streams everything eagerly and
    stops at the closing tag — so clients get real incremental tokens and never
    see the wrapper markup.
    """

    OPEN_TAG = "<response>"
    CLOSE_TAG = "</response>"

    def __init__(self) -> None:
        self.buf = ""
        self.done = False

    def feed(self, delta: str) -> str:
        if self.done:
            return ""
        self.buf += delta
        if len(self.buf) < len(self.OPEN_TAG):
            return ""
        if self.buf.startswith(self.OPEN_TAG):
            self.buf = self.buf[len(self.OPEN_TAG):]
        out = self.buf
        self.buf = ""
        cidx = out.find(self.CLOSE_TAG)
        if cidx >= 0:
            out = out[:cidx]
            self.done = True
        return out

    def finish(self) -> str:
        return "" if self.done else self.buf.strip()