import datetime as dt

import pytest

from backend.agent.conditions import Conditions, merge, missing_fields

NOW = dt.datetime(2026, 11, 18, 11, 0)


def full(**kw):
    base = dict(origin="광주 첨단동", destination="서울 강남역", date=dt.date(2026, 11, 21), arrive_by="14:00")
    return Conditions(**{**base, **kw})


def test_defaults_not_invented():
    c = merge(None, {})
    assert c.budget is None and c.origin is None and c.arrive_by is None and c.buffer_min == 10


def test_merge_only_changed():
    c = merge(full(budget=60000), {"depart_after": "10:00"})
    assert c.depart_after == "10:00"
    assert c.date == dt.date(2026, 11, 21) and c.destination == "서울 강남역" and c.budget == 60000


def test_merge_none_does_not_erase():
    c = merge(full(budget=60000), {"budget": None})
    assert c.budget == 60000


def test_merge_clear():
    c = merge(full(budget=60000), {"_clear": ["budget"]})
    assert c.budget is None


def test_merge_ignores_unknown_keys():
    assert merge(full(), {"foo": 1}).origin == "광주 첨단동"


def test_missing_when_no_date():
    assert "date" in missing_fields(full(date=None), NOW)


def test_missing_when_no_time():
    assert "time" in missing_fields(full(arrive_by=None), NOW)


def test_complete_has_no_missing():
    assert missing_fields(full(), NOW) == []


def test_past_deadline_is_missing_condition():
    c = full(date=NOW.date(), arrive_by="09:00")
    assert missing_fields(c, NOW) == ["past_deadline"]


def test_past_date_is_missing():
    assert missing_fields(full(date=dt.date(2026, 11, 1)), NOW) == ["past_deadline"]


def test_bad_time_rejected():
    with pytest.raises(ValueError):
        full(arrive_by="2시")
