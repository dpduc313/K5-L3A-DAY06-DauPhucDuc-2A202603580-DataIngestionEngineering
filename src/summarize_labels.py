"""Tổng hợp nhãn thủ công trong results/labels/ thành bảng cho báo cáo.

    python -m src.summarize_labels

Đọc coherence.csv, metadata_audit.csv, grounding.csv do người chấm điền; dòng chưa có
điểm được báo là "chưa chấm" (không tính vào trung bình). Ghi results/labels_summary.md.
"""

import csv
from collections import defaultdict

from src import lab_config as C


def rows(name: str) -> list[dict]:
    with (C.LABELS / name).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    lines = [
        "# Tổng hợp nhãn",
        "",
        "Người chấm: metadata do tác giả chấm tay; 3 dòng được sửa theo bước đối chiếu tự "
        "động (text chunk có nằm trên trang ghi trong metadata, tiêu đề xuất hiện trong chunk "
        "có nằm trong `sections`), tác giả đồng ý. Coherence và grounding do Claude (LLM, qua "
        "Claude Code) chấm nháp theo thang và quy tắc ghi trong báo cáo, có lý do từng dòng; "
        "tác giả duyệt lại từng dòng, giữ nguyên điểm và viết lại lý do 3 dòng coherence "
        "(pos04 A, pos08 A, pos10 B/C).",
        "",
    ]

    coherence = defaultdict(list)
    missing = 0
    for r in rows("coherence.csv"):
        if r["score_0_1_2"].strip():
            coherence[r["strategy"]].append(int(r["score_0_1_2"]))
        else:
            missing += 1
    lines += ["## Coherence (10 vị trí, thang 0-2)", "", "| Strategy | n | Trung bình /2 | 0/1/2 |",
              "|---|---|---|---|"]
    for strategy, scores in sorted(coherence.items()):
        counts = "/".join(str(scores.count(v)) for v in (0, 1, 2))
        lines.append(f"| {strategy} | {len(scores)} | {sum(scores) / len(scores):.2f} | {counts} |")
    lines += ["", f"Chưa chấm: {missing} dòng.", ""]

    audit = defaultdict(lambda: [0, 0])
    missing = 0
    for r in rows("metadata_audit.csv"):
        if r["complete_and_correct_0_1"].strip():
            audit[r["strategy"]][0] += int(r["complete_and_correct_0_1"])
            audit[r["strategy"]][1] += 1
        else:
            missing += 1
    lines += ["## Metadata đủ và đúng (5 câu test × top-3)", "", "| Strategy | Đủ và đúng (n/N) |",
              "|---|---|"]
    for strategy, (ok, total) in sorted(audit.items()):
        lines.append(f"| {strategy} | {ok}/{total} |")
    lines += ["", f"Chưa chấm: {missing} dòng.", ""]

    grounding = defaultdict(list)
    missing = 0
    for r in rows("grounding.csv"):
        if r["score_0_1_2"].strip():
            grounding[r["strategy"]].append(int(r["score_0_1_2"]))
        else:
            missing += 1
    lines += ["## Grounding (5 câu test, top-3, thang 0-2)", "",
              "| Strategy | 0/1/2 (số câu) | Trung bình /2 |", "|---|---|---|"]
    for strategy, scores in sorted(grounding.items()):
        counts = "/".join(str(scores.count(v)) for v in (0, 1, 2))
        lines.append(f"| {strategy} | {counts} | {sum(scores) / len(scores):.2f} |")
    lines += ["", f"Chưa chấm: {missing} dòng.", ""]

    out = C.RESULTS / "labels_summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
