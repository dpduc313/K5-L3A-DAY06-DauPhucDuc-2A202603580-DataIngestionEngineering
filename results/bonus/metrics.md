# Bonus: hybrid retrieval trên corpus 3 tài liệu

Embedding `embeddinggemma-2`; BM25 k1 = 1.5, b = 0.75; 633 chunk; 36 câu; top-3; filter `chapter` cho câu có filter.

| Cấu hình | Split | Hit@1 | Evidence Hit@3 | MRR@3 | Filter tuân thủ | Câu trượt |
|---|---|---|---|---|---|---|
| dense | dev | 16/26 | 23/26 | 0.744 | 5/5 | q20, b06, b09 |
| dense | test | 7/10 | 9/10 | 0.783 | 3/3 | b13 |
| bm25 | dev | 19/26 | 23/26 | 0.801 | 5/5 | q03, q10, b09 |
| bm25 | test | 6/10 | 7/10 | 0.633 | 3/3 | b13, b14, b15 |
| hybrid_N20_k60_w1.0 | dev | 20/26 | 25/26 | 0.865 | 5/5 | b09 |
| hybrid_N20_k60_w1.0 | test | 7/10 | 9/10 | 0.767 | 3/3 | b13 |

## Hạng của chunk đúng đầu tiên (toàn danh sách): dense vs BM25 vs hybrid_N20_k60_w1.0

| Câu | Split | Loại | dense | bm25 | hybrid | Hybrid so với dense |
|---|---|---|---|---|---|---|
| q01 | dev | truc_tiep | 2 | 1 | 2 | như nhau |
| q02 | dev | dieu_kien | 1 | 1 | 1 | như nhau |
| q03 | dev | dien_dat_lai | 1 | 6 | 2 | **xấu hơn** |
| q04 | test | dieu_kien | 1 | 1 | 1 | như nhau |
| q05 | dev | truc_tiep | 1 | 3 | 1 | như nhau |
| q06 | dev | filter | 1 | 1 | 1 | như nhau |
| q07 | dev | dieu_kien | 1 | 1 | 1 | như nhau |
| q08 | test | dien_dat_lai | 1 | 1 | 1 | như nhau |
| q09 | dev | filter | 1 | 2 | 2 | **xấu hơn** |
| q10 | dev | truc_tiep | 2 | 6 | 2 | như nhau |
| q11 | test | filter | 1 | 1 | 1 | như nhau |
| q12 | dev | dien_dat_lai | 1 | 1 | 1 | như nhau |
| q13 | dev | truc_tiep | 2 | 1 | 1 | tốt hơn |
| q14 | dev | truc_tiep | 1 | 1 | 1 | như nhau |
| q15 | dev | filter | 1 | 1 | 1 | như nhau |
| q16 | test | filter | 1 | 1 | 1 | như nhau |
| q17 | dev | dien_dat_lai | 3 | 1 | 1 | tốt hơn |
| q18 | dev | truc_tiep | 1 | 1 | 1 | như nhau |
| q19 | test | cheo_ngon_ngu | 1 | 3 | 1 | như nhau |
| q20 | dev | cheo_ngon_ngu | 4 | 2 | 2 | tốt hơn |
| b01 | dev | truc_tiep | 1 | 1 | 1 | như nhau |
| b02 | dev | dieu_kien | 1 | 1 | 1 | như nhau |
| b03 | dev | so_hieu | 1 | 1 | 1 | như nhau |
| b04 | dev | dien_dat_lai | 1 | 1 | 1 | như nhau |
| b05 | dev | filter | 2 | 1 | 1 | tốt hơn |
| b06 | dev | truc_tiep | 4 | 1 | 1 | tốt hơn |
| b07 | dev | cheo_ngon_ngu | 2 | 2 | 1 | tốt hơn |
| b08 | dev | filter | 1 | 1 | 1 | như nhau |
| b09 | dev | dien_dat_lai | - | - | - | như nhau |
| b10 | dev | truc_tiep | 2 | 1 | 1 | tốt hơn |
| b11 | dev | truc_tiep | 1 | 1 | 1 | như nhau |
| b12 | test | dien_dat_lai | 1 | 1 | 1 | như nhau |
| b13 | test | filter | 5 | 4 | 4 | tốt hơn |
| b14 | test | so_hieu | 3 | 6 | 3 | như nhau |
| b15 | test | cheo_ngon_ngu | 1 | 18 | 3 | **xấu hơn** |
| b16 | test | dieu_kien | 2 | 1 | 1 | tốt hơn |
