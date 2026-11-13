# Kết quả truy xuất

Embedding: `embeddinggemma-2` (Ollama, local, $0). pgvector, cosine, exact search, top-3. 20 câu hỏi.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Đúng trang @3 (n/N) | Filter tuân thủ | Chunk | Thời gian truy xuất |
|---|---|---|---|---|---|---|---|
| A | dev | 10/15 | 14/15 | 15/15 | 1/3 | 88 | 0.12 s |
| A | test | 2/5 | 4/5 | 5/5 | 1/2 | 88 | 0.12 s |
| B | dev | 10/15 | 15/15 | 15/15 | 2/3 | 129 | 0.09 s |
| B | test | 5/5 | 5/5 | 5/5 | 1/2 | 129 | 0.09 s |
| C | dev | 10/15 | 15/15 | 15/15 | 3/3 | 129 | 0.08 s |
| C | test | 5/5 | 5/5 | 5/5 | 2/2 | 129 | 0.08 s |

## Câu trượt Evidence Hit@3

- **A / dev**: q17 (đúng trang nhưng thiếu evidence: q17)
- **A / test**: q04 (đúng trang nhưng thiếu evidence: q04)
- **B / dev**: không có (đúng trang nhưng thiếu evidence: không có)
- **B / test**: không có (đúng trang nhưng thiếu evidence: không có)
- **C / dev**: không có (đúng trang nhưng thiếu evidence: không có)
- **C / test**: không có (đúng trang nhưng thiếu evidence: không có)
