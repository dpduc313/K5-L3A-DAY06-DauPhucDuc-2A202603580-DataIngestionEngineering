"""Bonus: thêm sách "Deep Learning cơ bản" vào corpus và thử hybrid retrieval (dense + BM25).

    python -m src.bonus parse      # đọc sách -> data/bonus/ (trang, chunk heading, manifest)
    python -m src.bonus verify     # evidence của benchmark bonus nằm đúng trang gold
    python -m src.bonus index      # embed chunk của sách vào lab_chunks (chunking 'heading-dlcb')
    python -m src.bonus evaluate        # dense / BM25 / 12 cấu hình hybrid trên dev, chọn tham số
    python -m src.bonus evaluate-test   # dense / BM25 / hybrid đã chọn trên dev + test (một lần)

Tách khỏi kết quả chính: chunk của sách lưu với `chunking = 'heading-dlcb'`, nên
`src.evaluate` (lọc `chunking = 'heading'`) vẫn chỉ thấy 2 tài liệu như trong báo cáo.
Corpus bonus = chunk heading của aiayn, nd13 (chiến lược B/C) + chunk heading của sách.
"""

import hashlib
import json
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

from src import lab_config as C
from src.parse_docs import locate, read_jsonl, write_jsonl
from perry import documents, models  # noqa: E402  (sau lab_config)

BONUS_DATA = C.DATA / "bonus"
BONUS_RESULTS = C.RESULTS / "bonus"
DOC_ID = "dlcb"
SOURCE_PDF = Path(r"C:\Users\teflo\Desktop\Study\Sách - giáo trình\Deep Learning cơ bản_v2.pdf")
PDF = C.RAW / "dlcb.pdf"
CHUNKING = "heading-dlcb"  # nhãn trong lab_chunks; cách chunk giống B ("heading")

# Trang bìa của 8 Phần: chỉ có số La Mã và mục lục mini của phần, không phải nội dung.
PART_PAGES = {17, 45, 81, 107, 159, 191, 225, 263}
CONTENT_PAGES = [p for p in range(19, 299) if p not in PART_PAGES]  # 299-301: Bibliography
HEADER_BAND = 75  # header chạy (số trang + tên chương/mục) nằm ở y ≈ 62-64
HEADING_FONT = "URWGothicL-Demi"
SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+){1,2})\s+(\S.*)$")
CHAPTER_TITLE = re.compile(r"^(\d+)\.\s+(\S.*)$")
# Heading do page_markdown tạo: "# 3 Linear regression", "## 3.1 Bài toán", "### 3.1.1 …"
HEADING_LINE = re.compile(r"^(#{1,3}) (\d+(?:\.\d+){0,2} \S.*)$")


# --- Đọc PDF ------------------------------------------------------------------------------


def _line_text(line: dict) -> str:
    """Text của một dòng, chèn lại dấu cách mà lớp text bị mất: font tiếng Việt của LaTeX
    (vntex) làm mất dấu cách sau chữ có dấu ("mởđầu"), nhưng khoảng trống giữa hai glyph vẫn
    còn, nên khoảng trống > 0,18 cỡ chữ được coi là dấu cách."""
    text, previous = "", None
    for span in line["spans"]:
        for char in span["chars"]:
            c = char["c"]
            if previous is not None and c != " " and not text.endswith(" "):
                if char["bbox"][0] - previous > 0.18 * span["size"]:
                    text += " "
            text += c
            previous = char["bbox"][2]
    return text.rstrip()


# Một đoạn Markdown không được vượt giới hạn token của chunker (384): HybridChunker của
# Perrier crash khi phải tự tách một đoạn quá dài (`_EmbeddingTokens.get_tokenizer()` trả
# None). Chừa chỗ cho dòng heading mà chunker chèn vào đầu chunk.
PARAGRAPH_TOKENS = 300


