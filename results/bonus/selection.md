# Bonus: chọn cấu hình trên dev

Tiêu chí (chốt trước khi chạy): [benchmark/bonus_selection_criteria.md](../../benchmark/bonus_selection_criteria.md).

| Cấu hình | Hit@1 | Evidence Hit@3 | MRR@3 | Filter tuân thủ | Câu trượt |
|---|---|---|---|---|---|
| dense | 16/26 | 23/26 | 0.744 | 5/5 | q20, b06, b09 |
| bm25 | 19/26 | 23/26 | 0.801 | 5/5 | q03, q10, b09 |
| hybrid_N20_k10_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N20_k10_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N20_k30_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N20_k30_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N20_k60_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N20_k60_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N50_k10_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N50_k10_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N50_k30_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N50_k30_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N50_k60_w0.5 | 19/26 | 25/26 | 0.840 | 5/5 | b09 |
| hybrid_N50_k60_w1.0 | 20/26 | 25/26 | 0.865 | 5/5 | b09 |

**Chọn:** `hybrid_N20_k60_w1.0` (N = 20, k = 60, w = 1.0).
