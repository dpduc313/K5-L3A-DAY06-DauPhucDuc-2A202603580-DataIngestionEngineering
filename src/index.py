"""Nạp các chunk ĐÃ DUYỆT vào pgvector (cổng duyệt trước khi index).

    python -m src.index --approve <12 ký tự đầu của fingerprint trong results/preview.html>

Chỉ nạp đúng bản parse đã xem trong preview: fingerprint khác là từ chối. Nạp lại cùng
phiên bản không tạo bản trùng: chunk có `text_sha256` không đổi được bỏ qua, chunk đổi thì
embed lại, chunk không còn thì xóa. Mỗi lần chạy ghi một dòng vào results/index_log.jsonl.

Tìm kiếm là exact (quét tuần tự, cosine), không tạo index HNSW: corpus nhỏ, và filter
metadata không làm thiếu kết quả như với approximate search.
"""

import argparse
import datetime as dt
import json
import sys
import time

from src import lab_config as C
from src.parse_docs import CHUNKINGS, parsed_fingerprint, read_jsonl
from perry import db, models  # noqa: E402

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS lab_chunks (
    chunk_id      text PRIMARY KEY,
    chunking      text NOT NULL,
    document_id   text NOT NULL,
    source        text NOT NULL,
    page          int  NOT NULL,
    chapter       text NOT NULL,
    section       text NOT NULL,
    chapters      text[] NOT NULL,
    sections      text[] NOT NULL,
    language      text NOT NULL,
    document_type text NOT NULL,
    text          text NOT NULL,
    text_sha256   text NOT NULL,
    embedding     vector({models.EMBEDDING_DIMENSIONS}) NOT NULL,
    embedding_model text NOT NULL,
    indexed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lab_chunks_chunking_idx ON lab_chunks (chunking);
"""

BATCH = 32


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", required=True, help="fingerprint (tiền tố) đã duyệt")
    approved = parser.parse_args().approve
    fingerprint = parsed_fingerprint()
    if len(approved) < 8 or not fingerprint.startswith(approved):
        sys.exit(
            f"Từ chối: bản parse hiện tại có fingerprint {fingerprint[:12]}, khác bản đã duyệt "
            f"{approved}. Chạy lại `python -m src.parse_docs preview` và duyệt lại."
        )
    db.init_schema()  # bảng Usage Ledger của Perrier
    with db.pool().connection() as conn:
        conn.execute(SCHEMA, prepare=False)
    model = models.embedding_model()
    log = {"at": dt.datetime.now().isoformat(timespec="seconds"), "fingerprint": fingerprint[:12]}
    for chunking in CHUNKINGS:
        started = time.monotonic()
        rows = read_jsonl(C.PARSED / f"chunks-{chunking}.jsonl")
        with db.pool().connection() as conn:
            stored = {
                r["chunk_id"]: (r["text_sha256"], r["embedding_model"])
                for r in conn.execute(
                    "SELECT chunk_id, text_sha256, embedding_model FROM lab_chunks WHERE chunking = %s",
                    (chunking,),
                )
            }
        wanted = {r["chunk_id"] for r in rows}
        todo = [r for r in rows if stored.get(r["chunk_id"]) != (r["text_sha256"], model)]
        gone = sorted(set(stored) - wanted)
        for start in range(0, len(todo), BATCH):
            batch = todo[start : start + BATCH]
            vectors = models.embed_documents([r["text"] for r in batch])
            with db.pool().connection() as conn, conn.transaction():
                for row, vector in zip(batch, vectors, strict=True):
                    conn.execute(
                        """INSERT INTO lab_chunks (chunk_id, chunking, document_id, source, page,
                               chapter, section, chapters, sections, language, document_type,
                               text, text_sha256, embedding, embedding_model)
                           VALUES (%(chunk_id)s, %(chunking)s, %(document_id)s, %(source)s, %(page)s,
                               %(chapter)s, %(section)s, %(chapters)s, %(sections)s, %(language)s,
                               %(document_type)s, %(text)s, %(text_sha256)s, %(embedding)s::vector,
                               %(model)s)
                           ON CONFLICT (chunk_id) DO UPDATE SET
                               chapter = EXCLUDED.chapter, section = EXCLUDED.section,
                               chapters = EXCLUDED.chapters, sections = EXCLUDED.sections,
                               page = EXCLUDED.page, text = EXCLUDED.text,
                               text_sha256 = EXCLUDED.text_sha256, embedding = EXCLUDED.embedding,
                               embedding_model = EXCLUDED.embedding_model, indexed_at = now()""",
                        {**row, "embedding": str(vector), "model": model},
                    )
            print(f"{chunking}: embedded {min(start + BATCH, len(todo))}/{len(todo)}", flush=True)
        with db.pool().connection() as conn:
            if gone:
                conn.execute("DELETE FROM lab_chunks WHERE chunk_id = ANY(%s)", (gone,))
            total = conn.execute(
                "SELECT count(*) AS n, count(DISTINCT chunk_id) AS distinct_ids "
                "FROM lab_chunks WHERE chunking = %s",
                (chunking,),
            ).fetchone()
        log[chunking] = {
            "parsed": len(rows),
            "embedded": len(todo),
            "unchanged": len(rows) - len(todo),
            "deleted": len(gone),
            "stored": total["n"],
            "seconds": round(time.monotonic() - started, 1),
        }
        print(f"{chunking}: {log[chunking]}", flush=True)
    log["embedding_model"] = model
    C.RESULTS.mkdir(exist_ok=True)
    with (C.RESULTS / "index_log.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(log, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
