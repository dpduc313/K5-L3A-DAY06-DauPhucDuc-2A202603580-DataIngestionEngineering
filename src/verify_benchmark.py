"""Kiểm chứng benchmark TRƯỚC khi chạy truy xuất.

    python -m src.verify_benchmark

- Mỗi `evidence_quote` (và của từng `alternatives`) phải là chuỗi con của text trang gold
  sau chuẩn hóa (data/parsed/pages.jsonl).
- Đủ trường bắt buộc; ≥20 câu; ≥15 dev, ≥5 test; ≥3 câu có filter, ≥1 trong test.
- Giá trị filter phải tồn tại trong metadata chunk (không tạo giá trị giả).
Sai bất kỳ điều nào thì thoát với mã 1.
"""

import json
import sys

from src import lab_config as C

REQUIRED = ("id", "split", "type", "question", "expected_answer", "gold_source_id",
            "gold_page", "evidence_quote", "filter")
FILTER_KEYS = ("chapter", "section", "language", "document_type")


def load_questions() -> list[dict]:
    path = C.BENCHMARK / "questions.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def golds(question: dict) -> list[dict]:
    """Nguồn gold chính và các nguồn hợp lệ khác."""
    main = {k: question[k] for k in ("gold_source_id", "gold_page", "evidence_quote")}
    return [main, *question.get("alternatives", [])]


def main() -> None:
    questions = load_questions()
    pages = {
        (row["document_id"], row["page"]): C.normalize(row["text"])
        for row in map(json.loads, (C.PARSED / "pages.jsonl").read_text("utf-8").splitlines())
    }
    values = {key: set() for key in FILTER_KEYS}
    for line in (C.PARSED / "chunks-heading.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line)
        for key in FILTER_KEYS:
            if key in ("chapter", "section"):
                values[key].update(row[f"{key}s"])
            else:
                values[key].add(row[key])
    problems = []
    ids = set()
    for q in questions:
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            problems.append(f"{q.get('id')}: thiếu trường {missing}")
            continue
        if q["id"] in ids:
            problems.append(f"{q['id']}: trùng id")
        ids.add(q["id"])
        if q["split"] not in ("dev", "test"):
            problems.append(f"{q['id']}: split phải là dev/test")
        for gold in golds(q):
            page = pages.get((gold["gold_source_id"], gold["gold_page"]))
            if page is None:
                problems.append(f"{q['id']}: không có trang {gold['gold_source_id']} p{gold['gold_page']}")
            elif C.normalize(gold["evidence_quote"]) not in page:
                problems.append(
                    f"{q['id']}: evidence không nằm trong {gold['gold_source_id']} p{gold['gold_page']}: "
                    f"{gold['evidence_quote'][:70]!r}"
                )
        for key, value in (q["filter"] or {}).items():
            if key not in FILTER_KEYS:
                problems.append(f"{q['id']}: trường filter {key!r} không hỗ trợ")
            elif value not in values[key]:
                problems.append(f"{q['id']}: giá trị filter {key}={value!r} không có trong metadata")
    dev = [q for q in questions if q["split"] == "dev"]
    test = [q for q in questions if q["split"] == "test"]
    filtered = [q for q in questions if q["filter"]]
    filtered_test = [q for q in test if q["filter"]]
    print(f"{len(questions)} câu: {len(dev)} dev / {len(test)} test; "
          f"{len(filtered)} câu có filter ({len(filtered_test)} trong test)")
    if len(questions) < 20 or len(dev) < 15 or len(test) < 5:
        problems.append("cần ≥20 câu, ≥15 dev, ≥5 test")
    if len(filtered) < 3 or not filtered_test:
        problems.append("cần ≥3 câu có filter, ≥1 trong test")
    for problem in problems:
        print("LỖI", problem)
    if problems:
        sys.exit(1)
    print("Benchmark hợp lệ: mọi evidence nằm đúng trang gold.")


if __name__ == "__main__":
    main()