def page_markdown(page) -> str:
    """Trang sách thành Markdown: bỏ header chạy; tên chương (cỡ chữ ≥ 18) -> `#`, mục `N.M`
    -> `##`, mục con `N.M.K` -> `###` (font heading của sách). Số mục và tên mục nằm ở hai
    dòng cùng tung độ được ghép lại. Mỗi block của PyMuPDF là một đoạn (cách bằng dòng trống);
    đoạn dài hơn PARAGRAPH_TOKENS được chia theo dòng."""
    # (block, y, cỡ chữ, font heading, text)
    rows: list[tuple[int, float, float, bool, str]] = []
    for number, block in enumerate(page.get_text("rawdict")["blocks"]):
        for line in block.get("lines", []):
            y = round(line["bbox"][1])
            if y < HEADER_BAND:
                continue
            text = _line_text(line)
            if not text.strip():
                continue
            size = max(s["size"] for s in line["spans"])
            heading_font = all(HEADING_FONT in s["font"] for s in line["spans"] if s["chars"])
            if rows and abs(rows[-1][1] - y) <= 2 and rows[-1][3] and heading_font:
                prev = rows[-1]
                rows[-1] = (prev[0], prev[1], max(prev[2], size), True, f"{prev[4]} {text}")
            else:
                rows.append((number, y, size, heading_font, text))
    paragraphs: list[list[str]] = []
    current_block = None
    for number, _, size, heading_font, text in rows:
        heading = None
        if heading_font and size >= 18 and (m := CHAPTER_TITLE.match(text.strip())):
            heading = f"# {m.group(1)} {m.group(2)}"
        elif heading_font and (m := SECTION_NUMBER.match(text.strip())):
            level = "##" if m.group(1).count(".") == 1 else "###"
            heading = f"{level} {m.group(1)} {m.group(2)}"
        if text.lstrip().startswith("#"):
            # Comment trong code Python ("# create the gan"): escape để Markdown không coi
            # là heading (normalize bỏ lại dấu "\").
            text = "\\" + text.lstrip()
        if heading:
            paragraphs.append([heading])
            current_block = None
        elif number != current_block:
            paragraphs.append([text])
            current_block = number
        else:
            paragraphs[-1].append(text)
    out = []
    for lines in paragraphs:
        out += _split_long(lines)
    return "\n\n".join(out)


def _split_long(lines: list[str]) -> list[str]:
    """Các dòng của một đoạn, gom thành các đoạn không quá PARAGRAPH_TOKENS token."""
    pieces, current = [], []
    for line in lines:
        if current and models.count_embedding_tokens("\n".join([*current, line])) > PARAGRAPH_TOKENS:
            pieces.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        pieces.append("\n".join(current))
    return pieces


def headings(markdown: str) -> list[tuple[int, str | None, str]]:
    """(vị trí trong text đã chuẩn hóa, chapter mới hoặc None, section) của từng heading."""
    norm = C.normalize(markdown)
    found, cursor = [], 0
    for line in markdown.splitlines():
        m = HEADING_LINE.match(line)
        if not m:
            continue
        level, title = len(m.group(1)), m.group(2)
        position = norm.find(C.normalize(title), cursor)
        if position < 0:
            continue
        cursor = position
        if level == 1:
            found.append((position, title, title))
        elif level == 2:
            found.append((position, None, title))
        # mục con (###) không đổi section: filter và truy vết dùng chương và mục N.M
    return found


