"""Đọc, chuẩn hóa và chunk corpus; KHÔNG ghi vào vector store.

    python -m src.parse_docs ocr       # nd13: vision reader đọc từng trang scan (trả phí, có cache)
    python -m src.parse_docs parse     # trang + chunk cho hai cách chunk -> data/parsed/
    python -m src.parse_docs preview   # results/preview.html để duyệt trước khi index

Đọc và chunk dùng lại Perrier (perry.documents): aiayn đọc bằng Docling, nd13 đọc bằng
vision model thành Markdown theo trang. Metadata `chapter`/`section` được trích tất định
từ heading (regex), mang sang trang sau, không dùng LLM.
"""

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import re
import statistics
import sys
import time

from src import lab_config as C
from perry import db, documents, models  # noqa: E402  (sau lab_config)

CHUNKINGS = ("fixed", "heading")

# --- OCR (nd13) -------------------------------------------------------------------------


def ocr_dir(doc_id: str):
    return C.OCR_CACHE / doc_id


def run_ocr() -> None:
    db.init_schema()  # Usage Ledger của Perrier ghi chi phí từng lần gọi vào DB lab
    for doc_id, spec in C.DOCUMENTS.items():
        if spec["reader"] != "vision":
            continue
        path = C.RAW / spec["file"]
        out = ocr_dir(doc_id)
        out.mkdir(parents=True, exist_ok=True)
        meta_path = out / "meta.json"
        meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
        meta.update(
            model=models.page_reader_model(),
            source_sha256=documents.content_hash(path),
        )
        meta.setdefault("pages", {})
        errors = []
        for page in spec["pages"]:
            target = out / f"page-{page:02d}.md"
            if target.exists():
                continue
            started = time.monotonic()
            try:
                text = models.read_page_as_markdown(documents.render_page(path, page), "image/png")
            except Exception as error:  # ghi lỗi, đọc tiếp trang khác
                errors.append({"page": page, "error": repr(error)})
                print(f"{doc_id} p{page}: LỖI {error!r}", flush=True)
                continue
            target.write_text(text, encoding="utf-8")
            meta["pages"][str(page)] = {
                "read_at": dt.datetime.now().isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - started, 1),
                "chars": len(text),
            }
            print(f"{doc_id} p{page}: {len(text)} ký tự", flush=True)
        meta["errors"] = errors
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        if errors:
            sys.exit(f"{len(errors)} trang đọc lỗi; chạy lại để thử lại các trang đó.")


# --- Trang và chunk -----------------------------------------------------------------------


def page_texts(doc_id: str) -> dict[int, str]:
    """Text đã đọc của từng trang được tính: nguồn của chunk và của evidence."""
    spec = C.DOCUMENTS[doc_id]
    path = C.RAW / spec["file"]
    if spec["reader"] == "vision":
        texts = {}
        for page in spec["pages"]:
            cached = ocr_dir(doc_id) / f"page-{page:02d}.md"
            if not cached.exists():
                sys.exit(f"Chưa OCR {doc_id} trang {page}: chạy `python -m src.parse_docs ocr`.")
            texts[page] = promote_headings(cached.read_text("utf-8"))
        return texts
    converted = documents._convert(path.resolve(), documents.content_hash(path))
    return {page: converted.export_to_markdown(page_no=page) for page in spec["pages"]}


# Vision model đánh dấu heading không nhất quán (`## Điều 30.`, `**Điều 33.**` hay dòng
# thường `Điều 31.`). Chuẩn hóa tất định trước khi chunk để chunk theo heading cắt đúng
# từng Điều: Chương -> #, Mục -> ##, Điều -> ###.
LEGAL_HEADING = re.compile(
    r"^[#\s]*(?:\*\*)?\s*((Chương\s+[IVXLC]+)|(Mục\s+\d+)|(Điều\s+\d+\..*?))\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)


def promote_headings(text: str) -> str:
    lines = []
    for line in text.splitlines():
        m = LEGAL_HEADING.match(line)
        if m:
            level = "#" if m.group(2) else "##" if m.group(3) else "###"
            line = f"{level} {m.group(1).strip()}"
        lines.append(line)
    return "\n".join(lines)


def raw_chunks(doc_id: str, chunking: str, pages: dict[int, str]) -> list[documents.Chunk]:
    spec = C.DOCUMENTS[doc_id]
    if spec["reader"] == "vision":
        return [c for page, text in pages.items() for c in documents.page_chunks(page, text, chunking)]
    parsed = documents.parse(C.RAW / spec["file"], chunking, spec["reader"])
    return [c for c in parsed.chunks if c.page in pages]


ND13_CHAPTER = re.compile(r"^(Chương\s+[IVXLC]+)\b", re.IGNORECASE)
ND13_ARTICLE = re.compile(r"^(Điều\s+\d+)\.?\s*(.*)$", re.IGNORECASE)
PAPER_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,80})$")


