# 08 — Hash mật khẩu

## Vấn đề

Để kiểm tra mật khẩu, server phải so cái bạn gõ với cái nó đã lưu. Cách ngây thơ:

```
users
  email                  password
  you@example.com        hunter2          ← chữ thường
```

Giờ bất kỳ ai đọc được bảng đó — một lỗ SQL injection, một bản backup bị trộm, một
laptop thất lạc, một nhà thầu tò mò — đều có mật khẩu của bạn. Và vì người ta dùng
lại mật khẩu, họ có luôn email và ngân hàng của bạn.

Nên yêu cầu ở đây vừa lạ vừa rất cụ thể: **server phải xác minh được mật khẩu mà
không bao giờ có khả năng biết nó.**

## Ý tưởng

**Hash** là một hàm một chiều. Xuôi thì dễ, ngược thì bất khả thi về mặt tính
toán:

```
  hash("hunter2")  →  8b2c1f4e9a…      (nhanh)
  8b2c1f4e9a…      →  ???              (không khả thi)
```

Lưu cái hash. Khi đăng nhập, hash cái vừa gõ rồi so hai hash. Database bị trộm chỉ
cho ra hash, mà hash không phải mật khẩu.

Đó là hình dạng chung. Để làm đúng cần thêm hai ý nữa.

## Ý 1 — Salt

Chỉ hash thôi vẫn hở. Hàm hash là tất định, nên `hash("password123")` cho ra *cùng
một giá trị* với mọi người trên đời chọn mật khẩu đó. Kẻ tấn công tính trước hash
của mười triệu mật khẩu phổ biến một lần (**rainbow table**) rồi tra ngược bất kỳ
database nào ngay lập tức.

**Salt** là một giá trị ngẫu nhiên lưu kèm, trộn vào trước khi hash:

```
  alice:  hash("hunter2" + "x7Kp2m")  →  a1b2c3…   hash
  bob:    hash("hunter2" + "9zQr4T")  →  f4e5d6…   khác nhau
```

Giờ bảng tính sẵn thành vô dụng — kẻ tấn công phải làm lại toàn bộ công sức **cho
từng người dùng**. Mật khẩu giống nhau không còn trông giống nhau, nên cũng chặn
luôn kiểu phân tích "400 tài khoản này dùng chung một mật khẩu".

Bạn không tự quản salt: argon2 và bcrypt tự sinh một salt cho mỗi mật khẩu và nhúng
nó vào chuỗi kết quả, kèm cả tham số đã dùng.

## Ý 2 — Chậm, một cách cố ý

Đây là ý phản trực giác, và là lý do thiết kế ngây thơ vẫn hỏng.

Salt chặn *tính trước*. Nó không chặn việc kẻ tấn công lấy hash đã trộm rồi đoán,
từng người một. Mà phần cứng hiện đại đoán rất nhanh:

| Thuật toán | Lượt đoán/giây (GPU phổ thông, bậc độ lớn) |
|---|---|
| MD5 | ~100.000.000.000 |
| SHA-256 | ~10.000.000.000 |
| bcrypt (cost 12) | ~10.000 |
| argon2id (đã chỉnh) | ~1.000 |

SHA-256 **rất giỏi** việc nó được thiết kế để làm — kiểm tra một file có bị đổi
không — và mục tiêu thiết kế đó là *tốc độ*. Với mật khẩu, tốc độ chính là lỗ hổng.

Nên hash mật khẩu được xây để **cố tình chậm**, và loại tốt còn **ngốn bộ nhớ**
(memory-hard): mỗi lần tính cần một vùng RAM lớn. GPU nhanh nhờ hàng nghìn nhân
nhỏ với rất ít bộ nhớ mỗi nhân, nên một hàm ngốn bộ nhớ làm sập lợi thế đó. Đấy là
ý tưởng cốt lõi của argon2.

```
  Kẻ tấn công có 8 hash trộm được, đoán mật khẩu 10 ký tự:

  SHA-256      →  vài giờ
  bcrypt       →  vài thế kỷ
  argon2id     →  vài thế kỷ, và GPU không giúp được gì
```

Cái giá với *bạn* là ~100 mili giây mỗi lần đăng nhập. Cái giá với kẻ tấn công là
toàn bộ chiến lược của họ. **Biện pháp bảo mật tốt thường bất đối xứng như vậy** —
khi một biện pháp làm bạn đau ngang kẻ tấn công, thường đó là biện pháp sai.

### Chọn cái nào

| | Dùng không? |
|---|---|
| **argon2id** | ✅ Khuyến nghị hiện tại. Memory-hard. Python: `argon2-cffi` |
| **bcrypt** | ✅ Ổn. Cũ hơn, đã qua thử lửa, có ở khắp nơi |
| **scrypt** | ⚠️ Chấp nhận được |
| **PBKDF2** | ⚠️ Chấp nhận được nếu bị quy định bắt buộc |
| **SHA-256 / SHA-3** | ❌ Sai công cụ. Quá nhanh |
| **MD5 / SHA-1** | ❌❌ Còn hỏng vì nhiều lý do khác |

