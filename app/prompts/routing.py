"""Router system prompt, rendered per turn from the actually-offered tools.

The prompt never names a specific addon: the tool bullet list is generated
from whatever the registry offers for the session, so adding, renaming, or
removing an addon needs no prompt edit.
"""

from string import Template

from .loader import load_prompt

_TEMPLATE = Template(load_prompt("routing"))

_NO_TOOLS_LINE = "- (no specialist tools are available this turn)"


def build_routing_prompt(tools: list[dict]) -> str:
    """Render the routing prompt with one bullet per offered tool.

    ``tools`` are the OpenAI-style dicts already built for the router call
    (``ToolSchema.as_dict`` output), reused so prompt and tool payload can
    never disagree.
    """
    bullets = "\n".join(
        f"- {tool['function']['name']}: {tool['function']['description']}"
        for tool in tools
    )
    return _TEMPLATE.substitute(tool_instructions=bullets or _NO_TOOLS_LINE)
