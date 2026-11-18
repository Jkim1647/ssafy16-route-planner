"""운송약관·행동요령 RAG 검색 Tool(F3022, 로컬 서버 API 툴). 시간표 API로 알 수 없는 규정을 근거 문서와 함께 답한다.

색인: python scripts/build_index.py  (data/docs/*.md|*.txt|*.pdf → Chroma 'terms' 컬렉션)
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Callable

from backend.tools.base import BAD_ARGUMENT, NO_INDEX, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.registry import register

COLLECTION = "terms"
SKIP = {"SOURCES.md", "README.md"}
Embedder = Callable[[list[str]], list[list[float]]]


def get_embedder() -> Embedder:
    from langchain_openai import OpenAIEmbeddings

    from backend.settings import get_settings
    s = get_settings()
    emb = OpenAIEmbeddings(model=s.EMBEDDING_MODEL, base_url=s.GMS_BASE_URL, api_key=s.GMS_API_KEY)
    return emb.embed_documents


def _chroma_dir() -> str:
    from backend.settings import get_settings
    return get_settings().CHROMA_DIR


def _load(path: Path) -> list[tuple[str, int | None]]:
    """(텍스트, 페이지) 목록."""
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # 선택 의존성: PDF 원문을 넣을 때만 필요
        return [(p.extract_text() or "", i + 1) for i, p in enumerate(PdfReader(str(path)).pages)]
    return [(path.read_text(encoding="utf-8"), None)]


def _title(path: Path, text: str) -> str:
    m = re.search(r"^#\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else path.stem


def build_index(docs_dir: str, chroma_dir: str, embedder: Embedder | None = None) -> int:
    import chromadb
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    embed = embedder or get_embedder()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    ids, texts, metas = [], [], []
    for path in sorted(Path(docs_dir).iterdir()):
        if path.name in SKIP or path.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        pages = _load(path)
        title = _title(path, pages[0][0] if pages else "")
        for text, page in pages:
            for i, chunk in enumerate(splitter.split_text(text)):
                ids.append(hashlib.md5(f"{path.name}:{page}:{i}".encode()).hexdigest())
                texts.append(chunk)
                metas.append({"source": path.name, "title": title, "page": page or 0})
    client = chromadb.PersistentClient(path=chroma_dir)
    try:
        client.delete_collection(COLLECTION)  # 다시 만들면 중복 없이 처음부터
    except Exception:
        pass
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)
    if texts:
        col.add(ids=ids, documents=texts, metadatas=metas, embeddings=embed(texts))
    return len(texts)


def search_terms(question: str, k: int = 4) -> dict:
    if not question or not question.strip():
        return fail(BAD_ARGUMENT, "question은 필수입니다.")
    path = _chroma_dir()
    if not os.path.isdir(path):
        return fail(NO_INDEX, "아직 규정 문서를 색인하지 않았습니다.")
    try:
        import chromadb
        col = chromadb.PersistentClient(path=path).get_collection(COLLECTION, embedding_function=None)
        if col.count() == 0:
            return fail(NO_INDEX, "아직 규정 문서를 색인하지 않았습니다.")
        res = col.query(query_embeddings=get_embedder()([question]), n_results=min(k, col.count()))
    except ValueError:
        return fail(NO_INDEX, "아직 규정 문서를 색인하지 않았습니다.")
    except Exception:
        return fail(UPSTREAM_ERROR, "규정 검색 중 오류가 났습니다.")
    chunks = [{"text": doc, "source": m["source"], "title": m["title"], "page": m["page"] or None,
               "distance": round(dist, 4)}
              for doc, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]
    return ok({"chunks": chunks})


register(Tool(
    name="search_terms",
    description="열차·고속버스 환불 위약금, 지연 보상, 기상특보 행동요령처럼 시간표 API로 확인할 수 없는 규정을 물을 때 부른다. "
                "근거 문단과 출처를 돌려준다.",
    parameters={"type": "object", "properties": {"question": {"type": "string"}, "k": {"type": "integer"}},
                "required": ["question"]},
    func=search_terms, kind="local"))