## Giá trị lưu ra trông thế nào

```
$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG
└──┬───┘ └─┬─┘ └──────┬──────┘ └───┬────┘ └──────────────┬──────────────┘
thuật toán  phiên bản  tham số      salt                  hash
```

Mọi thứ cần để xác minh nằm trong một chuỗi: thuật toán nào, tham số nào, salt
nào. Đó là thứ khiến việc nâng cấp khả thi — khi bạn tăng tham số chi phí, hash cũ
vẫn xác minh được bằng tham số cũ, và bạn hash lại mật khẩu ở lần đăng nhập thành
công kế tiếp.

## Xác minh, và thêm một cái bẫy

```python
from argon2 import PasswordHasher
ph = PasswordHasher()

hash = ph.hash("hunter2")          # lúc tạo tài khoản
ph.verify(hash, "hunter2")         # lúc đăng nhập — sai thì raise
```

**Đừng bao giờ so bí mật bằng `==`.** So chuỗi dừng ở byte khác nhau đầu tiên, nên
một lần đoán sai nhưng trùng phần đầu sẽ mất nhiều thời gian hơn một cách đo được.
Đo đủ nhiều lần là khôi phục được bí mật từng ký tự — gọi là **timing attack**.
Dùng `hmac.compare_digest`, luôn tốn thời gian như nhau.

`argon2.verify` đã làm điều này bên trong. Nó quan trọng với *các bí mật khác*:
`app/main.py` hiện đang viết

```python
if authorization != f"Bearer {settings.mobile_api_token}":   # ← không constant-time
```

Rủi ro thực tế thấp (nhiễu mạng lấn át tín hiệu), sửa thì miễn phí, và kế hoạch
sửa nó ở Phase 3.

## Quy tắc mật khẩu nên có (và nên bỏ)

Hướng dẫn hiện đại (NIST SP 800-63B) đã đảo ngược lời khuyên cũ:

- ✅ **Độ dài quan trọng hơn độ phức tạp.** Tối thiểu ~10; dài hơn thì tốt hơn. Một
  cụm từ dài ăn đứt `P@ssw0rd!`.
- ✅ **Đối chiếu danh sách mật khẩu đã lộ** nếu tiện.
- ❌ **Không bắt buộc thành phần.** "Một chữ hoa, một số, một ký tự đặc biệt" đẩy
  người ta tới `Password1!` — dễ đoán, và ai cũng ghét.
- ❌ **Không bắt đổi định kỳ.** Hết hạn 90 ngày sinh ra `Summer2026`, rồi
  `Summer2027`. Đổi khi có dấu hiệu bị lộ, không đổi theo lịch.

## Trong StockPulse

- **argon2id** qua `argon2-cffi`, tham số mặc định (hợp lý ở thời điểm này).
- Một người dùng, tạo bằng CLI trên droplet. Hash nằm trong bảng `users`.
- **Mật khẩu không bao giờ chạm vào bộ nhớ lưu trữ của điện thoại** — chỉ có token
  (file 11).
- Đặt lại mật khẩu = chạy lại lệnh CLI. Trung thực với một người dùng; thành việc
  thật với hai người.

## Hiểu lầm thường gặp

**"Tôi sẽ mã hoá mật khẩu."** Mã hoá theo thiết kế là đảo ngược được, nên bạn sẽ
phải lưu một khoá biến database trở lại thành mật khẩu. Hash một chiều là có chủ
đích. (Mã hoá đúng cho dữ liệu bạn cần đọc lại — như một API key phải gửi đi tiếp.
Không bao giờ cho mật khẩu.)

**"Hash ở client để nó không phải đi qua mạng."** Thế thì cái hash *chính là* mật
khẩu: ai bắt được là phát lại được, và bạn chẳng được gì trong khi làm hỏng khả
năng nâng cấp phía server. Gửi qua TLS; hash ở server.

**"Salt phải bí mật."** Không cần, và nó nằm ngay cạnh hash. Việc của nó là tính
duy nhất, không phải tính bí mật. (Một bí mật riêng gọi là *pepper*, lưu ngoài
database, là lớp bổ sung tuỳ chọn — cơ chế khác.)

**"argon2 chậm, hại API của tôi."** Nó chạy một lần mỗi **lần đăng nhập**, không
phải mỗi request. Token sinh ra chính là để lo việc đó.

## Nhớ điều này

- Lưu hash, không lưu mật khẩu — server phải không có khả năng biết bí mật của bạn.
- **Salt** diệt tính-trước; **chậm** diệt đoán-mò. Cần cả hai.
- SHA-256 là công cụ sai *chính vì nó nhanh*. Dùng argon2id.
- So sánh bí mật bằng hàm constant-time.
