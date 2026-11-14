# Bonus: tiêu chí chọn cấu hình hybrid (chốt trước khi chạy truy xuất)

Chốt ngày 2026-11-14, trước lần chạy `python -m src.bonus evaluate` đầu tiên. Không sửa sau khi xem kết quả.

## Dữ liệu và câu hỏi

- Corpus bonus: chunk heading của aiayn và nd13 (giống chiến lược B/C) cộng chunk heading của sách
  "Deep Learning cơ bản" (`dlcb`). Chunk và metadata giữ nguyên giữa mọi cấu hình.
- Câu hỏi: 20 câu của benchmark chính và 16 câu mới về sách (`benchmark/bonus_questions.jsonl`).
  - Dev bonus = 15 câu dev chính + 11 câu dev mới (26 câu).
  - Test bonus = 5 câu test chính + 5 câu test mới (10 câu).
- 5 câu test chính đã được dùng để đánh giá chiến lược C (một lần) nhưng chưa dùng để chỉnh
  hybrid. 5 câu test về sách chưa từng được chạy.
- Câu hỏi về sách do Claude soạn và chưa được người duyệt (người làm bài chọn chạy luôn).

## Cấu hình

Mọi cấu hình đều top-3, áp dụng filter `chapter` cho câu có filter (như chiến lược C), và
cùng embedding (`embeddinggemma-2`).

- `dense`: baseline, giống chiến lược C nhưng trên corpus bonus (pgvector, cosine, exact).
- `bm25`: BM25 trên cùng chunk, tách từ theo âm tiết sau `normalize`, k1 = 1.5, b = 0.75.
  Không chỉnh k1, b.
- `hybrid`: gộp hai danh sách bằng weighted RRF:
  `score = 1/(k + rank_dense) + w * 1/(k + rank_bm25)`. Mỗi bên lấy N ứng viên đầu, sau filter.
  Lưới tham số (12 cấu hình):
  - N ∈ {20, 50}
  - k ∈ {10, 30, 60}
  - w ∈ {0.5, 1.0}

## Cách chọn (chỉ dùng dev bonus)

1. Evidence Hit@3 cao nhất.
2. Nếu bằng: Hit@1 cao hơn.
3. Nếu vẫn bằng: MRR@3 cao hơn (1/hạng của hit đầu tiên trong top-3, 0 nếu không có).
4. Nếu vẫn bằng: cấu hình gần mặc định nhất (N = 20, k = 60, w = 1.0), xét lần lượt w, k, N.

Sau khi chọn, ghi `results/bonus/selection.md`, rồi mới chạy test **một lần** cho `dense`,
`bm25` và hybrid đã chọn. Báo cáo cả các câu mà hybrid làm xấu hơn dense, trên dev và test.
