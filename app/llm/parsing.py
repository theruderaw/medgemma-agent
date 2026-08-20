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