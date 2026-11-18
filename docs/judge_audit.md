# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có (`TP=24, FP=4, FN=6, TN=66`; fail rate 0.280 → Rogan-Gladen 0.300) | dùng (chỉ cho tiêu chí giọng điệu, sau khi cập nhật rubric) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không — `κ < 0.6` và `Recall < 0.7` (`TP=9, FP=0, FN=21, TN=70`; fail rate 0.090 → Rogan-Gladen 0.300) | loại (không được dùng làm gate) |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | `H-008` (`tone_ok`): `"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."` | PASS | FAIL | Người đúng | Judge đánh giá quá thoáng với kiểu xưng `"em"` + `"nha"`. **Sửa rubric:** bổ sung quy tắc cứng: mọi câu trả lời CS LogiX bắt buộc xưng `"LogiX"` – `"anh/chị"`, cấm xưng `"em"` hoặc dùng từ suồng sã (`"nha"`, `"nhé"`, `"check giúp"`). |
| 2 | `H-017` (`tone_ok`): `"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."` | PASS | FAIL | Người đúng | Có `"Dạ"` nhưng vẫn gọi khách là `"bạn ơi"` + `"nha"`. **Sửa rubric:** thêm ví dụ phản chứng (few-shot FAIL) để judge không chỉ chấm dựa vào từ khóa `"Dạ"` mà phải kiểm tra đại từ xưng hô chuẩn. |
| 3 | `H-029` (`tone_ok`): `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` | PASS | FAIL | Người đúng | Giọng ra lệnh/đuổi khách (`"không cần nhắn thêm"`), judge bị đánh lừa bởi `"Dạ, vui lòng"`. **Sửa rubric:** liệt kê rõ các cụm từ mang tính từ chối tiếp nhận/ra lệnh khách dừng liên hệ là FAIL dù có mở đầu lịch sự. |
| 4 | `H-042` (`tone_ok`): `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` | FAIL | PASS | Người đúng | Câu ngắn gọn, lịch sự, đủ thông tin nhưng judge phạt vì "thiếu lời xin lỗi". **Sửa rubric:** làm rõ tiêu chí `tone_ok` không bắt buộc câu trả lời hoàn tiền phải có lời xin lỗi dài dòng nếu đã lịch sự (`Dạ`...`ạ`) và đủ ý. |
| 5 | `H-051` (`tone_ok`): `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` | FAIL | PASS | Người đúng | Chính sách CS LogiX cho phép dùng từ `"refund"`, judge tự phạt vì chêm tiếng Anh. **Sửa rubric:** bổ sung danh sách thuật ngữ tiếng Anh được phép dùng (allowlist: `refund`, `voucher`, `order`) để giảm FP. |
| 6 | `H-063` (`tone_ok`): `"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."` | PASS | FAIL | Người đúng | Hứa `"sẽ hoàn thêm"` ngoài kết quả hệ thống nhưng giọng rất lễ phép nên judge cho PASS. **Sửa rubric:** thêm quy tắc FAIL khi câu trả lời cam kết khoản tiền/hành động bổ sung không có trong kết quả hệ thống. |
| 7 | `H-070` (`tone_ok`): `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"` | PASS | FAIL | Người đúng | Dùng emoji cười cợt (`😂😂`) trong ngữ cảnh khiếu nại hoàn tiền. **Sửa rubric:** cấm hoàn toàn emoji/biểu tượng cảm xúc trong phản hồi khiếu nại. |
| 8 | `H-081` (`tone_ok`): `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."` | FAIL | PASS | Judge đúng (nhãn người sai) | Người gán nhãn đọc nhầm ngữ cảnh ticket nên đánh nhầm. **Hành động:** sửa lại nhãn chuẩn trong tập hiệu chuẩn và rà soát double-annotation cho các ca biên; không sửa rubric cho ca này. |

## Kết luận
- **Tiêu chí bị loại — `helpful`:** không đạt ngưỡng tối thiểu (`κ = 0.375 < 0.6`, `Recall = 0.300 < 0.7`, dù `Precision = 1.000`). Dựa trên ma trận nhầm lẫn `TP = 9, FP = 0, FN = 21, TN = 70` (`n = 100`), judge bỏ sót tới **21/30 ca lỗi thật (70% lỗi lọt qua)**. Phân tích các ca `FN` cho thấy 18/21 ca là lỗi **sai số tiền so với ledger** (ví dụ `HL-015`, `HL-016`, `HL-028`, `HL-035`...), nhưng câu trả lời dài dòng và xin lỗi nhiều nên judge bị thiên kiến lịch sự/độ dài (*politeness/verbosity bias*) và không có quyền đọc ledger để đối chiếu. Hậu quả là tỷ lệ lỗi quan sát chỉ còn `0.090` (9%) trong khi tỷ lệ lỗi thực sau hiệu chỉnh Rogan-Gladen là `0.300` (30%) — nếu dùng làm gate sẽ cho lọt hàng loạt lỗi sai tiền nghiêm trọng (FM-08). Do đó loại bỏ `helpful` khỏi gate và chuyển kiểm tra số tiền hoàn sang **code grader** đối chiếu trực tiếp với ledger (M3).
- **Tiêu chí đạt — `tone_ok`:** đạt cả 3 sàn (`κ = 0.757 ≥ 0.6`, `P = 0.857 ≥ 0.8`, `R = 0.800 ≥ 0.7`; `TP = 24, FP = 4, FN = 6, TN = 66`; tỷ lệ lỗi `0.280 → 0.300` sau Rogan-Gladen), có thể dùng cho tiêu chí giọng điệu (không dùng để chấm tiền hay approval) sau khi cập nhật rubric theo bảng audit trên.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (`judge_tone_public.csv`, `judge_helpful_public.csv`); cần một tập held-out mới do người gắn nhãn độc lập sau khi sửa rubric để xác nhận không bị overfit vào các ca đã audit.