def run_parse() -> None:
    import pymupdf

    BONUS_DATA.mkdir(parents=True, exist_ok=True)
    if not PDF.exists():
        shutil.copyfile(SOURCE_PDF, PDF)
    started = time.monotonic()
    pdf = pymupdf.open(PDF)
    pages = {p: page_markdown(pdf[p - 1]) for p in CONTENT_PAGES}
    state = ("Mở đầu", "Mở đầu")
    entry, page_heads, page_rows = {}, {}, []
    for page in CONTENT_PAGES:
        entry[page] = state
        page_heads[page] = headings(pages[page])
        for _, chapter, section in page_heads[page]:
            state = (chapter or state[0], section)
        page_rows.append({"document_id": DOC_ID, "source": PDF.name, "page": page,
                          "chars": len(C.normalize(pages[page])), "text": pages[page]})
    rows, unlocated, last = [], 0, {}
    raw = [c for page, text in pages.items() for c in documents.page_chunks(page, text, "heading")]
    for index, chunk in enumerate(raw):
        norm_page = C.normalize(pages[chunk.page])
        position, length = locate(chunk.text, norm_page, last.get(chunk.page, 0))
        if position < 0:
            unlocated += 1
            position = last.get(chunk.page, 0)
        last[chunk.page] = position
        chapter, section = entry[chunk.page]
        for head_position, head_chapter, head_section in page_heads[chunk.page]:
            if head_position <= position:
                chapter, section = head_chapter or chapter, head_section
        chapters, sections = [chapter], [section]
        for head_position, head_chapter, head_section in page_heads[chunk.page]:
            if position < head_position < position + length:
                if head_chapter and head_chapter not in chapters:
                    chapters.append(head_chapter)
                if head_section not in sections:
                    sections.append(head_section)
        rows.append({
            "chunk_id": f"{DOC_ID}-heading-{index:04d}",
            "document_id": DOC_ID,
            "source": PDF.name,
            "page": chunk.page,
            "start": position,
            "chapter": chapter,
            "section": section,
            "chapters": chapters,
            "sections": sections,
            "language": "vi",
            "document_type": "book",
            "chunking": "heading",
            "chars": len(chunk.text),
            "tokens": models.count_embedding_tokens(chunk.text),
            "text_sha256": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            "text": chunk.text,
        })
    seconds = round(time.monotonic() - started, 1)
    write_jsonl(BONUS_DATA / "pages-dlcb.jsonl", page_rows)
    write_jsonl(BONUS_DATA / "chunks-dlcb.jsonl", rows)
    lengths = [r["chars"] for r in rows]
    empty = [r["page"] for r in page_rows if r["chars"] < 50]
    stats = {
        "parse_seconds": seconds,
        "pages": len(page_rows),
        "empty_pages": empty,
        "chunks": len(rows),
        "unlocated_chunks": unlocated,
        "chars_total": sum(lengths),
        "tokens_total": sum(r["tokens"] for r in rows),
        "chars_min": min(lengths),
        "chars_median": statistics.median(lengths),
        "chars_max": max(lengths),
        "chapters": sorted({c for r in rows for c in r["chapters"]}, key=_chapter_order),
    }
    (BONUS_DATA / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), "utf-8")
    write_manifest(page_rows, pdf.page_count)
    print(json.dumps({k: v for k, v in stats.items() if k != "chapters"}, ensure_ascii=False))
    print("chapters:", stats["chapters"])


def _chapter_order(chapter: str) -> tuple[int, str]:
    head = chapter.split()[0]
    return (int(head), chapter) if head.isdigit() else (-1, chapter)


