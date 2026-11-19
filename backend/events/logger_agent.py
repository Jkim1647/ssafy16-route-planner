"""로깅 서브 Agent(F3013). 이벤트를 받는 즉시 세션 단위로 발생 순서대로 저장한다. LLM을 쓰지 않는다."""
import logging

log = logging.getLogger(__name__)


class LoggerAgent:
    """EventBus 구독자(호출 가능 객체): 받은 이벤트를 EventRepo에 가공 없이 append한다. 저장 실패는 경고 로그만 남긴다."""
    def __init__(self, event_repo):
        self.repo = event_repo

    def __call__(self, event: dict) -> None:
        try:
            self.repo.append(event)  # 발생한 사실을 그대로 남긴다(요약·가공 없음)
        except Exception:
            log.warning("실행 로그 저장 실패(대화는 계속)", exc_info=True)
