"""Chạy các lệnh của Perrier (chat, nạp tài liệu, tạo Owner) trên DB của lab, để demo.

    python -m src.perrier owner                  # tạo Owner đăng nhập chat (hỏi mật khẩu, một lần)
    python -m src.perrier ingest data/raw/aiayn.pdf   # nạp qua Perrier: báo ước tính, hỏi trước
    python -m src.perrier library list           # tài liệu Perrier đang có
    python -m src.perrier web                    # chat của Perrier: http://127.0.0.1:7861/
    python -m src.perrier ask "câu hỏi" --no-log # hỏi thử một Turn từ dòng lệnh

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
}
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
    module = importlib.import_module(name)  # sau khi đặt biến môi trường: Perrier đọc lúc import
    if name == "perry.web":
        module.PORT = PORT
    sys.exit(module.main([*fixed, *sys.argv[2:]]))


if __name__ == "__main__":
    main()
