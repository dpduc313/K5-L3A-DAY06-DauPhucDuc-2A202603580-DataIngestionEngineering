# Lựa chọn chiến lược (chỉ dựa trên dev, trước khi chạy test)

Áp dụng `benchmark/selection_criteria.md` cho kết quả dev (15 câu) trong `results/metrics.md`:

| Strategy | Evidence Hit@3 dev | Hit@1 dev | Chunk | Filter tuân thủ (dev) |
|---|---|---|---|---|
| A | 14/15 | 10/15 | 88 | 1/3 |
| B | 15/15 | 10/15 | 129 | 2/3 |
| C | 15/15 | 10/15 | 129 | 3/3 |

1. Evidence Hit@3: B = C (15/15) > A (14/15) → loại A.
2. Hit@1: B = C (10/15).
3. C ≥ B theo hai tiêu chí trên → **chọn C** (chunk theo heading + filter `chapter` cho trước).

Ghi chú trung thực: lần chạy dev đầu tiên báo q15 trượt ở cả A/B/C. Nguyên nhân là lỗi so
khớp: evidence chép từ Markdown của Docling có escape `warmup\_steps`, còn text chunk là
`warmup_steps`. Đã sửa `normalize` (bỏ escape Markdown, áp dụng như nhau cho mọi chiến
lược) rồi chạy lại dev trước khi chọn. Kết quả lần đầu: A 13/15, B 14/15, C 14/15
Evidence Hit@3; Hit@1 9/15 cho cả ba. Thứ tự và lựa chọn không đổi.

Test (5 câu) chạy một lần sau khi ghi file này.
