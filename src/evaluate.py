"""Chạy top-3 cho mọi câu hỏi với ba chiến lược, lưu trace và tính chỉ số.

    python -m src.evaluate                 # chỉ tập dev
    python -m src.evaluate --include-test  # dev + test; chỉ chạy được sau khi đã có
                                           # results/selection.md (chọn chiến lược trên dev)

Hit (định nghĩa của đề): chunk thuộc đúng nguồn/trang gold (hoặc một `alternatives`) VÀ
chứa trọn `evidence_quote` sau chuẩn hóa. Hit@1 = top-1 là hit; Evidence Hit@3 = có ít
nhất một hit trong top-3. "page_only" = đúng trang nhưng chunk không chứa trọn evidence
(thường do evidence bị cắt qua hai chunk) — vẫn tính là miss.

Kết quả: results/<A|B|C>/trace.jsonl, results/metrics.md, results/metrics.json và mẫu
nhãn thủ công trống trong results/labels/ (không ghi đè nhãn đã điền).
"""

import argparse
import csv
import json
import sys
import time

from src import lab_config as C
from src.parse_docs import read_jsonl
from src.verify_benchmark import golds, load_questions
from perry import db, models  # noqa: E402

SEARCH = """
SELECT chunk_id, document_id, source, page, chapter, section, chapters, sections, language,
       document_type, text, 1 - (embedding <=> %(q)s::vector) AS score
FROM lab_chunks
WHERE chunking = %(chunking)s {where}
ORDER BY embedding <=> %(q)s::vector
LIMIT %(k)s
"""


def search(vector: list[float], chunking: str, flt: dict | None) -> list[dict]:
    params = {"q": str(vector), "chunking": chunking, "k": C.TOP_K}
    where = ""
    for key, value in (flt or {}).items():
        # key đã được verify_benchmark giới hạn. chapter/section khớp khi chunk TRẢI QUA
        # chương/mục đó (chunk vắt qua ranh giới chương vẫn được giữ).
        if key in ("chapter", "section"):
            where += f" AND %({key})s = ANY({key}s)"
        else:
            where += f" AND {key} = %({key})s"
        params[key] = value
    with db.pool().connection() as conn:
        return [dict(r) for r in conn.execute(SEARCH.format(where=where), params)]


def is_hit(question: dict, hit: dict) -> bool:
    text = C.normalize(hit["text"])
    return any(
        hit["document_id"] == g["gold_source_id"]
        and hit["page"] == g["gold_page"]
        and C.normalize(g["evidence_quote"]) in text
        for g in golds(question)
    )


def on_gold_page(question: dict, hit: dict) -> bool:
    return any(
        hit["document_id"] == g["gold_source_id"] and hit["page"] == g["gold_page"]
        for g in golds(question)
    )


