"""이름으로 찾는 Tool 레지스트리. Agent에는 이름·설명·입력 규격만 넘긴다."""
from backend.tools.base import Tool

_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    """Tool을 이름으로 등록하고 그대로 돌려준다(각 Tool 모듈이 import될 때 호출). 같은 이름이면 덮어쓴다."""
    _TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    """이름으로 Tool을 찾는다. 없으면 None(executor는 NOT_FOUND 실패로 처리)."""
    return _TOOLS.get(name)


def all_tools() -> dict[str, Tool]:
    """등록된 Tool 전체(이름 → Tool)의 얕은 사본."""
    return dict(_TOOLS)


def catalog(kind: str | None = None) -> list[dict]:
    """Agent에 넘길 Tool 목록(이름·설명·입력 규격). kind로 external/local만 고를 수 있다."""
    return [{"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in _TOOLS.values() if kind is None or t.kind == kind]
