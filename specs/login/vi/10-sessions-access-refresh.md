# 10 — Session: access token và refresh token

## Vấn đề

File 09 để lại một lựa chọn tưởng như bất khả về thời hạn token:

| Thời hạn | Hệ quả |
|---|---|
| **Ngắn** (15 phút) | Token bị trộm chết nhanh ✅ … nhưng bạn nhập mật khẩu 4 lần mỗi giờ ❌ |
| **Dài** (30 ngày) | Đăng nhập mỗi tháng một lần ✅ … nhưng token bị trộm cho cả tháng truy cập mà bạn không thu hồi được ❌ |

Chọn cái nào cũng có thứ quan trọng bị sai. Lối ra là thôi coi nó là một vấn đề.

## Ý tưởng

Cấp **hai** token với hai nhiệm vụ, hai thời hạn và hai tính chất bảo mật khác
nhau.

| | Access token | Refresh token |
|---|---|---|
| Dạng | **JWT** (tự mô tả) | **Chuỗi ngẫu nhiên opaque** |
| Thời hạn | ~15 phút | ~30 ngày |
| Gửi khi | **mọi** request | **chỉ** tới `/api/auth/refresh` |
| Lưu ở server | không | có — **đã hash** |
| Thu hồi được | không | **được** |
| Nhiệm vụ duy nhất | chứng minh danh tính, rẻ | tạo access token mới |

Điểm mấu chốt: **token dùng liên tục thì sống ngắn, còn token sống dài thì gần như
không dùng.** Mức độ phơi bày và thời hạn được đảo ngược so với nhau.

```
  ┌────────── 30 ngày ──────────────────────────────────┐
  │ refresh token — rời Keychain khoảng 96 lần tổng cộng │
  └──────────────────────────────────────────────────────┘
   ┌─ 15p ─┐┌─ 15p ─┐┌─ 15p ─┐┌─ 15p ─┐ …
   access token — gửi ở từng request một
```

## Vì sao refresh token cố tình *không* phải JWT

Đây là quyết định thiết kế đáng hiểu cho kỹ.

JWT không thu hồi được (file 09) — xác minh là kiểm chữ ký, nên chẳng có gì để
xoá. Chấp nhận được với 15 phút. **Không chấp nhận được với 30 ngày.**

Làm refresh token thành chuỗi ngẫu nhiên opaque lưu trong database biến việc thu
hồi thành một câu `UPDATE`:

- "Đăng xuất thiết bị này" → thu hồi dòng đó
- "Đăng xuất mọi nơi" (mất điện thoại) → thu hồi mọi dòng của người dùng
- "Token đó bị trộm" → thu hồi và phát hiện

Bạn trả giá bằng một lượt tra cứu database — nhưng chỉ khi refresh, tức khoảng 15
phút một lần, chứ không phải mỗi request. Chi phí rơi đúng vào chỗ không quan
trọng.

**Lưu ở dạng đã hash.** Nó là credential (file 07): database bị trộm không được
phép cho ra refresh token dùng được. Ở đây SHA-256 là đủ, **không** dùng argon2 —
token là 256 bit ngẫu nhiên, không phải mật khẩu do người nghĩ ra, nên chẳng có gì
để dò và không có lý do trả giá argon2 ở mỗi lần refresh.

> Để ý đây là hình ảnh phản chiếu của bài học ở file 08. Hash chậm đúng cho bí mật
> entropy thấp do con người chọn; hash nhanh đúng cho bí mật entropy cao do máy
> sinh. Lý do trong cả hai trường hợp là như nhau: khả năng đoán được.

## Rotation và phát hiện tái sử dụng

Giờ tới phần biến vụ trộm từ thảm hoạ âm thầm thành một sự kiện bị phát hiện.

**Rotation (xoay vòng)**: mỗi lần refresh trả về một refresh token **mới** và cho
cái cũ nghỉ hưu. Các token tạo thành một chuỗi, cùng chung một `family_id`.

```
  đăng nhập → refresh_A
  refresh   → refresh_B   (A nghỉ hưu)
  refresh   → refresh_C   (B nghỉ hưu)
```

**Phát hiện tái sử dụng**: nếu một token *đã nghỉ hưu* lại được trình ra, có gì đó
sai. Client hợp pháp luôn giữ cái mới nhất. Một token đã nghỉ hưu xuất hiện nghĩa
là tồn tại một bản sao — nên server thu hồi **toàn bộ họ (family)** và bắt đăng
nhập lại.