def follows(flt: dict | None, hit: dict) -> bool:
    return all(
        value in hit[f"{key}s"] if key in ("chapter", "section") else hit[key] == value
        for key, value in (flt or {}).items()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-test", action="store_true")
    include_test = parser.parse_args().include_test
    if include_test and not (C.RESULTS / "selection.md").exists():
        sys.exit("Chưa chọn chiến lược trên dev: viết results/selection.md trước khi chạy test.")
    questions = [q for q in load_questions() if include_test or q["split"] == "dev"]
    started = time.monotonic()
    vectors = {q["id"]: models.embed_query(q["question"]) for q in questions}
    embed_seconds = time.monotonic() - started

    summary = {}
    for name, strategy in C.STRATEGIES.items():
        out_dir = C.RESULTS / name
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        started = time.monotonic()
        for q in questions:
            flt = q["filter"] if strategy["filter"] else None
            hits = search(vectors[q["id"]], strategy["chunking"], flt)
            for rank, hit in enumerate(hits, start=1):
                rows.append(
                    {
                        "strategy": name,
                        "qid": q["id"],
                        "split": q["split"],
                        "type": q["type"],
                        "question": q["question"],
                        "filter_applied": flt,
                        "question_filter": q["filter"],
                        "rank": rank,
                        "chunk_id": hit["chunk_id"],
                        "score": round(float(hit["score"]), 4),
                        "metadata": {k: hit[k] for k in ("document_id", "source", "page", "chapter",
                                                          "section", "chapters", "sections",
                                                          "language", "document_type")},
                        "hit": is_hit(q, hit),
                        "on_gold_page": on_gold_page(q, hit),
                        "follows_question_filter": follows(q["filter"], hit) if q["filter"] else None,
                        "text": hit["text"],
                    }
                )
        seconds = time.monotonic() - started
        with (out_dir / "trace.jsonl").open("w", encoding="utf-8", newline="\n") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        summary[name] = {"seconds": round(seconds, 2), **score(questions, rows)}
    summary["_meta"] = {
        "embedding_model": models.embedding_model(),
        "query_embedding_seconds": round(embed_seconds, 1),
        "top_k": C.TOP_K,
        "questions": len(questions),
        "include_test": include_test,
    }
    (C.RESULTS / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    (C.RESULTS / "metrics.md").write_text(render(summary, questions), "utf-8")
    write_label_templates(questions)
    print((C.RESULTS / "metrics.md").read_text("utf-8"))


def score(questions: list[dict], rows: list[dict]) -> dict:
    by_q = {}
    for row in rows:
        by_q.setdefault(row["qid"], []).append(row)
    result = {}
    for split in ("dev", "test"):
        group = [q for q in questions if q["split"] == split]
        if not group:
            continue
        top = [by_q.get(q["id"], []) for q in group]
        hit1 = sum(bool(t) and t[0]["hit"] for t in top)
        hit3 = sum(any(r["hit"] for r in t) for t in top)
        page3 = sum(any(r["on_gold_page"] for r in t) for t in top)
        flt = [t for q, t in zip(group, top) if q["filter"]]
        result[split] = {
            "n": len(group),
            "hit1": hit1,
            "hit3": hit3,
            "page_hit3": page3,
            "page_only_misses": [
                q["id"] for q, t in zip(group, top)
                if not any(r["hit"] for r in t) and any(r["on_gold_page"] for r in t)
            ],
            "misses": [q["id"] for q, t in zip(group, top) if not any(r["hit"] for r in t)],
            "filter_questions": len(flt),
            "filter_compliant": sum(all(r["follows_question_filter"] for r in t) for t in flt),
        }
    return result


def render(summary: dict, questions: list[dict]) -> str:
    stats = json.loads((C.PARSED / "stats.json").read_text("utf-8"))
    meta = summary["_meta"]
    lines = [
        "# Kết quả truy xuất",
        "",
        f"Embedding: `{meta['embedding_model']}` (Ollama, local, $0). pgvector, cosine, exact "
        f"search, top-{meta['top_k']}. {meta['questions']} câu hỏi.",
        "",
        "| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Đúng trang @3 (n/N) | Filter tuân thủ "
        "| Chunk | Thời gian truy xuất |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, strategy in C.STRATEGIES.items():
        s = summary[name]
        chunks = stats[strategy["chunking"]]["chunks"]
        for split in ("dev", "test"):
            if split not in s:
                continue
            r = s[split]
            compliant = f"{r['filter_compliant']}/{r['filter_questions']}" if r["filter_questions"] else "N/A"
            lines.append(
                f"| {name} | {split} | {r['hit1']}/{r['n']} | {r['hit3']}/{r['n']} | "
                f"{r['page_hit3']}/{r['n']} | {compliant} | {chunks} | {s['seconds']} s |"
            )
    lines += ["", "## Câu trượt Evidence Hit@3", ""]
    for name in C.STRATEGIES:
        for split, r in summary[name].items():
            if split in ("dev", "test"):
                lines.append(
                    f"- **{name} / {split}**: {', '.join(r['misses']) or 'không có'}"
                    f" (đúng trang nhưng thiếu evidence: {', '.join(r['page_only_misses']) or 'không có'})"
                )
    return "\n".join(lines) + "\n"


def write_label_templates(questions: list[dict]) -> None:
    """Mẫu nhãn thủ công (trống). Không ghi đè file đã có để không mất nhãn đã điền."""
    C.LABELS.mkdir(parents=True, exist_ok=True)
    test = [q for q in questions if q["split"] == "test"]
    if not test:
        return
    traces = {name: read_jsonl(C.RESULTS / name / "trace.jsonl") for name in C.STRATEGIES}
    grounding = C.LABELS / "grounding.csv"
    if not grounding.exists():
        with grounding.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["qid", "strategy", "top3_chunk_ids", "score_0_1_2", "reason"])
            for name, rows in traces.items():
                for q in test:
                    ids = [r["chunk_id"] for r in rows if r["qid"] == q["id"]]
                    writer.writerow([q["id"], name, " ".join(ids), "", ""])
    audit = C.LABELS / "metadata_audit.csv"
    if not audit.exists():
        with audit.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["qid", "strategy", "rank", "chunk_id", "source", "page", "chapters",
                             "sections", "complete_and_correct_0_1", "note"])
            for name, rows in traces.items():
                for r in rows:
                    if r["split"] == "test":
                        m = r["metadata"]
                        writer.writerow([r["qid"], name, r["rank"], r["chunk_id"], m["source"],
                                         m["page"], "; ".join(m["chapters"]),
                                         "; ".join(m["sections"]), "", ""])


if __name__ == "__main__":
    main()
