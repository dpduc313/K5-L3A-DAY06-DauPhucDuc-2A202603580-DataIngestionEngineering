# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** hai tài liệu khác ngôn ngữ và loại văn bản.
  - `aiayn`: bài báo "Attention Is All You Need" (arXiv 1706.03762), tiếng Anh. Tính trang 1–10; bỏ trang 11–12 (tài liệu tham khảo) và 13–15 (hình minh họa attention). Giấy phép: arXiv non-exclusive license; trang 1 ghi Google cho phép tái sử dụng bảng/hình khi ghi nguồn cho tác phẩm học thuật. Dùng cho bài lab học thuật phi thương mại.
  - `nd13`: Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân, bản scan ký số của Cổng TTĐT Chính phủ (19/04/2023), tiếng Việt. Tính trang 1–28 (Chương I–IV, Điều 1–44); bỏ trang 29–39 (Phụ lục biểu mẫu, chủ yếu ô trống). Văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả (Điều 15 Luật SHTT).
  - Tổng **38 trang nội dung**, không trang rỗng. Manifest (SHA-256, số ký tự mỗi trang): [data/manifest.json](../../data/manifest.json).
- **Chuẩn hóa, lỗi và giới hạn:**
  - nd13 không có lớp text, được OCR từng trang bằng vision reader của Perrier thành Markdown. Lần chạy đầu lỗi 401 (key OpenAI hết hạn) ở cả 39 trang; script ghi lỗi từng trang, không lưu gì, và chạy lại thành công sau khi thay key.
  - Tác giả đối chiếu ảnh scan với text OCR qua preview.
  - Vision model đánh dấu heading **không nhất quán** (`## Điều 30.`, `**Điều 33.**` hay dòng thường `Điều 31.`). 15 dòng heading trên 7 trang không phải heading Markdown, khiến chunk theo heading gộp Điều 30–31 (trang 24) và Điều 32–36 (trang 25). Lỗi được phát hiện ở cổng duyệt trước khi index; khắc phục bằng `promote_headings`, đưa các dòng `Chương`/`Mục`/`Điều N.` về `#`/`##`/`###` bằng regex.
  - Hàm `normalize` dùng chung cho chunk, trang và evidence: NFC, bỏ escape Markdown, nối từ gạch nối cuối dòng, bỏ ký tự định dạng, gộp khoảng trắng, chữ thường.
  - Với aiayn, 6/45 chunk heading và 3/35 chunk fixed không định vị được vị trí trong trang (do text Docling khác Markdown export ở bảng và công thức). Các chunk này lấy vị trí của chunk trước, nên metadata `section` của chúng có thể lệch.
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - Embedding: `embeddinggemma-2` qua Ollama 0.40.9 (local), 768 chiều, prefix `title: none | text: ` cho document và `task: search result | query: ` cho query (Perrier tự thêm).
  - Vector store: PostgreSQL 16 + pgvector 0.8.7, cosine, **exact search** (không dùng HNSW để filter không làm thiếu kết quả).
  - Lệnh chạy: xem [README.md](../../README.md).
  - Chi phí: OCR 39 trang 0,1645 USD; embedding và truy xuất 0 USD.
- **Metadata:**
  - Bắt buộc: `document_id`, `source`, `page`.
  - Bổ sung: `chapter` (chương tại điểm đầu chunk), `chapters` và `sections` (mọi chương/Điều chunk trải qua), `language` (`vi`/`en`), `document_type` (`decree`/`paper`).
  - `chapter`/`section` được trích tất định từ heading (Chương I–IV và Điều N của nd13; mục số 1–7 của aiayn), có mang sang trang sau, không dùng LLM.
  - Lý do chọn `chapter`: phạm vi lọc có ý nghĩa với người dùng ("theo Chương III…") và có giá trị phân biệt rõ.

## Cấu hình và benchmark

- **A / B / C:**
  - A: `fixed` của Perrier, cắt theo trang thành đoạn ~1.500 ký tự, overlap 200; 88 chunk, trung vị 1.197 ký tự.
  - B: `heading` (Docling HybridChunker), mỗi chunk nằm trong một heading và một trang, ≤384 token đo bằng tokenizer của embedding model; 129 chunk, trung vị 642 ký tự.
  - C: chunk và index giống hệt B. **Khác biệt duy nhất B–C:** với câu có `filter`, C thêm `WHERE 'Chương III' = ANY(chapters)`; câu không có filter thì C chạy như B.
  - Cùng corpus, cùng embedding, cùng store và metric.
- **Benchmark:** 20 câu, 15 dev / 5 test, chia theo cả tài liệu và loại câu (trực tiếp, diễn đạt lại, điều kiện/ngoại lệ, filter, chéo ngôn ngữ).
  - 5 câu có filter `chapter`, trong đó 2 câu thuộc test (q11, q16). Phạm vi filter do chính câu hỏi nêu ("Theo Chương I của nghị định…"), không lấy từ gold.
  - `src/verify_benchmark.py` kiểm tra mỗi `evidence_quote` là chuỗi con của trang gold sau chuẩn hóa, và giá trị filter tồn tại trong metadata. Cả 20 câu đều đạt.
  - Câu hỏi do AI soạn nháp; tác giả duyệt trước lần chạy đầu.
