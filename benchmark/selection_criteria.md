# Tiêu chí chọn chiến lược (chốt trước khi chạy truy xuất)

Chốt ngày 2026-11-13, trước lần chạy `src.evaluate` đầu tiên. Không sửa sau khi xem kết quả.

1. Chỉ dùng **tập dev** (15 câu) để chọn.
2. Thứ tự ưu tiên:
   1. Evidence Hit@3 trên dev cao hơn.
   2. Nếu bằng nhau: Hit@1 trên dev cao hơn.
   3. Nếu vẫn bằng nhau: ít chunk hơn (ít tài nguyên lưu trữ và embedding hơn).
3. C chỉ khác B ở filter cho câu có filter; nếu C ≥ B theo tiêu chí trên thì chọn C, vì filter
   là đầu vào người dùng cung cấp trước và không làm hại câu không có filter.
4. Ghi lựa chọn vào `results/selection.md`, rồi mới chạy `python -m src.evaluate --include-test`
   **một lần**. Không chỉnh chiến lược dựa trên kết quả test.
