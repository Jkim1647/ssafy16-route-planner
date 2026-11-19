"""README용 그림(docs/images/*.svg)을 만든다 — 시스템 구조도(아이콘 포함).

사용: python scripts/make_readme_images.py   (구조가 바뀌면 이 파일의 BOXES·ARROWS를 고치고 다시 실행)
그림은 외부 라이브러리 없이 SVG 문자열로 그린다. 아이콘은 직접 그린 단순 선 아이콘(24×24).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
FONT = "Pretendard, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"
ACCENT, INK, MUTED, LINE = "#1f5f4a", "#1d2421", "#5c6763", "#c9d3ce"

# 24×24 선 아이콘(stroke=currentColor)
ICONS = {
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "browser": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/><circle cx="6" cy="6.5" r=".6"/><circle cx="8.5" cy="6.5" r=".6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "api": '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>',
    "agent": '<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="17" r="2.2"/><circle cx="19" cy="17" r="2.2"/><circle cx="12" cy="12.5" r="2.2"/><path d="M12 7.2v3.1M10.2 13.8l-3.4 2M13.8 13.8l3.4 2"/>',
    "log": '<path d="M6 3h9l3 3v15H6z"/><path d="M15 3v3h3M9 10h6M9 13.5h6M9 17h4"/>',
    "scale": '<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-2.5 6h5zM19 7l-2.5 6h5z"/>',
    "tool": '<path d="M14.5 5.5a4 4 0 0 0 4.9 5.2l-8.7 8.7a2 2 0 0 1-2.8-2.8l8.7-8.7a4 4 0 0 0-2.1-2.4z"/>',
    "db": '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
    "chip": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M10 10h4v4h-4z"/>',
    "pin": '<path d="M12 21s-6.5-5.7-6.5-11a6.5 6.5 0 0 1 13 0c0 5.3-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    "train": '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 10h14M9 21l1.5-4M15 21l-1.5-4"/><circle cx="9" cy="13.5" r=".7"/><circle cx="15" cy="13.5" r=".7"/>',
    "bus": '<rect x="4" y="3" width="16" height="15" rx="2.5"/><path d="M4 11h16M7 21v-3M17 21v-3"/><circle cx="8" cy="14.5" r=".7"/><circle cx="16" cy="14.5" r=".7"/>',
    "weather": '<path d="M7 18h9.5a3.5 3.5 0 0 0 .5-7 5 5 0 0 0-9.6 1.2A3 3 0 0 0 7 18z"/><path d="M5 5l1 1M10 3v1.5M3 10h1.5"/>',
    "walk": '<circle cx="13" cy="4" r="1.8"/><path d="M10 21l2-6 2.5 2V21M9 11l2.5-3 3 1.5 2 3M11.5 8L10 14"/>',
    "calendar": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4M8 13.5l2 2 4-4"/>',
}


def icon(name: str, x: float, y: float, size: int = 26, color: str = ACCENT) -> str:
    s = size / 24
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(x, y, w, h, ico, title, sub="", fill="#fff", stroke=LINE, title_color=INK):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>',
           icon(ico, x + 14, y + (h - 26) / 2),
           f'<text x="{x + 50}" y="{y + (h / 2 - 4 if sub else h / 2 + 5)}" font-size="15" font-weight="700" fill="{title_color}">{esc(title)}</text>']
    if sub:
        out.append(f'<text x="{x + 50}" y="{y + h / 2 + 15}" font-size="12" fill="{MUTED}">{esc(sub)}</text>')
    return "\n".join(out)


def arrow(points, label="", dashed=False, lx=None, ly=None):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="5 5"' if dashed else ""
    out = [f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="1.6"{dash} marker-end="url(#arrow)"/>']
    if label:
        x = lx if lx is not None else (points[0][0] + points[-1][0]) / 2
        y = ly if ly is not None else (points[0][1] + points[-1][1]) / 2 - 6
        out.append(f'<text x="{x}" y="{y}" font-size="11.5" fill="{MUTED}" text-anchor="middle" '
                   f'paint-order="stroke" stroke="#fff" stroke-width="4">{esc(label)}</text>')
    return "\n".join(out)


def band(y, h, title, fill):
    return (f'<rect x="16" y="{y}" width="1248" height="{h}" rx="16" fill="{fill}"/>'
            f'<text x="34" y="{y + 24}" font-size="13" font-weight="700" fill="{ACCENT}">{esc(title)}</text>')


def architecture() -> str:
    W, H = 1280, 720
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         band(16, 124, "① 화면 · frontend/ (Vue 3 SPA, 빌드 없음)", "#eef5f1"),
         band(156, 300, "② 백엔드 · backend/ (FastAPI)", "#f3f5f9"),
         band(472, 232, "③ 외부 서비스 (백엔드에서만 호출 · 캐시·호출 한도 budget.py)", "#fbf6ec")]
    # ① 화면
    p.append(box(40, 52, 150, 70, "user", "사용자", "말하거나 골라서 묻기"))
    p.append(box(240, 52, 560, 70, "browser", "화면 (Vue 3 · Vue Router · Leaflet)",
                 "대화·질문 만들기·지도 · 내 장소 · 이동 계획 · 실행 로그 · 공유 링크"))
    p.append(box(850, 52, 390, 70, "pin", "지도 동선", "버스=도로 · 도보=보행로 · 노선별 색", fill="#fff"))
    p.append(arrow([(190, 87), (240, 87)]))
    # ② 백엔드
    p.append(box(40, 196, 200, 74, "shield", "로그인", "Google OAuth → JWT 쿠키"))
    p.append(box(290, 196, 230, 74, "api", "API 라우터", "chat · plans · places · logs"))
    p.append(box(570, 190, 320, 86, "agent", "메인 Agent (LangGraph)", "분석→계획→실행→판단→재계획→응답",
                 fill="#e7f1ec", stroke=ACCENT, title_color=ACCENT))
    p.append(box(960, 196, 280, 74, "log", "로깅 Agent", "이벤트 저장 · 이상 징후 판정"))
    p.append(box(470, 350, 220, 74, "scale", "판단 엔진 (코드)", "마감·예산·일정·파레토"))
    p.append(box(730, 350, 270, 74, "tool", "Tool 13종", "ok/fail 규약 · 레지스트리"))
    p.append(box(1040, 350, 200, 74, "db", "SQLite", "계획·장소·로그·사용자"))
    p.append(arrow([(400, 122), (400, 160), (140, 160), (140, 196)], "fetch (쿠키 포함)", lx=270, ly=154))
    p.append(arrow([(240, 233), (290, 233)]))
    p.append(arrow([(520, 233), (570, 233)]))
    p.append(arrow([(890, 233), (960, 233)], "이벤트", dashed=True, ly=222))
    p.append(arrow([(620, 276), (620, 350)], "후보 판정", lx=660, ly=318))
    p.append(arrow([(840, 276), (840, 350)], "작업 t1~t15", lx=884, ly=318))
    p.append(arrow([(1100, 270), (1100, 350)]))
    # ③ 외부
    ext = [("chip", "SSAFY GMS", "LLM · 요청당 ≤2회"), ("pin", "카카오", "장소 · 택시 · 도로"),
           ("train", "TAGO", "열차 · 고속버스"), ("bus", "ODsay", "대중교통 · 하루 30회"),
           ("weather", "날씨·돌발·행사", "기상청 · ITS · TourAPI"), ("walk", "OSM 보행 경로", "도보 동선(지도)"),
           ("calendar", "Google Calendar", "일정 조회 · 등록")]
    xs = [40 + i * 175 for i in range(len(ext))]
    for x, (ico, t, s) in zip(xs, ext):
        p.append(box(x, 600, 160, 74, ico, t, s))
    # LLM: Agent → (아래로 돌아) GMS
    p.append(arrow([(590, 276), (590, 300), (120, 300), (120, 600)], "조건 뽑기 · 답장", lx=300, ly=294))
    # Tool → 나머지 외부 서비스(버스 선)
    bus_y = 540
    p.append(f'<path d="M865,424 L865,{bus_y}" stroke="{MUTED}" stroke-width="1.6" fill="none"/>')
    p.append(f'<path d="M{xs[1] + 80},{bus_y} L{xs[-1] + 80},{bus_y}" stroke="{MUTED}" stroke-width="1.6" fill="none"/>')
    for x in xs[1:]:
        p.append(arrow([(x + 80, bus_y), (x + 80, 600)]))
    p.append(f'<text x="{xs[1] + 84}" y="{bus_y - 8}" font-size="11.5" fill="{MUTED}">Tool 호출 · 같은 입력은 캐시 재사용</text>')
    p.append("</svg>")
    return "\n".join(p)


# ---------------------------------------------------------------- ERD
# 테이블: (이름, 설명, x, y, [(키, 열, 타입, 메모)]) — backend/db/database.py 스키마의 주요 열
TABLES = [
    ("users", "사용자", 40, 70, [("PK", "id", "TEXT", "google:sub · local"), ("", "email", "TEXT", ""),
                                 ("", "name", "TEXT", ""), ("", "last_login", "TEXT", "")]),
    ("places", "내 장소", 40, 360, [("PK", "id", "INTEGER", ""), ("FK", "user_id", "TEXT", ""),
                                   ("", "label", "TEXT", "집·교육장(사용자별 고유)"), ("", "kind", "TEXT", "home·school·work·pin"),
                                   ("", "x, y", "REAL", "좌표")]),
    ("plans", "이동 계획", 440, 70, [("PK", "id", "INTEGER", ""), ("FK", "user_id", "TEXT", ""),
                                     ("", "date · leave_at · arrive_at", "TEXT", ""), ("", "legs_json", "TEXT", "구간·동선"),
                                     ("", "total_fare", "INTEGER", ""), ("FK", "source_run_id", "TEXT", "만든 실행"),
                                     ("", "calendar_event_id", "TEXT", ""), ("", "share_token", "TEXT", "읽기 전용 공유")]),
    ("local_calendar", "로컬 캘린더", 440, 400, [("PK", "id", "INTEGER", ""), ("FK", "user_id", "TEXT", ""),
                                               ("", "title · start · end", "TEXT", ""), ("FK", "plan_id", "INTEGER", "")]),
    ("runs", "실행(요청 1건)", 840, 70, [("PK", "run_id", "TEXT", ""), ("FK", "user_id", "TEXT", ""),
                                       ("", "session_id", "TEXT", "대화 세션"), ("", "status", "TEXT", ""),
                                       ("", "replan_count", "INTEGER", ""), ("", "llm_calls", "INTEGER", "")]),
    ("run_events", "실행 단계 이벤트", 840, 360, [("PK", "id", "INTEGER", ""), ("FK", "run_id", "TEXT", ""),
                                               ("", "seq", "INTEGER", "순서"), ("", "type", "TEXT", "tool_call·replan…"),
                                               ("", "payload_json", "TEXT", "")]),
    ("anomaly_reports", "이상 징후 판정", 1180, 360, [("PK", "run_id", "TEXT", ""), ("", "verdict", "TEXT", "ok·warn·불가"),
                                                   ("", "findings_json", "TEXT", ""), ("", "diagnosis", "TEXT", "LLM 원인 진단")]),
]
TW, HEAD, ROW = 300, 40, 24


def table_box(name, desc, x, y, rows, w=TW):
    h = HEAD + ROW * len(rows) + 8
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fff" stroke="{LINE}" stroke-width="1.4"/>',
           f'<path d="M{x},{y + 10} a10,10 0 0 1 10,-10 h{w - 20} a10,10 0 0 1 10,10 v{HEAD - 10} h-{w} z" fill="{ACCENT}"/>',
           f'<text x="{x + 14}" y="{y + 26}" font-size="15" font-weight="700" fill="#fff">{esc(name)}</text>',
           f'<text x="{x + w - 14}" y="{y + 26}" font-size="12" fill="#d9ece4" text-anchor="end">{esc(desc)}</text>']
    for i, (key, col, typ, note) in enumerate(rows):
        ry = y + HEAD + 18 + i * ROW
        color = "#b5651d" if key == "PK" else "#2f6fde" if key == "FK" else MUTED
        out.append(f'<text x="{x + 12}" y="{ry}" font-size="10.5" font-weight="700" fill="{color}">{key}</text>')
        out.append(f'<text x="{x + 40}" y="{ry}" font-size="13" fill="{INK}">{esc(col)}</text>')
        out.append(f'<text x="{x + w - 12}" y="{ry}" font-size="11" fill="{MUTED}" text-anchor="end">'
                   f'{esc(note + " · " if note else "")}{typ}</text>')
    return "\n".join(out), h


def rel(points, label):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    # 라벨은 가장 긴 선분 가운데에
    segs = list(zip(points, points[1:]))
    (ax, ay), (bx, by) = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
    mx, my = (ax + bx) / 2, (ay + by) / 2
    return (f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#many)"/>'
            f'<circle cx="{points[0][0]}" cy="{points[0][1]}" r="3.5" fill="{MUTED}"/>'
            f'<text x="{mx}" y="{my - 6}" font-size="11.5" fill="{MUTED}" text-anchor="middle" paint-order="stroke" '
            f'stroke="#fff" stroke-width="4">{esc(label)}</text>')


def erd() -> str:
    W, H = 1520, 600
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">',
         # N쪽 끝: 까마귀발(crow's foot)
         f'<defs><marker id="many" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">'
         f'<path d="M0,6 L11,6 M11,1 L4,6 L11,11" fill="none" stroke="{MUTED}" stroke-width="1.5"/></marker></defs>',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<text x="40" y="24" font-size="13" fill="{MUTED}">● 한쪽(1) — ⟨ 여러 쪽(N) · PK 기본키 · FK 참조키 · 모든 데이터 테이블은 user_id로 사용자별 분리</text>']
    boxes = {}
    for name, desc, x, y, rows in TABLES:
        s, h = table_box(name, desc, x, y, rows)
        p.append(s)
        boxes[name] = (x, y, h)
    ux, uy, uh = boxes["users"]
    px, py, ph = boxes["plans"]
    rx, ry, rh = boxes["runs"]
    # users 1:N places · plans · runs
    p.append(rel([(ux + 150, uy + uh), (ux + 150, boxes["places"][1])], "저장 1:N"))
    p.append(rel([(ux + TW, uy + 40), (px, uy + 40)], "소유 1:N"))
    p.append(rel([(ux + 120, uy), (ux + 120, 54), (rx + 150, 54), (rx + 150, ry)], "요청 1:N"))
    # runs 1:N plans(source_run_id), runs 1:N run_events, runs 1:1 anomaly
    p.append(rel([(rx, ry + 100), (px + TW, ry + 100)], "출처 1:N"))
    p.append(rel([(rx + 150, ry + rh), (rx + 150, boxes["run_events"][1])], "단계 1:N"))
    ax, ay, _ = boxes["anomaly_reports"]
    p.append(rel([(rx + TW, ry + 60), (ax + 150, ry + 60), (ax + 150, ay)], "판정 1:0..1"))
    # plans 1:N local_calendar(plan_id)
    p.append(rel([(px + 150, py + ph), (px + 150, boxes["local_calendar"][1])], "캘린더 등록"))
    p.append(f'<text x="1180" y="560" font-size="12" fill="{MUTED}">외부 API 캐시·호출 수는 별도 DB</text>'
             f'<text x="1180" y="578" font-size="12" fill="{MUTED}">(api_cache · api_quota, tools/budget.py)</text>')
    p.append("</svg>")
    return "\n".join(p)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("architecture.svg", architecture), ("erd.svg", erd)):
        (OUT / name).write_text(fn(), encoding="utf-8")
        print("wrote", OUT / name)
