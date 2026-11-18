"""테스트용 가짜 LLM: with_structured_output(schema).invoke()가 준비한 응답을 순서대로 돌려준다."""


class _Bound:
    def __init__(self, parent, schema):
        self.parent, self.schema = parent, schema

    def invoke(self, messages):
        self.parent.prompts.append(messages)
        if not self.parent.responses:
            raise AssertionError("FakeLLM 응답이 더 없습니다")
        r = self.parent.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeLLM:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.prompts = []

    def with_structured_output(self, schema):
        return _Bound(self, schema)