def headings_in(doc_id: str, text: str) -> list[tuple[int, str | None, str]]:
    """(vị trí trong text đã chuẩn hóa, chapter mới hoặc None, section) của từng heading."""
    norm_page = C.normalize(text)
    found = []
    cursor = 0
    for raw_line in text.splitlines():
        line = re.sub(r"^[#>*\s]+|[*\s]+$", "", raw_line).strip()
        if not line:
            continue
        chapter = section = None
        if doc_id == "nd13":
            if m := ND13_CHAPTER.match(line):
                chapter = "Chương " + m.group(1).split()[-1].upper()
                section = chapter
            elif m := ND13_ARTICLE.match(line):
                section = m.group(1)
        else:
            if line.lower() == "abstract":
                chapter = section = "Abstract"
            elif m := PAPER_HEADING.match(line):
                section = f"{m.group(1)} {m.group(2).strip()}"
                if "." not in m.group(1):
                    chapter = section
        if section is None:
            continue
        position = norm_page.find(C.normalize(line), cursor)
        if position < 0:
            continue
        cursor = position
        found.append((position, chapter, section))
    return found


def locate(chunk_text: str, norm_page: str, after: int) -> tuple[int, int]:
    """(vị trí đầu, độ dài) của phần thân chunk trong trang đã chuẩn hóa, bỏ dần các dòng
    heading Perrier chèn vào đầu chunk theo heading; (-1, độ dài) nếu không tìm được."""
    lines = chunk_text.splitlines()
    for skip in range(min(4, len(lines))):
        body = C.normalize("\n".join(lines[skip:]))
        probe = body[:60]
        if len(probe) < 15:
            continue
        position = norm_page.find(probe, max(after - 200, 0))
        if position < 0:
            position = norm_page.find(probe)
        if position >= 0:
            return position, len(body)
    return -1, len(C.normalize(chunk_text))


def build(doc_id: str, pages: dict[int, str]) -> tuple[list[dict], dict[str, list[dict]]]:
    spec = C.DOCUMENTS[doc_id]
    page_rows = []
    chunk_rows: dict[str, list[dict]] = {}
    # Trạng thái (chapter, section) ở đầu mỗi trang: mang heading của trang trước sang.
    entry: dict[int, tuple[str, str]] = {}
    state = ("Front matter", "Front matter") if doc_id == "aiayn" else ("Mở đầu", "Mở đầu")
    page_headings = {}
    for page in sorted(pages):
        entry[page] = state
        heads = headings_in(doc_id, pages[page])
        page_headings[page] = heads
        for _, chapter, section in heads:
            state = (chapter or state[0], section)
        page_rows.append(
            {
                "document_id": doc_id,
                "source": spec["file"],
                "page": page,
                "chars": len(C.normalize(pages[page])),
                "text": pages[page],
            }
        )
    for chunking in CHUNKINGS:
        rows = []
        unlocated = 0
        last = {}
        for index, chunk in enumerate(raw_chunks(doc_id, chunking, pages)):
            norm_page = C.normalize(pages[chunk.page])
            position, length = locate(chunk.text, norm_page, last.get(chunk.page, 0))
            if position < 0:
                unlocated += 1
                position = last.get(chunk.page, 0)
            last[chunk.page] = position
            chapter, section = entry[chunk.page]
            for head_position, head_chapter, head_section in page_headings[chunk.page]:
                if head_position <= position:
                    chapter, section = head_chapter or chapter, head_section
            # Mọi chương/mục chunk trải qua, không chỉ điểm đầu: chunk vắt qua Điều 30-31
            # phải được ghi cả hai.
            chapters, sections = [chapter], [section]
            for head_position, head_chapter, head_section in page_headings[chunk.page]:
                if position < head_position < position + length:
                    if head_chapter and head_chapter not in chapters:
                        chapters.append(head_chapter)
                    if head_section not in sections:
                        sections.append(head_section)
            text = chunk.text
            rows.append(
                {
                    "chunk_id": f"{doc_id}-{chunking}-{index:04d}",
                    "document_id": doc_id,
                    "source": spec["file"],
                    "page": chunk.page,
                    "start": position,  # vị trí đầu thân chunk trong text trang đã chuẩn hóa
                    "chapter": chapter,  # chương tại điểm đầu chunk
                    "section": section,  # mục/Điều tại điểm đầu chunk
                    "chapters": chapters,  # mọi chương chunk trải qua (dùng cho filter)
                    "sections": sections,  # mọi mục/Điều chunk trải qua
                    "language": spec["language"],
                    "document_type": spec["document_type"],
                    "chunking": chunking,
                    "chars": len(text),
                    "tokens": models.count_embedding_tokens(text),
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "text": text,
                }
            )
        chunk_rows[chunking] = rows
        print(f"{doc_id}/{chunking}: {len(rows)} chunk, {unlocated} chunk không định vị được trong trang")
    return page_rows, chunk_rows


