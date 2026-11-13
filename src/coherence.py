"""Chọn 10 vị trí chấm coherence (trước khi xem điểm) và tạo mẫu nhãn trống.

    python -m src.coherence

Quy tắc chọn tất định: 5 trang được tính đầu tiên của mỗi tài liệu; vị trí là giữa text
trang đã chuẩn hóa. Với mỗi cách chunk, chunk được chấm là chunk cuối cùng trên trang có
điểm bắt đầu <= vị trí đó (chunk bao phủ vị trí). C dùng chunk của B nên chấm chung với B.
Ghi benchmark/coherence_positions.json và results/labels/coherence.csv (không ghi đè).
"""

import csv
import json

from src import lab_config as C
from src.parse_docs import CHUNKINGS, read_jsonl

PAGES_PER_DOCUMENT = 5


def main() -> None:
    pages = read_jsonl(C.PARSED / "pages.jsonl")
    positions = []
    for doc_id, spec in C.DOCUMENTS.items():
        for page in spec["pages"][:PAGES_PER_DOCUMENT]:
            row = next(r for r in pages if r["document_id"] == doc_id and r["page"] == page)
            norm = C.normalize(row["text"])
            offset = len(norm) // 2
            positions.append(
                {
                    "position_id": f"pos{len(positions) + 1:02d}",
                    "document_id": doc_id,
                    "page": page,
                    "offset": offset,
                    "anchor": norm[offset : offset + 60],
                }
            )
    (C.BENCHMARK / "coherence_positions.json").write_text(
        json.dumps(positions, ensure_ascii=False, indent=2), "utf-8"
    )
    out = C.LABELS / "coherence.csv"
    if out.exists():
        print(f"{out} đã có, không ghi đè.")
        return
    C.LABELS.mkdir(parents=True, exist_ok=True)
    chunks = {c: read_jsonl(C.PARSED / f"chunks-{c}.jsonl") for c in CHUNKINGS}
    with out.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["position_id", "strategy", "document_id", "page", "anchor", "chunk_id",
                         "score_0_1_2", "reason"])
        for pos in positions:
            for strategy, chunking in (("A", "fixed"), ("B/C", "heading")):
                on_page = [
                    r for r in chunks[chunking]
                    if r["document_id"] == pos["document_id"] and r["page"] == pos["page"]
                ]
                covering = [r for r in on_page if r["start"] <= pos["offset"]] or on_page[:1]
                writer.writerow([pos["position_id"], strategy, pos["document_id"], pos["page"],
                                 pos["anchor"], covering[-1]["chunk_id"], "", ""])
    print(f"Đã ghi {len(positions)} vị trí và {out}")


if __name__ == "__main__":
    main()