- **Tiêu chí chọn, chốt trước khi xem test** ([benchmark/selection_criteria.md](../../benchmark/selection_criteria.md)): trên dev ưu tiên Evidence Hit@3, rồi Hit@1, rồi số chunk; C được chọn nếu C ≥ B.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 10/15 | 14/15 | 88 | embed 93,9 s; truy xuất 0,12 s | 0 |
| A | test | 2/5 | 4/5 | 88 | | 0 |
| B | dev | 10/15 | 15/15 | 129 | embed 80,7 s; truy xuất 0,09 s | 0 |
| B | test | 5/5 | 5/5 | 129 | | 0 |
| C | dev | 10/15 | 15/15 | 129 | dùng index của B; truy xuất 0,08 s | 0 |
| C | test | 5/5 | 5/5 | 129 | | 0 |

Chi phí chung: OCR nd13 0,1645 USD, dùng cho cả ba chiến lược.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | _chờ chấm_ | _chờ chấm_ | dev 1/3, test 1/2 | _chờ chấm_ |
| B | _chờ chấm_ | _chờ chấm_ | dev 2/3, test 1/2 | _chờ chấm_ |
| C | _chờ chấm (chung với B)_ | _chờ chấm_ | dev 3/3, test 2/2 | _chờ chấm_ |

**Trace, nhãn và cách chọn mẫu:**
- Trace top-3 đầy đủ (text, score, metadata, hit): `results/A|B|C/trace.jsonl`. Chỉ số: [results/metrics.md](../../results/metrics.md).
- Nhãn thủ công: [results/labels/](../../results/labels/), tổng hợp bằng `python -m src.summarize_labels`.
- Coherence: 10 vị trí chọn tất định trước khi xem điểm, là giữa text của 5 trang đầu mỗi tài liệu ([benchmark/coherence_positions.json](../../benchmark/coherence_positions.json)).
- Metadata và grounding: 5 câu test × top-3 của mỗi chiến lược.

## Phân tích và kết luận

- **A–B (đổi cách chunk):** B hơn A 1 câu Evidence Hit@3 trên dev (15 vs 14) và 1 câu trên test (5 vs 4); Hit@1 trên test 5/5 so với 2/5. Hai ví dụ sai của A:
  - **q04 (test, nd13 trang 17, Điều 23):** A lấy đúng trang (`nd13-fixed-0031`, hạng 2) nhưng câu "chậm nhất 72 giờ… Trường hợp thông báo sau 72 giờ thì phải kèm theo lý do…" bị cắt qua hai chunk cố định, nên không chunk nào chứa trọn evidence. B giữ trọn khoản 1 Điều 23 trong một chunk.
  - **q17 (dev, aiayn trang 8):** top-1 của A là chunk trang 8 chứa chú thích "…TFLOPS for K80, K40, M40 and P100", không phải câu "Training took 3.5 days on 8 P100 GPUs". Hạng 2 là chunk trang 7 vắt qua 5 mục (từ "4 Why Self-Attention" đến "5.3 Optimizer"): chunk lớn trộn nhiều chủ đề làm loãng embedding.
- **B–C (chỉ thêm filter):** Hit@1 và Hit@3 không đổi trên mẫu này (các câu filter đều đã được B tìm đúng). Khác biệt nằm ở **phạm vi**: B trả về chunk Chương II cho câu hỏi về Chương III (q09, `nd13-heading-0027`, Điều 13) và Chương I (q11, `nd13-heading-0027` và `-0035`). C tuân thủ phạm vi 5/5 câu filter, B 3/5, A 2/5. Filter có lợi khi người dùng biết phạm vi; hạn chế là nếu người dùng nêu sai chương, C sẽ loại mất bằng chứng đúng.
- **Chiến lược chọn: C.** Đánh đổi: B/C có nhiều chunk hơn A (129 vs 88, nhiều lượt embed hơn) nhưng tổng token ít hơn (25.306 vs 27.688, vì không có overlap) và chunk giữ trọn Điều. Chunk theo heading phụ thuộc vào chất lượng heading: với OCR cần chuẩn hóa heading trước, nếu không B thoái hóa thành chunk gộp nhiều Điều. Điều kiện áp dụng: tài liệu có cấu trúc heading rõ (văn bản pháp luật, bài báo).
- **Hạn chế:**
  - Test chỉ 5 câu, nên chênh lệch 1 câu đã là 20%; không suy rộng ngoài corpus này.
  - Nhãn do chính tác giả chấm (nguy cơ thiên lệch); câu hỏi do AI soạn nháp.
  - **Lần chạy dev đầu** báo q15 trượt ở cả ba chiến lược. Nguyên nhân là lỗi so khớp (evidence chép từ Markdown của Docling có `warmup\_steps`, chunk có `warmup_steps`), không phải lỗi truy xuất. Đã sửa `normalize` trước khi chọn chiến lược, áp dụng như nhau cho cả ba; kết quả lần đầu và lần sửa đều ghi trong [results/selection.md](../../results/selection.md).
  - Thời gian đo một lần trên CPU máy cá nhân.
  - Manifest đếm ký tự bằng `normalize` trước lần sửa escape (sai lệch vài ký tự).
- **Nếu làm tiếp:**
  - Thêm hybrid search (dense + full-text) và reranker đa ngữ (`bge-reranker-v2-m3`) của Perrier làm dòng mở rộng.
  - Cho Self-query của Perrier tự suy filter rồi so với filter cho trước.
  - Mang heading sang trang sau ngay trong text chunk (hiện mới có trong metadata).
  - Tăng tập test.

## Công cụ AI

Dùng Claude Code để viết code pipeline, soạn nháp câu hỏi benchmark và báo cáo. Tác giả duyệt preview parse/chunk, duyệt câu hỏi và evidence, và tự chấm nhãn thủ công. Mọi số liệu lấy từ các lần chạy thật ghi trong `results/`.
