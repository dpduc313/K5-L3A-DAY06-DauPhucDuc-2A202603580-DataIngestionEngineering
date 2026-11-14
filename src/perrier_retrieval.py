"""Demo chat Perrier: mỗi lần tìm giữ đúng N chunk (mặc định 5) và hiện chúng trong chat.

    python -m src.perrier web                         # chat, kèm khối "Retrieval" trước câu trả lời
    python -m src.perrier retrieve "câu hỏi"          # chỉ bước retrieval, in 5 chunk, không gọi LLM
    python -m src.perrier retrieve "câu hỏi" --technique hybrid_search

Mỗi chunk hiện đủ để kiểm chứng: citation (tài liệu#trang), id chunk trong bảng `chunks`,
điểm (điểm reranker và hạng trước rerank, hoặc điểm RRF nếu không rerank), toàn văn.
Đối chiếu bằng cách mở PDF đúng trang, hoặc `SELECT * FROM chunks WHERE id = <id>`.

Vá Perrier lúc chạy, không sửa repo Perrier (đã ghim commit dd09dad):
- `perry.search.FINDINGS` và `perry.techniques.FINDINGS` = N. Có reranker thì reranker giữ
  N chunk tốt nhất trong pool 20; không có reranker (mặc định của lab, xem src/perrier.py)
  thì Hybrid search trả về N chunk theo điểm RRF.
- `perry.techniques.search`: cắt về N chunk nếu technique trả nhiều hơn, và ghi lại mỗi lần
  tìm (truy vấn, technique, chunk, điểm).
- `perry.threads.Thread.send`: xóa bản ghi khi bắt đầu một Turn.
- `perry.app.show`: chèn trước câu trả lời một tin nhắn thu gọn cho mỗi lần tìm.

Giới hạn: bản ghi dùng chung trong tiến trình, chỉ đúng khi một người hỏi tại một thời
điểm (đủ cho demo). Khối Retrieval không được lưu vào Thread: mở lại Thread sẽ không thấy.
Một Turn có thể có nhiều lần tìm (Knowledge Agent diễn đạt lại, tối đa 3), mỗi lần một khối.
Ít hơn N chunk chỉ xảy ra khi technique tìm được ít hơn N ứng viên.
"""

import argparse
import sys
import threading
from dataclasses import dataclass, replace

FINDINGS = 5


@dataclass(frozen=True)
class Search:
    """Một lần tìm trong Turn: truy vấn Knowledge Agent gửi, technique, và kết quả `Found`."""

    query: str
    technique: str
    found: object  # perry.techniques.Found


_lock = threading.Lock()
_searches: list[Search] = []


def take() -> list[Search]:
    """Các lần tìm đã ghi từ lần lấy trước, rồi xóa."""
    with _lock:
        taken = list(_searches)
        _searches.clear()
    return taken


def install(findings: int = FINDINGS) -> None:
    """Vá Perrier: giữ `findings` chunk mỗi lần tìm và ghi lại chúng để hiện trong chat."""
    from perry import app, search, techniques, threads

    search.FINDINGS = findings
    techniques.FINDINGS = findings

    original_search = techniques.search

    def recorded_search(technique, question):
        found = original_search(technique, question)
        if len(found.hits) > findings:
            # Không có reranker thì technique gộp nhiều lần tìm (ví dụ Question Decomposition)
            # có thể trả hơn N chunk: giữ N chunk đầu, đúng thứ tự của technique.
            found = replace(found, hits=found.hits[:findings])
        with _lock:
            _searches.append(Search(question, technique.label, found))
        return found

    techniques.search = recorded_search

    original_send = threads.Thread.send

    def send(self, *args, **kwargs):
        take()  # bỏ bản ghi còn sót từ Turn trước (ví dụ Turn lỗi)
        return original_send(self, *args, **kwargs)

    threads.Thread.send = send

    original_show = app.show

    def show(outcome, history):
        shown, *card = original_show(outcome, history)
        retrieval = [message(s, n) for n, s in enumerate(take(), start=1)]
        # Khối Retrieval nằm giữa câu hỏi và câu trả lời của Turn.
        return [*shown[: len(history)], *retrieval, *shown[len(history) :]], *card

    app.show = show


def _chunk_ids(hits) -> list[int | None]:
    """Id trong bảng `chunks` của từng hit (khớp tên tài liệu, trang và text)."""
    from perry import db

    sql = """SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
             WHERE d.name = %s AND c.page = %s AND c.text = %s ORDER BY c.id LIMIT 1"""
    with db.pool().connection() as conn:
        rows = [conn.execute(sql, (h.document, h.page, h.text)).fetchone() for h in hits]
    return [row["id"] if row else None for row in rows]


def _scores(found) -> list[str]:
    """Điểm của từng hit, theo thứ tự hit."""
    if found.reranked:
        # Ứng viên được giữ xếp đúng thứ tự của hits (cùng thứ tự điểm reranker).
        kept = [c for c in found.candidates if c.kept]
        pool = len(found.candidates)
        return [f"rerank {c.score:.3f}, hạng trước rerank {c.rank_before}/{pool}" for c in kept]
    return [f"điểm {hit.score:.4f}" for hit in found.hits]


def render(search: Search) -> str:
    """Một lần tìm dưới dạng Markdown: truy vấn, technique, rồi từng chunk nguyên văn."""
    found = search.found
    hits = found.hits
    how = ", reranked" if found.reranked else ""
    lines = [f"Truy vấn: `{search.query}`", f"Technique: {search.technique}{how}", ""]
    if found.problem:
        lines += [f"Cảnh báo: {found.problem}", ""]
    for rank, (hit, score, chunk_id) in enumerate(
        zip(hits, _scores(found), _chunk_ids(hits), strict=True), start=1
    ):
        where = f"chunk #{chunk_id}" if chunk_id is not None else "không tìm thấy id chunk"
        lines += [
            f"**{rank}. [{hit.citation}]** · {where} · {score} · {len(hit.text)} ký tự",
            "````text",
            hit.text,
            "````",
            "",
        ]
    return "\n".join(lines)


def message(search: Search, n: int) -> dict:
    """Tin nhắn thu gọn của Gradio cho lần tìm thứ `n`."""
    count = len(search.found.hits)
    return {
        "role": "assistant",
        "content": render(search),
        "metadata": {"title": f"Retrieval {n}: {count} chunk ({search.technique})", "status": "done"},
    }


def retrieve(argv: list[str]) -> int:
    """Chỉ chạy bước retrieval cho một câu hỏi và in các chunk (không gọi LLM trả lời)."""
    from perry import techniques

    parser = argparse.ArgumentParser(prog="python -m src.perrier retrieve")
    parser.add_argument("question")
    parser.add_argument("--technique", default="hybrid_search",
                        choices=[t.name for t in techniques.TECHNIQUES])
    args = parser.parse_args(argv)
    techniques.search(techniques.get(args.technique), args.question)
    sys.stdout.reconfigure(encoding="utf-8")
    for search in take():
        print(render(search))
    return 0
