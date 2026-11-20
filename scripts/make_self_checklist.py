"""공식 셀프 체크리스트 xlsx에 점검 결과를 채운다(표준 라이브러리만 — 셀 서식·드롭다운·집계 수식은 원본 그대로).

사용: python scripts/make_self_checklist.py <배포 xlsx> [출력 xlsx]
  - 결과(G)·증빙(H)·비고(I)와 작성자·점검자·점검 일시를 넣고, 집계 칸의 캐시 값을 맞춘 뒤 열 때 다시 계산하게 한다.
  - 같은 내용을 Markdown 표로 표준 출력에 낸다(docs/셀프체크리스트.md에 붙임).
"""
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from self_checklist_data import AUTHOR, CHECKED_AT, CHECKER, ITEMS  # noqa: E402

FIRST_ROW = 9  # 1번 항목의 행
SHEET = "xl/worksheets/sheet1.xml"


def put(xml: str, ref: str, text: str) -> str:
    """빈 셀 <c r="G9" s="3"/>(또는 값 있는 셀)을 서식(s)은 두고 인라인 문자열 셀로 바꾼다."""
    pat = re.compile(r'<c r="%s"( s="\d+")?(?: t="\w+")?\s*(?:/>|>.*?</c>)' % ref, re.S)
    m = pat.search(xml)
    if not m:
        raise SystemExit(f"셀 {ref}를 찾지 못했습니다")
    cell = f'<c r="{ref}"{m.group(1) or ""} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'
    return xml[:m.start()] + cell + xml[m.end():]


def put_number(xml: str, ref: str, n: int) -> str:
    """집계 수식 셀의 캐시 값(<v>)만 바꾼다 — 수식은 그대로."""
    return re.sub(r'(<c r="%s"[^>]*>\s*<f>.*?</f>\s*<v>)[^<]*(</v>)' % ref, rf"\g<1>{n}\g<2>", xml, flags=re.S)


def main(src: str, out: str) -> None:
    shutil.copyfile(src, out)
    zin = zipfile.ZipFile(src)
    sheet = zin.read(SHEET).decode("utf-8")
    sheet = put(sheet, "C3", "셀프")  # 점검 유형(드롭다운: 셀프·상호)
    sheet = put(sheet, "C4", AUTHOR)
    sheet = put(sheet, "C5", CHECKER)
    sheet = put(sheet, "C6", CHECKED_AT)
    counts = {"통과": 0, "실패": 0, "미확인": 0, "해당없음": 0}
    for n, result, evidence, note in ITEMS:
        row = FIRST_ROW + n - 1
        sheet = put(sheet, f"G{row}", result)
        sheet = put(sheet, f"H{row}", evidence)
        sheet = put(sheet, f"I{row}", note)
        counts[result] += 1
    for ref, key in (("F42", "통과"), ("F43", "실패"), ("F44", "미확인"), ("F45", "해당없음")):
        sheet = put_number(sheet, ref, counts[key])
    sheet = put_number(sheet, "F46", 32 - len(ITEMS))
    workbook = zin.read("xl/workbook.xml").decode("utf-8")
    workbook = re.sub(r"<calcPr([^>]*?)/>", r'<calcPr\1 fullCalcOnLoad="1"/>', workbook, count=1)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == SHEET:
                data = sheet.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                data = workbook.encode("utf-8")
            zout.writestr(item, data)
    print(f"| 번호 | 결과 | 증빙 | 비고 |\n|---|---|---|---|")
    for n, result, evidence, note in ITEMS:
        print(f"| {n} | {result} | {evidence} | {note} |")
    print(f"\n집계: " + " · ".join(f"{k} {v}" for k, v in counts.items()) + f" · 미기입 {32 - len(ITEMS)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "docs/셀프체크리스트.xlsx")
