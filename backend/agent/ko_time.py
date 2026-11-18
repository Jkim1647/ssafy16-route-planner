"""한국어 날짜·시각 표현 보조 파서. 최소 모델(gpt-5-nano)이 비워 두거나 칸을 헷갈린 값만 보충한다.

사용자 문장에 실제로 있는 표현만 읽는다(지어내지 않음).
"""
import datetime as dt
import re

WEEKDAYS = "월화수목금토일"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_PM_WORDS = ("오후", "저녁", "밤")


def _parse_date(text: str, today: dt.date) -> dt.date | None:
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        return d if d >= today else dt.date(today.year + 1, d.month, d.day)
    for word, plus in (("모레", 2), ("내일", 1), ("오늘", 0)):
        if word in text:
            return today + dt.timedelta(days=plus)
    m = re.search(r"(다음\s*주|담주)?\s*([월화수목금토일])요일", text)
    if m:
        target = WEEKDAYS.index(m.group(2))
        if m.group(1):
            monday = today + dt.timedelta(days=7 - today.weekday())
            return monday + dt.timedelta(days=target)
        return today + dt.timedelta(days=(target - today.weekday()) % 7)
    return None


def _parse_time(text: str) -> tuple[str, str] | None:
    """(HH:MM, 'arrive'|'depart')"""
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        h, mi, tail = int(m.group(1)), int(m.group(2)), text[m.end():m.end() + 8]
    else:
        m = re.search(r"(오전|오후|저녁|밤|아침|새벽)?\s*(\d{1,2})시\s*(?:(\d{1,2})분|(반))?", text)
        if not m:
            return None
        h = int(m.group(2))
        mi = int(m.group(3)) if m.group(3) else (30 if m.group(4) else 0)
        if m.group(1) in _PM_WORDS and h < 12:
            h += 12
        tail = text[m.end():m.end() + 8]
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    kind = "depart" if re.match(r"\s*(이후|부터|에\s*출발|넘어서)", tail) else "arrive"
    return f"{h:02d}:{mi:02d}", kind


def parse_when(text: str, today: dt.date) -> dict:
    out = {}
    d = _parse_date(text, today)
    if d:
        out["date"] = d.isoformat()
    t = _parse_time(text)
    if t:
        out["arrive_by" if t[1] == "arrive" else "depart_after"] = t[0]
    return out


def fix_changes(changes: dict, text: str, today: dt.date) -> dict:
    """LLM 추출값을 정리: 날짜가 시각 칸에 들어간 경우 옮기고, 형식이 틀린 시각은 버리고, 빈 칸만 파서로 채운다."""
    c = dict(changes)
    for k in ("arrive_by", "depart_after"):
        v = c.get(k)
        if isinstance(v, str) and _DATE_RE.match(v):
            c.setdefault("date", v)
            c.pop(k)
        elif v is not None and not (isinstance(v, str) and _HHMM_RE.match(v)):
            c.pop(k)
    if c.get("date") and not _DATE_RE.match(str(c["date"])):
        c.pop("date")
    parsed = parse_when(text, today)
    if "date" not in c and "date" in parsed:
        c["date"] = parsed["date"]
    if "arrive_by" not in c and "depart_after" not in c:
        for k in ("arrive_by", "depart_after"):
            if k in parsed:
                c[k] = parsed[k]
    return c
