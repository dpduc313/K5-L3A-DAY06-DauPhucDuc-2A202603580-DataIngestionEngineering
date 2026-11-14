# Day 06 · Data Ingestion Engineering — bài nộp

Biến hai tài liệu thành kho tri thức truy xuất được bằng pgvector, so sánh ba chiến lược dữ
liệu A/B/C trên cùng benchmark 20 câu. Đề bài gốc: [ASSIGNMENT.md](ASSIGNMENT.md).

Pipeline **tái sử dụng [Perrier](https://github.com/dpduc313/perrier)** (trợ lý đa agent
của tác giả) cho phần đọc tài liệu, chunking và embedding. Code của lab nằm ở [src/](src/).

| | |
|---|---|
| Corpus | `aiayn.pdf` (Attention Is All You Need, trang 1–10) và `nd13.pdf` (Nghị định 13/2023/NĐ-CP, bản scan, trang 1–28): **38 trang nội dung**, xem [data/manifest.json](data/manifest.json) |
| Đọc | aiayn: Docling (layout model, CPU). nd13: vision reader của Perrier (`gpt-5.4-mini`), OCR từng trang thành Markdown, cache trong [data/ocr/nd13/](data/ocr/nd13/) |
| Chunk | A: cố định 1.500 ký tự, overlap 200. B: theo heading (Chương/Mục/Điều, mục bài báo), ≤384 token, không vắt trang. C: B + filter `chapter` |
| Embedding | `embeddinggemma-2` qua Ollama (local, 768 chiều, $0) |
| Vector store | PostgreSQL 16 + pgvector 0.8.7 (`starter/docker-compose.yml`), cosine, exact search |
| Benchmark | [benchmark/questions.jsonl](benchmark/questions.jsonl): 20 câu, 15 dev / 5 test, 5 câu filter (2 test), 2 câu hỏi chéo ngôn ngữ |
| Kết quả | [results/metrics.md](results/metrics.md), trace trong `results/A|B|C/trace.jsonl`, nhãn thủ công trong [results/labels/](results/labels/) |

## Cài đặt

