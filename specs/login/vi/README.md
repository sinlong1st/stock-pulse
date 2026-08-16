# Thư viện học về Login (tiếng Việt)

Mỗi khái niệm một file, theo thứ tự đọc. Viết để **hiểu** chứ không phải để lướt:
mỗi file giải thích **vấn đề mà thứ đó sinh ra để giải quyết** trước, rồi mới đến
cơ chế — vì một cơ chế không gắn với vấn đề của nó chỉ là mẩu kiến thức rời, đọc
xong sẽ quên.

> **Về thuật ngữ:** các từ kỹ thuật (TLS, JWT, token, hash, salt, reverse proxy…)
> được **giữ nguyên tiếng Anh** và giải thích bằng tiếng Việt. Đây là những từ bạn
> sẽ gặp trong mọi tài liệu, mọi thư viện, mọi lỗi trên Stack Overflow — dịch ra
> tiếng Việt sẽ khiến bạn không nhận ra chúng khi gặp ngoài đời.

## Cách dùng

Đọc theo thứ tự. Mỗi file chỉ giả định bạn đã đọc các file trước nó. Cố tình viết
ngắn — mỗi file một lần ngồi, và dừng ở đâu cũng được mà không bị hụt mạch.

Mọi file đều có cùng một cấu trúc:

1. **Vấn đề** — không có nó thì hỏng chuyện gì
2. **Ý tưởng** — cơ chế, nói thẳng
3. **Trong StockPulse** — áp dụng vào server *của bạn*, với số liệu thật
4. **Hiểu lầm thường gặp** — cái mà nhiều người (kể cả tôi) hiểu sai
5. **Nhớ điều này** — hai ba câu đáng giữ lại

## Thứ tự đọc

### Phần 1 — Đưa được kết nối tới nơi

| # | File | Trả lời câu hỏi |
|---|---|---|
| 01 | [the-problem.md](01-the-problem.md) | Tại sao phải thay đổi gì cả? |
| 02 | [dns-and-domains.md](02-dns-and-domains.md) | Làm sao một cái tên tìm ra được server? |
| 03 | [tls-and-https.md](03-tls-and-https.md) | Chữ "s" trong https thực sự làm gì? |
| 04 | [certificates-and-trust.md](04-certificates-and-trust.md) | Vì sao điện thoại tin server đó là của bạn? |
| 05 | [reverse-proxies.md](05-reverse-proxies.md) | Caddy/nginx để làm gì, sao không dùng thẳng app? |
| 06 | [ports-and-binding.md](06-ports-and-binding.md) | Vì sao `127.0.0.1` là lý do duy nhất bạn còn an toàn? |

### Phần 2 — Chứng minh bạn là ai

| # | File | Trả lời câu hỏi |
|---|---|---|
| 07 | [authentication-basics.md](07-authentication-basics.md) | Danh tính là gì, trong một hệ thống không có khuôn mặt? |
| 08 | [password-hashing.md](08-password-hashing.md) | Lưu mật khẩu mà không được phép biết nó, bằng cách nào? |
| 09 | [tokens-and-jwt.md](09-tokens-and-jwt.md) | Làm sao ở lại trạng thái đăng nhập mà không gửi lại mật khẩu? |
| 10 | [sessions-access-refresh.md](10-sessions-access-refresh.md) | Tại sao hai token chứ không phải một? |
| 11 | [secure-storage.md](11-secure-storage.md) | Điện thoại giữ bí mật ở đâu? |

### Phần 3 — Sống sót khi ra Internet

| # | File | Trả lời câu hỏi |
|---|---|---|
| 12 | [attacks-and-defences.md](12-attacks-and-defences.md) | Ai tấn công một server cá nhân nhỏ, và bằng cách nào? |
| 13 | [rate-limiting.md](13-rate-limiting.md) | Làm sao khiến mỗi lần thử trở nên đắt đỏ? |

## Các tài liệu còn lại

- **`../../STOCKPULSE_AUTH_PLAN.md`** — kế hoạch xây: các phase, các quyết định,
  và những phương án đã bị loại kèm lý do.
- **`../../../AUTH_EXPLAINED.md`** — luồng chạy đầy đủ với 5 kịch bản thực tế
  (đăng nhập lần đầu, refresh ngầm, token bị trộm, bot tìm ra bạn, mất điện
  thoại). Đọc sau Phần 2 — đó là chỗ mọi mảnh ghép khớp lại.

## Nếu chỉ đọc một câu

Điện thoại của bạn hiện đang vào server qua VPN, và **chính cái VPN đó là thứ duy
nhất đứng giữa 11 route không có xác thực và toàn bộ Internet** — nên trước khi bỏ
được VPN, bản thân ứng dụng phải học cách biết bạn là ai.
