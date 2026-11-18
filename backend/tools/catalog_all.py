"""모든 Tool 모듈을 불러와 레지스트리에 등록한다(import 부수효과로 register 호출)."""
from backend.tools import (calendar_tools, its_events, kakao_local, kakao_mobility, kma_weather, odsay, rag,  # noqa: F401
                           stations, tago_bus, tago_train)
