import hashlib

import pytest

from backend.tools import rag
from backend.tools.rag import build_index, search_terms


def fake_embed(texts):
    """키워드 기반 결정적 임베딩(네트워크 없음): 단어 해시를 64차원에 누적."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in t.split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        out.append(v)
    return out


@pytest.fixture
def docs(tmp_path, monkeypatch):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "korail.md").write_text("# 여객운송약관\n\n출발 전 반환 시 위약금은 출발 1시간 전까지 운임의 5퍼센트이다. "
                                 "출발 시각 이후 20분까지는 15퍼센트이다.", encoding="utf-8")
    (d / "weather.md").write_text("# 호우 행동요령\n\n호우 특보 시 지하차도 이용을 피한다.", encoding="utf-8")
    (d / "SOURCES.md").write_text("출처 목록(색인 제외)", encoding="utf-8")
    monkeypatch.setattr(rag, "get_embedder", lambda: fake_embed)
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    return d


def test_no_index_code(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(rag, "get_embedder", lambda: fake_embed)
    assert search_terms("위약금")["error"]["code"] == "NO_INDEX"


def test_build_and_search_returns_sources(docs, tmp_path):
    n = build_index(str(docs), str(tmp_path / "chroma"), fake_embed)
    assert n >= 2
    r = search_terms("출발 전 반환 시 위약금은", k=2)
    assert r["ok"]
    top = r["data"]["chunks"][0]
    assert "위약금" in top["text"] and top["source"] == "korail.md" and top["title"] == "여객운송약관"


def test_sources_file_not_indexed(docs, tmp_path):
    build_index(str(docs), str(tmp_path / "chroma"), fake_embed)
    r = search_terms("출처 목록", k=5)
    assert all(c["source"] != "SOURCES.md" for c in r["data"]["chunks"])


def test_empty_question():
    assert search_terms("")["error"]["code"] == "BAD_ARGUMENT"


def test_rebuild_is_idempotent(docs, tmp_path):
    a = build_index(str(docs), str(tmp_path / "chroma"), fake_embed)
    b = build_index(str(docs), str(tmp_path / "chroma"), fake_embed)
    assert a == b
    assert len(search_terms("위약금", k=10)["data"]["chunks"]) == a


def test_search_without_gms_key_is_invalid_key(docs, tmp_path, monkeypatch):
    build_index(str(docs), str(tmp_path / "chroma"), fake_embed)
    monkeypatch.setenv("GMS_API_KEY", "")
    assert search_terms("위약금")["error"]["code"] == "INVALID_KEY"
