"""이름으로 찾는 Tool 레지스트리. Agent에는 이름·설명·입력 규격만 넘긴다."""
from backend.tools.base import Tool

_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def all_tools() -> dict[str, Tool]:
    return dict(_TOOLS)


def catalog(kind: str | None = None) -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in _TOOLS.values() if kind is None or t.kind == kind]
