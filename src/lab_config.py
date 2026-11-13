"""Cấu hình chung của lab: đường dẫn, biến môi trường và cách nạp Perrier.

Lab tái sử dụng Perrier (https://github.com/dpduc313/perrier) cho phần đọc tài liệu
(Docling, vision reader), chunking (heading/fixed) và embedding (EmbeddingGemma 2 qua
Ollama). Perrier đọc biến môi trường lúc import, nên module này phải được import TRƯỚC
mọi `import perry`.
"""

import os
import sys
import unicodedata
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Postgres + pgvector riêng của lab (starter/docker-compose.yml), không dùng DB của Perrier.
os.environ.setdefault(
    "DATABASE_URL", "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab"
)
DATABASE_URL = os.environ["DATABASE_URL"]

PERRIER_DIR = Path(
    os.getenv("PERRIER_DIR", ROOT.parents[3] / "WORK" / "Internship" / "Projects" / "Perrier")
)
if not (PERRIER_DIR / "perry" / "__init__.py").exists():
    sys.exit(f"Không tìm thấy Perrier ở {PERRIER_DIR}. Đặt PERRIER_DIR trong .env.")
sys.path.insert(0, str(PERRIER_DIR))

DATA = ROOT / "data"
RAW = DATA / "raw"
OCR_CACHE = DATA / "ocr"
PARSED = DATA / "parsed"
BENCHMARK = ROOT / "benchmark"
RESULTS = ROOT / "results"
LABELS = RESULTS / "labels"

# Tài liệu trong corpus và các trang được tính (xem data/manifest.json).
DOCUMENTS = {
    "aiayn": {
        "file": "aiayn.pdf",
        "reader": "docling",
        "language": "en",
        "document_type": "paper",
        # Trang 11-12 là tài liệu tham khảo, 13-15 là hình minh họa attention: không tính.
        "pages": list(range(1, 11)),
    },
    "nd13": {
        "file": "nd13.pdf",
        "reader": "vision",  # bản scan: không có lớp text
        "language": "vi",
        "document_type": "decree",
        # Trang 29-39 là Phụ lục biểu mẫu (chủ yếu ô trống, dòng chấm): không tính.
        "pages": list(range(1, 29)),
    },
}

# Ba chiến lược. C dùng lại chunk của B, chỉ thêm filter cho câu hỏi có filter.
STRATEGIES = {
    "A": {"chunking": "fixed", "filter": False},
    "B": {"chunking": "heading", "filter": False},
    "C": {"chunking": "heading", "filter": True},
}
TOP_K = 3


def normalize(text: str) -> str:
    """Chuẩn hóa dùng chung cho chunk, trang và evidence: NFC, nối từ bị gạch nối cuối
    dòng, bỏ định dạng Markdown nhấn mạnh, gộp khoảng trắng, chữ thường."""
    text = unicodedata.normalize("NFC", text)
    # Docling xuất Markdown có escape (`warmup\_steps`), còn text chunk thì không.
    text = re.sub(r"\\([_*#\[\]()<>`|\\])", r"\1", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[*_`#|]+", " ", text)
    return " ".join(text.split()).casefold()