Cần Docker, [Ollama](https://ollama.com) và một bản checkout Perrier có môi trường `uv`.

```
git clone https://github.com/dpduc313/perrier.git
cd perrier
git checkout dd09dadb196ee96f074a3dae9fa841ad672a0d98   # commit Perrier mà lab dùng (nhánh docling-chunking)
uv sync
ollama pull embeddinggemma-2
```

Trong repo lab: chép `.env.example` thành `.env`, điền `OPENAI_API_KEY` (chỉ cần khi OCR lại
nd13) và `PERRIER_DIR` (đường dẫn tới bản checkout Perrier). Bật database:

```
docker compose -f starter/docker-compose.yml up -d
```

## Chạy

Mọi lệnh chạy bằng Python trong môi trường của Perrier, từ thư mục gốc của repo lab
(`PY=<PERRIER_DIR>/.venv/Scripts/python.exe` trên Windows, `.../.venv/bin/python` nơi khác):

```
$PY -m src.parse_docs ocr        # chỉ khi chưa có data/ocr/nd13/ (39 trang, ~0,16 USD)
$PY -m src.parse_docs parse      # trang + chunk A/B -> data/parsed/, data/manifest.json
$PY -m src.parse_docs preview    # results/preview.html: ảnh trang | text | chunk A | chunk B
$PY -m src.index --approve <fingerprint trong preview>   # cổng duyệt rồi mới index
$PY -m src.verify_benchmark      # evidence phải nằm đúng trang gold
$PY -m src.coherence             # 10 vị trí chấm coherence (chọn trước khi xem điểm)
$PY -m src.evaluate              # dev
$PY -m src.evaluate --include-test   # chỉ sau khi có results/selection.md
$PY -m src.summarize_labels      # tổng hợp nhãn thủ công -> results/labels_summary.md
```

**Cổng duyệt trước khi index:** `index` chỉ nạp đúng bản parse đã xem trong preview
(fingerprint SHA-256 của các file chunk). Nạp lại cùng phiên bản không tạo bản trùng: chunk
có hash không đổi được bỏ qua, chunk đổi thì embed lại, chunk không còn thì bị xóa
(minh chứng trong [results/index_log.jsonl](results/index_log.jsonl)).

## Bonus: hybrid retrieval trên corpus 3 tài liệu

Thêm sách "Deep Learning cơ bản" (`data/raw/dlcb.pdf`), rồi so sánh dense, BM25 và hybrid (RRF).
Kết quả và phân tích nằm ở mục Bonus của báo cáo cá nhân.

```
$PY -m src.bonus parse           # sách -> data/bonus/ (trang, 504 chunk heading, manifest)
$PY -m src.bonus verify          # evidence của 36 câu (20 chính + 16 về sách) nằm đúng trang gold
$PY -m src.bonus index           # embed vào lab_chunks với chunking 'heading-dlcb'
$PY -m src.bonus evaluate        # dev: dense, bm25, 12 cấu hình hybrid -> results/bonus/selection.md
$PY -m src.bonus evaluate-test   # chạy một lần: dense, bm25, hybrid đã chọn -> results/bonus/metrics.md
```

Tiêu chí chọn tham số được chốt trước khi chạy: [benchmark/bonus_selection_criteria.md](benchmark/bonus_selection_criteria.md).
Chunk của sách dùng nhãn riêng, nên `src.evaluate` và các kết quả chính không bị ảnh hưởng.

## Demo trên giao diện chat của Perry

Cùng một quy trình nạp → parse → duyệt → index, nhưng thao tác trên giao diện chat của Perry:

```
$PY -m src.perrier owner     # một lần: tạo tài khoản Owner (chỉ Owner được nạp tài liệu)
$PY -m src.perrier web       # http://127.0.0.1:7861/
```

1. Ở sidebar, mục **Documents**, chọn **Reader** (`docling` cho aiayn, `vision` cho nd13 bản
   scan) và **Chunking Strategy** (`heading` hoặc `fixed`), rồi thả PDF vào **Upload**.
2. Perry báo ước tính token và chi phí. Bấm **Read for Review**: Perry đọc và chunk tài liệu,
   **chưa ghi gì vào DB**. Reader `vision` tốn tiền ngay ở bước này; Docling chạy trên CPU,
   khoảng 6 phút với aiayn.
3. Khung **Review before indexing** mở phía trên khung chat:
   - Bảng tóm tắt: số trang, số chunk, độ dài trung vị, số token lớn nhất, trang đọc lỗi,
     fingerprint.
   - Chọn từng trang, kể cả trang không ra chunk nào. Ảnh trang nằm cạnh các chunk của trang,
     đúng như text sẽ được embed.
4. Bấm **Approve and index** để embed (EmbeddingGemma 2) và ghi vào pgvector, hoặc
   **Discard** để bỏ, không ghi gì. Sau khi duyệt, có thể hỏi Perry ngay trong khung chat, câu
   trả lời có trích dẫn trang.

Giao diện ghi vào bảng `documents`/`chunks` của Perrier, những bảng mà chat tìm kiếm, trên
cùng DB với lab. Benchmark A/B/C dùng bảng `lab_chunks` riêng, nên demo không làm thay đổi
kết quả benchmark.

**5 chunk kiểm chứng được.** Với `web`, mỗi lần tìm giữ đúng 5 chunk. Trước câu trả lời, chat
hiện một khối thu gọn "Retrieval N: 5 chunk". Mỗi chunk có citation (`nd13.pdf#page=17`), id
trong bảng `chunks`, điểm và toàn văn. Để đối chiếu, mở PDF đúng trang hoặc chạy
`SELECT * FROM chunks WHERE id = …`. Muốn xem riêng bước retrieval, không gọi LLM:

```
$PY -m src.perrier retrieve "Việc xóa dữ liệu cá nhân phải thực hiện trong bao lâu?"
```

- Reranker mặc định của Perrier (`ms-marco-MiniLM`, chỉ tiếng Anh) bị tắt cho các lệnh của
  lab. Trên 20 câu benchmark, Evidence Hit@5 là 17/20 khi bật và 20/20 khi tắt. Đặt
  `PERRY_RERANK_MODEL` trong `.env` để bật lại.
- Nạp nd13 qua giao diện có thể thiếu trang nếu vision model đọc lỗi (lần nạp ngày
  2026-11-13 chỉ còn 21/39 trang). Nạp lại từ OCR cache của lab, không tốn phí:
  `$PY -m src.perrier ingest-ocr`.

## Chi phí và thời gian (lần chạy 2026-11-13)

| Bước | Thời gian | Chi phí |
|---|---|---|
| OCR nd13, 39 trang (`gpt-5.4-mini-2026-03-17`) | vài phút | 0,1645 USD (Usage Ledger) |
| Parse aiayn bằng Docling (CPU) | ~63 s | 0 |
| Embed 88 chunk A / 129 chunk B | 93,9 s / 80,7 s | 0 (local) |
| Truy xuất 20 câu × 3 chiến lược | < 0,2 s mỗi chiến lược | 0 |

Phiên bản: docling 2.150.0, pymupdf 1.28.2, psycopg 3.3.6, pgvector (Python) 0.5.0,
Ollama 0.40.9.
