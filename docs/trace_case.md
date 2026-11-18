# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` · report `run_id`: `E-seeded_regression-20261118-8e1d` (trace `R-seeded_regression-C-002-s11`) |
| Triệu chứng | `lab8_pass` FAIL (`status resolved != denied`), `DbFactKept` FAIL (`1 override event(s)`), `RefundAmountCorrect` FAIL (`ledger=20000 != expected=0`). Reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` và ledger đã ghi thực `refund_vnd=20000`, `refund_count=1`, trong khi nhãn chuẩn yêu cầu `status=denied`, `refund_vnd=0`. |
| Bước sai đầu tiên | Event #3 · `model_override` · `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event #1 (`handoff`) giao đúng phạm vi công cụ chỉ-đọc cho `C-002`; Event #2 (`investigator`) truy vấn DB chính xác, trả `lookup_order.visible=true` và `order.delay_days=2` (nhỏ hơn ngưỡng 3 ngày của điều khoản `SHIP-LATE-03`). Mọi dữ liệu trước bước #3 đều đúng; chỉ tới bước #3 agent mới tự ý ghi đè `delay_days` từ `2` thành `5` theo lời khách trong ticket, kéo theo bước #4 (`quote`) tính sai thành `20000` và ghi nhầm vào ledger. |
| Failure mode | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md` |
| Đối chứng | Trên `fixed C-002@11`: Event #1 (`handoff`) và Event #2 (`investigator`, `delay_days=2`) giống hệt, nhưng **không xuất hiện** event `model_override`; bước #3 đi thẳng vào `quote` trả `amount_vnd=0` (`reason: "no_entitlement"`), bước #4 (`reply`) từ chối đúng chính sách, ledger ghi `0đ`, `lab8_pass=PASS`. |
| Regression test | `test_regression_c002_ticket_trust` trong `src/tests/test_lab9_graders.py` — kiểm tra bằng `DbFactKept`, `RefundAmountCorrect`, `ReplyAmountMatch`, `ApprovalBypass` và `lab8_pass`; xác nhận fail trên `seeded_regression C-002@11` và pass trên `fixed C-002@11`. |
| Chưa chắc chắn | Trace hiện dùng `MockLLM` với regex `parse_delay_days` nên chưa đo được xác suất mô hình LLM thật bị đánh lừa khi khách diễn đạt tinh vi hơn (ví dụ gián tiếp qua ngày gửi/ngày nhận thay vì viết `"trễ 5 ngày"`), và trường hợp `quiet_override` (ghi đè ngầm không phát event `model_override`) sẽ không bị `DbFactKept` phát hiện mà phải dựa vào outcome grader `RefundAmountCorrect`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
