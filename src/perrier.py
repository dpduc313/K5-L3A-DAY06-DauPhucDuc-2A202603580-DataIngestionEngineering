"""Chạy các lệnh của Perrier (chat, nạp tài liệu, tạo Owner) trên DB của lab, để demo.

    python -m src.perrier owner                  # tạo Owner đăng nhập chat (hỏi mật khẩu, một lần)
    python -m src.perrier ingest data/raw/aiayn.pdf   # nạp qua Perrier: báo ước tính, hỏi trước
    python -m src.perrier library list           # tài liệu Perrier đang có
    python -m src.perrier web                    # chat của Perrier: http://127.0.0.1:7861/
    python -m src.perrier ask "câu hỏi" --no-log # hỏi thử một Turn từ dòng lệnh
    python -m src.perrier retrieve "câu hỏi"     # chỉ bước retrieval: in 5 chunk, không gọi LLM
    python -m src.perrier ingest-ocr             # nạp lại nd13 vào Perrier từ OCR cache của lab

Với `web`, `ask` và `retrieve`, mỗi lần tìm giữ đúng 5 chunk; `web` hiện 5 chunk đó trong chat
trước câu trả lời để kiểm chứng (xem src/perrier_retrieval.py).

Perrier lưu tài liệu trong bảng `documents`/`chunks` của chính nó (cùng DB lab, tách khỏi
`lab_chunks` dùng cho benchmark A/B/C). Chat vì vậy trả lời bằng pipeline của Perrier
(hybrid search + Retrieval Techniques + rerank), không phải chiến lược C của lab.

Mặc định khác Perrier gốc, để không đụng Perry đang chạy trên máy:
- cổng 7861 (7860 thường đã có Perry);
- PERRY_APP_DATA_DIR riêng (index ColBERT, chart), không dùng %APPDATA%\\Perry.
"""

import importlib
import os
import sys
from pathlib import Path

from src import lab_config as C  # nạp .env của lab, DATABASE_URL lab, PERRIER_DIR vào sys.path

COMMANDS = {
    "owner": ("perry.users", ["create-owner"]),
    "ingest": ("perry.ingest", []),
    "library": ("perry.library", []),
    "web": ("perry.web", []),
    "ask": ("scripts.ask", []),
    "retrieve": ("src.perrier_retrieval", []),
    "ingest-ocr": ("perry.ingest", []),
}
# Các lệnh có bước retrieval: giữ 5 chunk mỗi lần tìm (src/perrier_retrieval.py).
RETRIEVING = {"web", "ask", "retrieve"}
PORT = int(os.getenv("LAB_PERRIER_PORT", "7861"))


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    name, fixed = COMMANDS[sys.argv[1]]
    os.environ.setdefault(
        "PERRY_APP_DATA_DIR",
        str(Path(os.environ["APPDATA"]) / "Perrier-Day06")
        if sys.platform == "win32"
        else str(C.ROOT / ".perrier-data"),
    )
    # Reranker mặc định của Perrier (ms-marco-MiniLM, chỉ tiếng Anh) làm rơi evidence tiếng
    # Việt khỏi top-5: Evidence Hit@5 trên 20 câu benchmark là 17/20, tắt reranker là 20/20
    # (q03, q09, q10 rơi). Tắt cho demo lab; đặt PERRY_RERANK_MODEL trong .env để bật lại.
    # " " chứ không phải "": trên Windows, gán chuỗi rỗng sẽ xóa biến môi trường.
    os.environ.setdefault("PERRY_RERANK_MODEL", " ")
    module = importlib.import_module(name)  # sau khi đặt biến môi trường: Perrier đọc lúc import
    if sys.argv[1] in RETRIEVING:
        from src import perrier_retrieval

        perrier_retrieval.install()
    if name == "perry.web":
        module.PORT = PORT
    if name == "src.perrier_retrieval":
        sys.exit(module.retrieve(sys.argv[2:]))
    if sys.argv[1] == "ingest-ocr":
        sys.exit(ingest_ocr())
    sys.exit(module.main([*fixed, *sys.argv[2:]]))


def ingest_ocr(doc_id: str = "nd13") -> int:
    """Nạp lại `doc_id` (bản scan) vào bảng của Perrier từ OCR cache của lab, đủ mọi trang.

    Nạp qua giao diện chat gọi vision model lại từng trang; trang nào lỗi bị bỏ qua và tài
    liệu được lưu thiếu trang (lần nạp nd13 ngày 2026-11-13 chỉ còn 21/39 trang). Lệnh này
    dùng chính text vision model đã đọc (data/ocr/<doc_id>/page-NN.md, đã duyệt qua preview),
    chuẩn hóa heading như lab, chunk `heading` như Perrier, embed local: không tốn phí.
    Thay tài liệu cùng tên trong Perrier; không đụng `lab_chunks` của benchmark.
    """
    from perry import documents, ingest

    from src.parse_docs import ocr_dir, promote_headings

    path = C.RAW / C.DOCUMENTS[doc_id]["file"]
    cached = sorted(ocr_dir(doc_id).glob("page-*.md"))
    chunks = [
        chunk
        for file in cached
        for chunk in documents.page_chunks(
            int(file.stem.split("-")[1]), promote_headings(file.read_text("utf-8")), "heading"
        )
    ]
    read = ingest.ReadDocument(
        path=path,
        name=path.name,
        content_hash=documents.content_hash(path),
        reader="vision",
        chunking="heading",
        chunks=tuple(chunks),
    )
    print(f"{read.name}: {len(cached)} trang từ cache, {len(chunks)} chunk; đang embed và lưu…")
    print(ingest.store(read).describe())
    return 0


if __name__ == "__main__":
    main()
