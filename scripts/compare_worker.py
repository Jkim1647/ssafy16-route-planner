"""Worker가 실제로 개입하는 요청 한 건의 구조 비교(F3021 보강, 3일차 상호 점검).

태안군청 반경 20km 안에는 기차역이 없어 첫 find_stations가 NO_DATA다. Worker LLM이 켜져 있으면 반경을 넓혀 재시도하고,
꺼져 있으면 실패를 그대로 보고한다. compare_modes.run_one으로 세 조건을 실행해 원본 결과를 JSON으로 남긴다
(docs/비교결과.md는 덮어쓰지 않는다).
사용: python scripts/compare_worker.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compare_modes import CONDITIONS, run_one  # noqa: E402

REQUEST = ("태안 → 서울역", "토요일 오후 3시까지 충남 태안군청에서 서울역 가야 해")
OUT = ROOT / "docs" / "evidence" / "2026-11-20-worker-compare.json"

if __name__ == "__main__":
    rows = []
    for cname, mode, wl in CONDITIONS:
        r = run_one(mode, wl, REQUEST[1])
        rows.append({"request": REQUEST[0], "message": REQUEST[1], "condition": cname, **r})
        print(cname, json.dumps(r, ensure_ascii=False))
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT.relative_to(ROOT))
