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

    Emits content only after the opening tag and stops at the closing tag, so
    callers can stream tokens to the client without ever surfacing the wrapper
    markup. If the stream never contains the wrapper, content is emitted once
    the buffered prefix exceeds a threshold.
    """

    OPEN_TAG = "<response>"
    CLOSE_TAG = "</response>"
    BUFFER_LIMIT = 4096

    def __init__(self) -> None:
        self.buf = ""
        self.past_open = False
        self.done = False

    def feed(self, delta: str) -> str:
        if self.done:
            return ""
        self.buf += delta
        if not self.past_open:
            idx = self.buf.find(self.OPEN_TAG)
            if idx >= 0:
                self.past_open = True
                self.buf = self.buf[idx + len(self.OPEN_TAG):]
            elif len(self.buf) > self.BUFFER_LIMIT:
                self.past_open = True
        if not self.past_open:
            return ""
        cidx = self.buf.find(self.CLOSE_TAG)
        if cidx >= 0:
            out = self.buf[:cidx]
            self.buf = ""
            self.done = True
            return out
        out = self.buf
        self.buf = ""
        return out

    def finish(self) -> str:
        return "" if self.done else self.buf.strip()