def write_manifest(page_rows: list[dict], physical: int) -> None:
    empty = [r["page"] for r in page_rows if r["chars"] < 50]
    entry = {
        "source_id": DOC_ID,
        "title": "Deep Learning cơ bản, tái bản lần 2 (Nguyễn Thanh Tuấn, 8/2020)",
        "source_path_or_url": "data/raw/dlcb.pdf; trang 2 ghi NTTUAN8.COM",
        "license_or_permission": (
            "Trang 2 chỉ ghi 'Copyright © 2019 Nguyễn Thanh Tuấn', không có giấy phép phân phối lại "
            "(chưa xác minh điều khoản trên nttuan8.com). Dùng cho bài lab học thuật phi thương mại, "
            "giữ nguyên ghi nguồn; người nộp quyết định đưa PDF và text vào repo."
        ),
        "snapshot": "Version 2, last update August 2020; PDF do pdfTeX tạo 2020-08-07",
        "page_rule": (
            "Tính trang 19-298 (Chương 1-22). Bỏ trang 1-16 (bìa, bản quyền, lời mở đầu, mục "
            "lục), 8 trang bìa Phần (17, 45, 81, 107, 159, 191, 225, 263: số La Mã và mục lục "
            "mini) và 299-301 (Bibliography). Trang có ít hơn 50 ký tự sau chuẩn hóa nằm trong "
            "empty_pages và không được tính."
        ),
        "reader": "pymupdf (rawdict) + chèn lại dấu cách theo khoảng trống giữa glyph",
        "accessed_at": "2026-11-14",
        "sha256": documents.content_hash(PDF),
        "language": "vi",
        "document_type": "book",
        "physical_pages": physical,
        "counted_pages": [r["page"] for r in page_rows if r["chars"] >= 50],
        "chars_per_page": {str(r["page"]): r["chars"] for r in page_rows},
        "chars_total": sum(r["chars"] for r in page_rows),
        "empty_pages": empty,
    }
    main = json.loads((C.DATA / "manifest.json").read_text("utf-8"))
    manifest = {
        "note": "Corpus bonus = corpus chính (data/manifest.json) + sách dlcb.",
        "counted_content_pages": main["counted_content_pages"] + len(entry["counted_pages"]),
        "char_rule": main["char_rule"],
        "documents": [*main["documents"], entry],
    }
    (BONUS_DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


# --- Benchmark bonus ----------------------------------------------------------------------


def load_questions() -> list[dict]:
    """20 câu của benchmark chính + các câu về sách."""
    from src.verify_benchmark import load_questions as main_questions

    extra = read_jsonl(C.BENCHMARK / "bonus_questions.jsonl")
    return [*main_questions(), *extra]


def run_verify() -> None:
    """Evidence của mọi câu nằm trong trang gold (sau chuẩn hóa); giá trị filter tồn tại."""
    from src.verify_benchmark import golds

    pages = {
        (r["document_id"], r["page"]): C.normalize(r["text"])
        for r in [*read_jsonl(C.PARSED / "pages.jsonl"), *read_jsonl(BONUS_DATA / "pages-dlcb.jsonl")]
    }
    chapters = {c for r in corpus_rows_from_files() for c in r["chapters"]}
    problems = []
    questions = load_questions()
    for q in questions:
        for g in golds(q):
            page = pages.get((g["gold_source_id"], g["gold_page"]))
            if page is None:
                problems.append(f"{q['id']}: không có trang {g['gold_source_id']} p{g['gold_page']}")
            elif C.normalize(g["evidence_quote"]) not in page:
                problems.append(f"{q['id']}: evidence không nằm trong {g['gold_source_id']} "
                                f"p{g['gold_page']}: {g['evidence_quote'][:60]!r}")
        for key, value in (q["filter"] or {}).items():
            if key != "chapter" or value not in chapters:
                problems.append(f"{q['id']}: filter {key}={value!r} không có trong metadata")
    dev = sum(q["split"] == "dev" for q in questions)
    print(f"{len(questions)} câu: {dev} dev / {len(questions) - dev} test; "
          f"{sum(bool(q['filter']) for q in questions)} câu có filter")
    for problem in problems:
        print("LỖI", problem)
    if problems:
        sys.exit(1)
    print("Benchmark bonus hợp lệ: mọi evidence nằm đúng trang gold.")


def corpus_rows_from_files() -> list[dict]:
    """Chunk của corpus bonus theo file: heading của aiayn, nd13 + chunk của sách."""
    return [*read_jsonl(C.PARSED / "chunks-heading.jsonl"), *read_jsonl(BONUS_DATA / "chunks-dlcb.jsonl")]


# --- Index --------------------------------------------------------------------------------


def run_index() -> None:
    """Embed chunk của sách vào lab_chunks (chunking 'heading-dlcb'); nạp lại không trùng."""
    import datetime as dt

    from perry import db

    from src.index import BATCH, SCHEMA

    rows = read_jsonl(BONUS_DATA / "chunks-dlcb.jsonl")
    model = models.embedding_model()
    db.init_schema()
    started = time.monotonic()
    with db.pool().connection() as conn:
        conn.execute(SCHEMA, prepare=False)
        stored = {
            r["chunk_id"]: (r["text_sha256"], r["embedding_model"])
            for r in conn.execute(
                "SELECT chunk_id, text_sha256, embedding_model FROM lab_chunks WHERE chunking = %s",
                (CHUNKING,),
            )
        }
    todo = [r for r in rows if stored.get(r["chunk_id"]) != (r["text_sha256"], model)]
    gone = sorted(set(stored) - {r["chunk_id"] for r in rows})
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        vectors = models.embed_documents([r["text"] for r in batch])
        with db.pool().connection() as conn, conn.transaction():
            for row, vector in zip(batch, vectors, strict=True):
                conn.execute(
                    """INSERT INTO lab_chunks (chunk_id, chunking, document_id, source, page,
                           chapter, section, chapters, sections, language, document_type,
                           text, text_sha256, embedding, embedding_model)
                       VALUES (%(chunk_id)s, %(label)s, %(document_id)s, %(source)s, %(page)s,
                           %(chapter)s, %(section)s, %(chapters)s, %(sections)s, %(language)s,
                           %(document_type)s, %(text)s, %(text_sha256)s, %(embedding)s::vector,
                           %(model)s)
                       ON CONFLICT (chunk_id) DO UPDATE SET
                           chapter = EXCLUDED.chapter, section = EXCLUDED.section,
                           chapters = EXCLUDED.chapters, sections = EXCLUDED.sections,
                           page = EXCLUDED.page, text = EXCLUDED.text,
                           text_sha256 = EXCLUDED.text_sha256, embedding = EXCLUDED.embedding,
                           embedding_model = EXCLUDED.embedding_model, indexed_at = now()""",
                    {**row, "label": CHUNKING, "embedding": str(vector), "model": model},
                )
        print(f"{CHUNKING}: embedded {min(start + BATCH, len(todo))}/{len(todo)}", flush=True)
    with db.pool().connection() as conn:
        if gone:
            conn.execute("DELETE FROM lab_chunks WHERE chunk_id = ANY(%s)", (gone,))
        stored_now = conn.execute(
            "SELECT count(*) AS n FROM lab_chunks WHERE chunking = %s", (CHUNKING,)
        ).fetchone()["n"]
    log = {
        "at": dt.datetime.now().isoformat(timespec="seconds"),
        "chunking": CHUNKING,
        "parsed": len(rows),
        "embedded": len(todo),
        "unchanged": len(rows) - len(todo),
        "deleted": len(gone),
        "stored": stored_now,
        "seconds": round(time.monotonic() - started, 1),
        "embedding_model": model,
    }
    BONUS_RESULTS.mkdir(parents=True, exist_ok=True)
    with (BONUS_RESULTS / "index_log.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(log, ensure_ascii=False) + "\n")
    print(log)


# --- Truy xuất: dense, BM25, hybrid --------------------------------------------------------

BM25_K1, BM25_B = 1.5, 0.75
DEPTHS, RRF_KS, BM25_WEIGHTS = (20, 50), (10, 30, 60), (0.5, 1.0)
DEFAULT = (20, 60, 1.0)  # (N, k, w): cấu hình mặc định, dùng để phá hòa


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", C.normalize(text))


class Corpus:
    """Chunk của corpus bonus (đọc từ lab_chunks) và chỉ mục BM25 trên chúng."""

    def __init__(self):
        from collections import Counter

        from perry import db

        with db.pool().connection() as conn:
            self.rows = [dict(r) for r in conn.execute(
                """SELECT chunk_id, document_id, source, page, chapter, section, chapters, sections,
                          language, document_type, text
                   FROM lab_chunks WHERE chunking = ANY(%s) ORDER BY chunk_id""",
                (["heading", CHUNKING],),
            )]
        self.docs = [Counter(tokens(r["text"])) for r in self.rows]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avgdl = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.rows)
        self.idf = {t: __import__("math").log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.index = {r["chunk_id"]: i for i, r in enumerate(self.rows)}

    def allowed(self, flt: dict | None) -> list[int]:
        return [i for i, r in enumerate(self.rows)
                if all(v in r["chapters"] for k, v in (flt or {}).items() if k == "chapter")]

    def bm25(self, question: str, flt: dict | None, n: int) -> list[str]:
        q = tokens(question)
        scored = []
        for i in self.allowed(flt):
            tf, s = self.docs[i], 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (BM25_K1 + 1) / (
                        f + BM25_K1 * (1 - BM25_B + BM25_B * self.lengths[i] / self.avgdl))
            scored.append((s, self.rows[i]["chunk_id"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [cid for s, cid in scored[:n] if s > 0]


def dense(vector: list[float], flt: dict | None, n: int) -> list[str]:
    from perry import db

    where, params = "", {"q": str(vector), "labels": ["heading", CHUNKING], "n": n}
    if flt and "chapter" in flt:
        where, params["chapter"] = " AND %(chapter)s = ANY(chapters)", flt["chapter"]
    sql = f"""SELECT chunk_id FROM lab_chunks WHERE chunking = ANY(%(labels)s){where}
              ORDER BY embedding <=> %(q)s::vector, chunk_id LIMIT %(n)s"""
    with db.pool().connection() as conn:
        return [r["chunk_id"] for r in conn.execute(sql, params)]


def fuse(dense_ids: list[str], bm25_ids: list[str], n: int, k: int, w: float) -> list[str]:
    """Weighted RRF trên N ứng viên đầu của mỗi bên: 1/(k+r_dense) + w/(k+r_bm25)."""
    score: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids[:n], start=1):
        score[cid] = score.get(cid, 0.0) + 1 / (k + rank)
    for rank, cid in enumerate(bm25_ids[:n], start=1):
        score[cid] = score.get(cid, 0.0) + w / (k + rank)
    return sorted(score, key=lambda cid: (-score[cid], cid))


def name_of(n: int, k: int, w: float) -> str:
    return f"hybrid_N{n}_k{k}_w{w}"


def is_hit(question: dict, row: dict) -> bool:
    from src.verify_benchmark import golds

    text = C.normalize(row["text"])
    return any(row["document_id"] == g["gold_source_id"] and row["page"] == g["gold_page"]
               and C.normalize(g["evidence_quote"]) in text for g in golds(question))


def run_evaluate(include_test: bool) -> None:
    BONUS_RESULTS.mkdir(parents=True, exist_ok=True)
    selection = BONUS_RESULTS / "selection.json"
    if include_test and not selection.exists():
        sys.exit("Chưa chọn cấu hình trên dev: chạy `python -m src.bonus evaluate` trước.")
    questions = [q for q in load_questions() if include_test or q["split"] == "dev"]
    corpus = Corpus()
    started = time.monotonic()
    vectors = {q["id"]: models.embed_query(q["question"]) for q in questions}
    embed_seconds = round(time.monotonic() - started, 1)
    deepest = max(DEPTHS)
    ranked = {
        q["id"]: (dense(vectors[q["id"]], q["filter"], deepest),
                  corpus.bm25(q["question"], q["filter"], deepest))
        for q in questions
    }
    configs = {"dense": lambda d, b: d, "bm25": lambda d, b: b}
    if include_test:
        chosen = json.loads(selection.read_text("utf-8"))["chosen"]
        n, k, w = chosen["N"], chosen["k"], chosen["w"]
        configs[name_of(n, k, w)] = lambda d, b, n=n, k=k, w=w: fuse(d, b, n, k, w)
    else:
        for n in DEPTHS:
            for k in RRF_KS:
                for w in BM25_WEIGHTS:
                    configs[name_of(n, k, w)] = lambda d, b, n=n, k=k, w=w: fuse(d, b, n, k, w)
    results, traces = {}, {}
    for name, rank in configs.items():
        rows = []
        for q in questions:
            dense_ids, bm25_ids = ranked[q["id"]]
            full = rank(dense_ids, bm25_ids)
            first_hit = next((i + 1 for i, cid in enumerate(full) if is_hit(q, corpus.rows[corpus.index[cid]])), None)
            for position, cid in enumerate(full[: C.TOP_K], start=1):
                row = corpus.rows[corpus.index[cid]]
                rows.append({
                    "config": name, "qid": q["id"], "split": q["split"], "type": q["type"],
                    "question": q["question"], "filter": q["filter"], "rank": position,
                    "chunk_id": cid,
                    "rank_dense": dense_ids.index(cid) + 1 if cid in dense_ids else None,
                    "rank_bm25": bm25_ids.index(cid) + 1 if cid in bm25_ids else None,
                    "first_hit_rank": first_hit,
                    "metadata": {k: row[k] for k in ("document_id", "source", "page", "chapter",
                                                      "chapters", "sections")},
                    "hit": is_hit(q, row),
                    "follows_filter": (all(v in row["chapters"] for v in q["filter"].values())
                                       if q["filter"] else None),
                    "text": row["text"],
                })
        traces[name] = rows
        results[name] = score(questions, rows)
    summary = {"_meta": {"embedding_model": models.embedding_model(), "query_embedding_seconds": embed_seconds,
                         "corpus_chunks": len(corpus.rows), "questions": len(questions),
                         "include_test": include_test, "bm25": {"k1": BM25_K1, "b": BM25_B}},
               **results}
    if include_test:
        for name, rows in traces.items():
            write_jsonl(BONUS_RESULTS / f"trace-{name.split('_')[0]}.jsonl", rows)
        (BONUS_RESULTS / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
        (BONUS_RESULTS / "metrics.md").write_text(render_final(summary, traces, questions), "utf-8")
        print((BONUS_RESULTS / "metrics.md").read_text("utf-8"))
    else:
        chosen = choose(results)
        (BONUS_RESULTS / "grid_dev.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
        selection.write_text(json.dumps({"chosen": chosen, "criteria": "benchmark/bonus_selection_criteria.md"},
                                        ensure_ascii=False, indent=2), "utf-8")
        (BONUS_RESULTS / "selection.md").write_text(render_grid(results, chosen), "utf-8")
        print((BONUS_RESULTS / "selection.md").read_text("utf-8"))


def score(questions: list[dict], rows: list[dict]) -> dict:
    by_q: dict[str, list[dict]] = {}
    for row in rows:
        by_q.setdefault(row["qid"], []).append(row)
    out = {}
    for split in ("dev", "test"):
        group = [q for q in questions if q["split"] == split]
        if not group:
            continue
        top = [by_q.get(q["id"], []) for q in group]
        first = [next((r["rank"] for r in t if r["hit"]), None) for t in top]
        flt = [t for q, t in zip(group, top) if q["filter"]]
        out[split] = {
            "n": len(group),
            "hit1": sum(f == 1 for f in first),
            "hit3": sum(f is not None for f in first),
            "mrr3": round(sum(1 / f for f in first if f) / len(group), 4),
            "misses": [q["id"] for q, f in zip(group, first) if f is None],
            "filter_questions": len(flt),
            "filter_compliant": sum(all(r["follows_filter"] for r in t) for t in flt),
        }
    return out


def choose(results: dict) -> dict:
    """Cấu hình hybrid tốt nhất trên dev theo benchmark/bonus_selection_criteria.md."""
    def key(item):
        name, r = item
        n, k, w = (float(p[1:]) if p[0] == "w" else int(p[1:]) for p in name.split("_")[1:])
        closeness = (w != DEFAULT[2], abs(k - DEFAULT[1]), abs(n - DEFAULT[0]))
        return (-r["dev"]["hit3"], -r["dev"]["hit1"], -r["dev"]["mrr3"], closeness)

    name, r = min(((n, r) for n, r in results.items() if n.startswith("hybrid")), key=key)
    n, k, w = (float(p[1:]) if p[0] == "w" else int(p[1:]) for p in name.split("_")[1:])
    return {"name": name, "N": n, "k": k, "w": w, "dev": r["dev"]}


def render_grid(results: dict, chosen: dict) -> str:
    lines = ["# Bonus: chọn cấu hình trên dev", "",
             "Tiêu chí (chốt trước khi chạy): [benchmark/bonus_selection_criteria.md]"
             "(../../benchmark/bonus_selection_criteria.md).", "",
             "| Cấu hình | Hit@1 | Evidence Hit@3 | MRR@3 | Filter tuân thủ | Câu trượt |",
             "|---|---|---|---|---|---|"]
    for name, r in results.items():
        d = r["dev"]
        lines.append(f"| {name} | {d['hit1']}/{d['n']} | {d['hit3']}/{d['n']} | {d['mrr3']:.3f} | "
                     f"{d['filter_compliant']}/{d['filter_questions']} | {', '.join(d['misses']) or '-'} |")
    lines += ["", f"**Chọn:** `{chosen['name']}` (N = {chosen['N']}, k = {chosen['k']}, w = {chosen['w']}).", ""]
    return "\n".join(lines)


def render_final(summary: dict, traces: dict, questions: list[dict]) -> str:
    meta = summary["_meta"]
    lines = ["# Bonus: hybrid retrieval trên corpus 3 tài liệu", "",
             f"Embedding `{meta['embedding_model']}`; BM25 k1 = {meta['bm25']['k1']}, b = {meta['bm25']['b']}; "
             f"{meta['corpus_chunks']} chunk; {meta['questions']} câu; top-3; filter `chapter` cho câu có filter.", "",
             "| Cấu hình | Split | Hit@1 | Evidence Hit@3 | MRR@3 | Filter tuân thủ | Câu trượt |",
             "|---|---|---|---|---|---|---|"]
    for name in traces:
        for split in ("dev", "test"):
            r = summary[name][split]
            lines.append(f"| {name} | {split} | {r['hit1']}/{r['n']} | {r['hit3']}/{r['n']} | {r['mrr3']:.3f} | "
                         f"{r['filter_compliant']}/{r['filter_questions']} | {', '.join(r['misses']) or '-'} |")
    hybrid = next(n for n in traces if n.startswith("hybrid"))
    first = {name: {r["qid"]: r["first_hit_rank"] for r in rows} for name, rows in traces.items()}
    lines += ["", f"## Hạng của chunk đúng đầu tiên (toàn danh sách): dense vs BM25 vs {hybrid}", "",
              "| Câu | Split | Loại | dense | bm25 | hybrid | Hybrid so với dense |", "|---|---|---|---|---|---|---|"]
    for q in questions:
        d, b, h = (first[n][q["id"]] for n in ("dense", "bm25", hybrid))
        if d == h:
            verdict = "như nhau"
        elif h is not None and (d is None or h < d):
            verdict = "tốt hơn"
        else:
            verdict = "**xấu hơn**"
        lines.append(f"| {q['id']} | {q['split']} | {q['type']} | {d or '-'} | {b or '-'} | {h or '-'} | {verdict} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    commands = {
        "parse": run_parse,
        "verify": run_verify,
        "index": run_index,
        "evaluate": lambda: run_evaluate(include_test=False),
        "evaluate-test": lambda: run_evaluate(include_test=True),
    }
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()
