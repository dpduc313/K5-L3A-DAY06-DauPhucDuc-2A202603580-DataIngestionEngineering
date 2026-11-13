# Tổng hợp nhãn

Người chấm: metadata do tác giả chấm tay; 3 dòng được sửa theo bước đối chiếu tự động (text chunk có nằm trên trang ghi trong metadata, tiêu đề xuất hiện trong chunk có nằm trong `sections`), tác giả đồng ý. Coherence và grounding do Claude (LLM, qua Claude Code) chấm nháp theo thang và quy tắc ghi trong báo cáo, có lý do từng dòng; tác giả duyệt lại từng dòng và sửa 3 điểm coherence (pos04 A, pos08 A, pos10 B/C).

## Coherence (10 vị trí, thang 0-2)

| Strategy | n | Trung bình /2 | 0/1/2 |
|---|---|---|---|
| A | 10 | 1.30 | 0/7/3 |
| B/C | 10 | 1.90 | 0/1/9 |

Chưa chấm: 0 dòng.

## Metadata đủ và đúng (5 câu test × top-3)

| Strategy | Đủ và đúng (n/N) |
|---|---|
| A | 14/15 |
| B | 14/15 |
| C | 14/15 |

Chưa chấm: 0 dòng.

## Grounding (5 câu test, top-3, thang 0-2)

| Strategy | 0/1/2 (số câu) | Trung bình /2 |
|---|---|---|
| A | 1/0/4 | 1.60 |
| B | 0/0/5 | 2.00 |
| C | 0/0/5 | 2.00 |

Chưa chấm: 0 dòng.