```
  t=0  KẺ TRỘM  refresh(A) → nhận B        server cho A nghỉ hưu
  t=1  BẠN      refresh(A) → A ĐÃ NGHỈ HƯU
                 │
                 ├─► "có kẻ đang phát lại token đã nghỉ hưu"
                 └─► thu hồi cả họ: A, B, C, tất cả
                      │
        B của kẻ trộm chết; bạn đăng nhập lại bằng MẬT KHẨU,
        thứ mà kẻ trộm không có.
```

Không có rotation, một refresh token bị trộm là **30 ngày truy cập âm thầm**. Có
rotation, vụ trộm lộ ra ngay lần refresh kế tiếp của *một trong hai bên* — thường
là vài phút.

Cái giá là một cột thêm và một câu `if`.

## Điệu nhảy phía client

Điện thoại không cho người dùng thấy gì trong chuyện này:

```
  1. Gửi request kèm access token
  2. Nhận 401? → access token hết hạn
  3. POST /api/auth/refresh kèm refresh token
  4. Lưu refresh token mới; giữ access token mới trong bộ nhớ
  5. Gửi lại request ban đầu — MỘT LẦN
  6. Refresh cũng hỏng? → phiên thật sự kết thúc → màn hình đăng nhập
```

**Một lần** là số lần thử lại đúng. Nếu refresh hỏng, thử lại nữa cũng vô ích; chỉ
tạo vòng lặp. Và hai lần 401 đồng thời không được phép kích hai lần refresh — cái
thứ hai sẽ trình ra token mà cái thứ nhất vừa cho nghỉ hưu, và cơ chế phát hiện
tái sử dụng sẽ đăng xuất bạn, hoàn toàn đúng luật. Hãy tuần tự hoá refresh sau một
promise duy nhất; đây là lỗi kinh điển của thiết kế này.

## Mỗi token sống ở đâu

| | Ở đâu | Vì sao |
|---|---|---|
| Access token | **chỉ trong bộ nhớ** | Sống 15 phút; ghi ra đĩa chỉ thêm rủi ro mà không được gì |
| Refresh token | **Keychain / Keystore** (file 11) | Phải sống qua lần mở lại app; là credential 30 ngày |
| Mật khẩu | **không ở đâu trên thiết bị** | Gõ lúc đăng nhập rồi quên |

Dòng cuối là toàn bộ ý nghĩa của thiết kế. So với hiện tại: một bí mật dùng chung
vĩnh viễn biên dịch vào app, giống hệt nhau trên mọi bản cài.

## Trong StockPulse

- Access: JWT, HS256, 15 phút, claim `sub`/`iat`/`exp`.
- Refresh: 32 byte ngẫu nhiên, dạng hex; lưu hash SHA-256; 30 ngày; xoay vòng kèm
  phát hiện tái sử dụng.
- Bảng `refresh_tokens`: `token_hash`, `family_id`, `issued_at`, `expires_at`,
  `revoked_at`, `replaced_by`, `user_agent`.
- `user_agent` có mặt để sau này màn hình "các phiên của bạn" nói được *"iPhone,
  dùng lần cuối thứ Ba"* — và để một thiết bị lạ trở nên dễ thấy.
- Đăng xuất thu hồi một token. Mất điện thoại → thu hồi mọi dòng của người dùng.

## Hiểu lầm thường gặp

**"Hai token là làm quá cho một người dùng."** Nó nhiều hơn khoảng bốn chục dòng
so với một token, và đổi lại được khả năng thu hồi và phát hiện trộm — hai thứ mà
một token duy nhất về bản chất không thể có. Đó là món hời ở mọi quy mô.

**"Cứ cho access token sống 30 ngày rồi bỏ refresh đi."** Thế thì không thu hồi
được, không phát hiện được trộm, và mất điện thoại nghĩa là phải đổi secret ký và
đăng xuất mọi thiết bị, kể cả của bạn.

**"Rotation làm người dùng bị đăng xuất suốt."** Rotation là vô hình — nó xảy ra
bên trong lệnh refresh. Người dùng chỉ thấy khi hệ thống *phát hiện* tái sử dụng,
mà lúc đó nghĩa là có chuyện thật.

**"Hash refresh token bằng argon2 cho chắc."** Không cần và chậm. Chi phí của
argon2 để bảo vệ bí mật *đoán được*. Một token ngẫu nhiên 256 bit không đoán nổi;
SHA-256 mới là đúng ở đây.

## Nhớ điều này

- Token sống ngắn thì dùng liên tục; token sống dài thì dùng hiếm và thu hồi được.
- Refresh token **cố tình không phải JWT** — khả năng thu hồi là toàn bộ lý do.
- **Rotation + phát hiện tái sử dụng** biến token bị trộm từ truy cập vĩnh viễn âm
  thầm thành một sự kiện bị phát hiện.
- Thử lại request hỏng **một lần**, và đừng bao giờ để hai lệnh refresh chạy cùng
  lúc.