def run_parse() -> None:
    C.PARSED.mkdir(parents=True, exist_ok=True)
    all_pages = []
    all_chunks = {c: [] for c in CHUNKINGS}
    stats = {}
    for doc_id in C.DOCUMENTS:
        started = time.monotonic()
        pages = page_texts(doc_id)
        page_rows, chunk_rows = build(doc_id, pages)
        stats[doc_id] = {"parse_seconds": round(time.monotonic() - started, 1)}
        empty = [r["page"] for r in page_rows if r["chars"] < 50]
        stats[doc_id]["empty_pages"] = empty
        all_pages += page_rows
        for chunking in CHUNKINGS:
            all_chunks[chunking] += chunk_rows[chunking]
    write_jsonl(C.PARSED / "pages.jsonl", all_pages)
    for chunking, rows in all_chunks.items():
        write_jsonl(C.PARSED / f"chunks-{chunking}.jsonl", rows)
        lengths = [r["chars"] for r in rows]
        stats[chunking] = {
            "chunks": len(rows),
            "chars_total": sum(lengths),
            "tokens_total": sum(r["tokens"] for r in rows),
            "chars_min": min(lengths),
            "chars_median": statistics.median(lengths),
            "chars_mean": round(statistics.mean(lengths), 1),
            "chars_max": max(lengths),
        }
    (C.PARSED / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), "utf-8")
    write_manifest(all_pages)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


SOURCES = {
    "aiayn": {
        "title": "Attention Is All You Need (Vaswani et al., 2017)",
        "source_path_or_url": "data/raw/aiayn.pdf; gốc: https://arxiv.org/abs/1706.03762",
        "license_or_permission": (
            "arXiv non-exclusive license. Trang 1 ghi: Google cho phép tái sử dụng bảng và "
            "hình khi ghi nguồn, chỉ cho tác phẩm báo chí/học thuật. Dùng cho bài lab học "
            "thuật phi thương mại, giữ nguyên ghi nguồn."
        ),
        "snapshot": "PDF do pdfTeX tạo ngày 2024-04-10 (metadata của file)",
        "page_rule": "Tính trang 1-10 (nội dung). Bỏ trang 11-12 (tài liệu tham khảo) và "
        "13-15 (hình minh họa attention, chủ yếu là từ rời).",
    },
    "nd13": {
        "title": "Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân",
        "source_path_or_url": "data/raw/nd13.pdf; bản PDF ký số của Cổng Thông tin điện tử "
        "Chính phủ (thời gian ký 19.04.2023)",
        "license_or_permission": (
            "Văn bản quy phạm pháp luật: không thuộc đối tượng bảo hộ quyền tác giả "
            "(Điều 15 Luật Sở hữu trí tuệ)."
        ),
        "snapshot": "Bản scan, ký số 19.04.2023 14:22:26 +07:00",
        "page_rule": "Tính trang 1-28 (Chương I-IV, Điều 1-44). Bỏ trang 29-39 (Phụ lục biểu "
        "mẫu, chủ yếu ô trống và dòng chấm); bản OCR của chúng vẫn ở data/ocr/nd13/. Bản "
        "scan, OCR toàn bộ 39 trang bằng vision model (data/ocr/nd13/meta.json). Trang có "
        "ít hơn 50 ký tự sau OCR được liệt kê trong empty_pages.",
    },
}


