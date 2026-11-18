"""규정 문서 색인(F3022). data/docs/의 .md·.txt·.pdf를 나눠 GMS 임베딩으로 Chroma에 저장한다.

사용: python scripts/build_index.py
문서 출처·수집일은 data/docs/SOURCES.md에 기록한다(색인 제외).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.settings import get_settings  # noqa: E402
from backend.tools.rag import build_index  # noqa: E402

if __name__ == "__main__":
    s = get_settings()
    n = build_index(str(ROOT / "data" / "docs"), s.CHROMA_DIR)
    print(f"색인 완료: 청크 {n}개 → {s.CHROMA_DIR}")