def write_manifest(page_rows: list[dict]) -> None:
    import pymupdf

    entries = []
    for doc_id, spec in C.DOCUMENTS.items():
        path = C.RAW / spec["file"]
        with pymupdf.open(path) as pdf:
            physical = pdf.page_count
        rows = [r for r in page_rows if r["document_id"] == doc_id]
        entries.append(
            {
                "source_id": doc_id,
                **SOURCES[doc_id],
                "accessed_at": "2026-11-13",
                "sha256": documents.content_hash(path),
                "reader": spec["reader"],
                "language": spec["language"],
                "document_type": spec["document_type"],
                "physical_pages": physical,
                "counted_pages": [r["page"] for r in rows],
                "chars_per_page": {str(r["page"]): r["chars"] for r in rows},
                "chars_total": sum(r["chars"] for r in rows),
                "empty_pages": [r["page"] for r in rows if r["chars"] < 50],
            }
        )
    total = sum(len(e["counted_pages"]) - len(e["empty_pages"]) for e in entries)
    manifest = {
        "counted_content_pages": total,
        "char_rule": "Số ký tự sau chuẩn hóa (src/lab_config.normalize).",
        "documents": entries,
    }
    (C.DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def write_jsonl(path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def parsed_fingerprint() -> str:
    """Băm các file chunk đã parse: index chỉ chấp nhận đúng bản đã được duyệt."""
    digest = hashlib.sha256()
    for chunking in CHUNKINGS:
        digest.update((C.PARSED / f"chunks-{chunking}.jsonl").read_bytes())
    return digest.hexdigest()


# --- Preview ------------------------------------------------------------------------------


def run_preview() -> None:
    pages = read_jsonl(C.PARSED / "pages.jsonl")
    chunks = {c: read_jsonl(C.PARSED / f"chunks-{c}.jsonl") for c in CHUNKINGS}
    stats = json.loads((C.PARSED / "stats.json").read_text("utf-8"))
    fingerprint = parsed_fingerprint()
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Duyệt parse và chunk</title>",
        "<style>body{font:14px system-ui;margin:16px;background:#fafafa;color:#222}"
        ".page{display:grid;grid-template-columns:320px 1fr 1fr 1fr;gap:10px;border-top:2px solid #999;padding:10px 0}"
        "img{width:320px;border:1px solid #ccc}pre{white-space:pre-wrap;margin:0;font:12px ui-monospace,monospace}"
        ".chunk{background:#fff;border:1px solid #ddd;border-left:4px solid #4a7;margin:0 0 6px;padding:6px}"
        ".meta{color:#666;font-size:11px;margin-bottom:4px}h3{margin:4px 0}</style>",
        "<h1>Duyệt parse và chunk trước khi index</h1>",
        f"<p>Fingerprint: <code>{fingerprint}</code>. Sau khi duyệt, chạy "
        f"<code>python -m src.index --approve {fingerprint[:12]}</code>.</p>",
        f"<pre>{html.escape(json.dumps(stats, ensure_ascii=False, indent=2))}</pre>",
    ]
    for page_row in pages:
        doc_id, page = page_row["document_id"], page_row["page"]
        image = documents.render_page(C.RAW / C.DOCUMENTS[doc_id]["file"], page)
        b64 = base64.b64encode(_shrink(image)).decode()
        cols = [f"<div><h3>{doc_id} · trang {page}</h3><img src='data:image/png;base64,{b64}'></div>"]
        cols.append(
            f"<div><h3>Text đã đọc ({page_row['chars']} ký tự chuẩn hóa)</h3>"
            f"<pre>{html.escape(page_row['text'])}</pre></div>"
        )
        for chunking in CHUNKINGS:
            boxes = [f"<h3>{chunking}</h3>"]
            for row in chunks[chunking]:
                if row["document_id"] == doc_id and row["page"] == page:
                    boxes.append(
                        f"<div class='chunk'><div class='meta'>{row['chunk_id']} · {row['chars']} ký tự · "
                        f"{row['tokens']} token · chapters=<b>{html.escape(', '.join(row['chapters']))}</b> · "
                        f"sections=<b>{html.escape(', '.join(row['sections']))}</b></div>"
                        f"<pre>{html.escape(row['text'])}</pre></div>"
                    )
            cols.append("<div>" + "".join(boxes) + "</div>")
        parts.append("<div class='page'>" + "".join(cols) + "</div>")
    C.RESULTS.mkdir(exist_ok=True)
    out = C.RESULTS / "preview.html"
    out.write_text("".join(parts), encoding="utf-8")
    print(f"Đã ghi {out}; fingerprint {fingerprint[:12]}")


def _shrink(png: bytes) -> bytes:
    import pymupdf

    pix = pymupdf.Pixmap(png)
    return pymupdf.Pixmap(pix, int(pix.width * 0.45), int(pix.height * 0.45), None).tobytes("png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("ocr", "parse", "preview"))
    step = parser.parse_args().step
    {"ocr": run_ocr, "parse": run_parse, "preview": run_preview}[step]()


if __name__ == "__main__":
    main()
