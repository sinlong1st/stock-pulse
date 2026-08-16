# 09 — Token và JWT

## Vấn đề

Bạn đã đăng nhập. Giờ bạn mở tab Predict, rồi Watchlist, rồi Settings — hai chục
request trong một phút. Mỗi request tới như một yêu cầu HTTP độc lập, mà HTTP thì
**không có trạng thái (stateless)**: server không nhớ request trước đó là của bạn.

Gửi mật khẩu kèm mọi request sẽ rất tệ:

- nó đi qua mạng hai chục lần thay vì một lần
- điện thoại phải **lưu** mật khẩu để làm được thế — đúng điều file 08 tránh
- argon2 tốn ~100 mili giây *mỗi request*, theo thiết kế
- một request bị lộ là lộ luôn credential vĩnh viễn

Vậy: chứng minh rằng bạn đã đăng nhập, mà không gửi lại thứ đã dùng để đăng nhập.

## Ý tưởng

**Token** là một chuỗi được cấp lúc đăng nhập, chứng minh bạn đã xác thực rồi.

Phần lớn là **bearer token**: ai *cầm* thì được vào, không hỏi thêm. Giống tiền
mặt — ai lấy được thì cũng tiêu được. Hai hệ quả định hình mọi thứ phía sau: chỉ
gửi qua TLS (file 03), và giữ thời hạn ngắn.

```
  Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.4f2a9c…
                 ↑      ↑
                 scheme  token
```

Trong header, không phải query string — URL rơi vào log, lịch sử và header
`Referer` (file 07).

## Hai loại token

**Opaque (mờ)** — một chuỗi ngẫu nhiên, tự nó không mang nghĩa gì. Server phải tra
cứu.

```
  8f3a9c2e4b6d1a7f…   →  DB nói: user 1, hết hạn 12/9
```

**Tự mô tả (JWT)** — mang sẵn dữ kiện, có ký. Server kiểm chữ ký rồi đọc. Không
tra cứu.

Không cái nào "tốt hơn"; chúng đánh đổi giữa khả năng thu hồi và tốc độ. File 10
dùng mỗi loại một cái.

## Giải phẫu một JWT

Ba phần base64url, ngăn bằng dấu chấm:

```
  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 . eyJzdWIiOiIxIiwiZXhwIjoxNzY1NDMyMTAwfQ . 4f2a9c8e…
  └───────────── header ──────────────┘ └──────────── payload ───────────────┘ └ chữ ký ─┘
```

**Header** — thuật toán nào đã ký:
```json
{ "alg": "HS256", "typ": "JWT" }
```

**Payload** — các **claim**, là những dữ kiện server khẳng định:
```json
{
  "sub": "1",              // subject — người dùng nào
  "iat": 1765431200,       // cấp lúc nào
  "exp": 1765432100,       // hết hạn lúc nào  ← cái quan trọng
  "jti": "a3f9…"           // id duy nhất, nếu muốn chặn riêng lẻ
}
```

**Chữ ký** — `HMAC-SHA256(header + "." + payload, secret_của_server)`.

### Vì sao chữ ký làm nó đáng tin

Server không cần nhớ đã cấp token nào. Để xác minh, nó tính lại chữ ký từ header
và payload nhận được bằng secret của mình. Khớp thì nội dung chưa bị đụng — vì tạo
được chữ ký hợp lệ đòi hỏi secret, mà chỉ server có.

Đổi `"sub": "1"` thành `"sub": "2"` là chữ ký không khớp nữa. Bạn không giả được
chữ ký mới nếu không có secret.

> ### Hiểu lầm quan trọng nhất
>
> **JWT được KÝ, không được MÃ HOÁ.**
>
> Payload chỉ là *base64*, tức là mã hoá ký tự chứ không phải mật mã. Ai cầm token
> đều giải ra đọc được — dán thử một cái vào [jwt.io](https://jwt.io) mà xem.
>
> Ký chặn **sửa đổi**, không chặn **đọc**.
>
> Nên: đừng bao giờ để thứ gì bí mật trong payload. Không mật khẩu, không API key,
> không dữ liệu cá nhân bạn không muốn công bố. Một user id và một mốc hết hạn là
> vừa đúng.

### HS256 và RS256

- **HS256** — một secret dùng chung để ký và để xác minh. Đơn giản. Đúng khi cùng
  một bên làm cả hai việc, tức là trường hợp của bạn.
- **RS256** — khoá riêng ký, khoá công khai xác minh. Đúng khi *dịch vụ khác* phải
  xác minh token mà không được phép tạo ra token.

StockPulse: **HS256**, một secret trong `.env` của droplet.

> Một cái bẫy lịch sử đáng biết: vài thư viện cũ chấp nhận `"alg": "none"` lấy từ
> *chính token*, khiến ai cũng gửi được token không ký và vẫn được tin. Luôn ghim
> thuật toán mong đợi khi xác minh (`algorithms=["HS256"]`) thay vì tin header.
> PyJWT hiện đại bắt buộc điều này.

## Cái vướng định hình toàn bộ thiết kế

JWT được xác minh bằng **toán**, không phải bằng tra cứu. Đó là tốc độ của nó — và
cũng là khuyết điểm:

**Bạn không thu hồi được JWT.** Không có gì để xoá. Đã cấp là hợp lệ tới `exp`,
hết. "Đăng xuất thiết bị này" không thực hiện được; token vẫn chạy.

Hai cách giảm nhẹ:

1. **Hạn ngắn.** Token 15 phút giới hạn thiệt hại trong 15 phút.
2. **Danh sách chặn.** Lưu các `jti` đã thu hồi và kiểm ở mọi request — tức là
   mang lại đúng cái lượt tra cứu database mà bạn dùng JWT để tránh.

StockPulse chọn cách 1 cho access token, và ghép nó với một refresh token opaque
thu hồi được cho mọi thứ dài hơi hơn. Đó là file 10.

## Trong StockPulse

- **Access token: JWT, HS256, 15 phút.** Claim: `sub`, `iat`, `exp`.
- **Secret**: `JWT_SECRET` trong `.env` của droplet — dài và ngẫu nhiên
  (`openssl rand -hex 32`). Không bao giờ commit. Đổi nó sẽ vô hiệu mọi token cùng
  lúc, một cái cần gạt thô nhưng hữu ích khi khẩn cấp.
- **Xác minh** là một dependency của FastAPI thay cho `_require_mobile_api`, để
  mọi route nhận được một người dùng thật thay vì một mật khẩu dùng chung.
- Thư viện: `pyjwt`.

## Hiểu lầm thường gặp

**"JWT được mã hoá."** Không. Được ký. Ai cầm token đều đọc được. Đây là hiểu lầm
phổ biến nhất về JWT và nó dẫn thẳng tới việc người ta nhét dữ liệu cá nhân vào
payload.

**"JWT an toàn hơn session."** Khác nhau, không phải tốt hơn. Session thu hồi tức
thì và tốn một lượt tra cứu. JWT nhanh và không thu hồi được. Chọn theo từng việc.

**"Cho token sống một năm để khỏi phải đăng nhập lại."** Thế thì token bị trộm là
một năm truy cập mà bạn không huỷ được. Thời hạn *chính là* cửa sổ rủi ro.

**"Nhét email và gói cước vào token cho khỏi query DB."** Được — nhưng ai cầm token
đọc được, và chúng sẽ **cũ đi**. Hạ gói cước của ai đó mà token vẫn khai gói cũ
cho tới khi hết hạn.

## Nhớ điều này

- Bearer token là tiền mặt: ai cầm, người đó tiêu. Luôn qua TLS; hạn ngắn.
- **Ký ≠ mã hoá.** Payload là công khai với bất kỳ ai cầm token.
- Tốc độ của JWT và việc không thu hồi được nó là cùng một tính chất. Đó là lý do
  một token thôi thì không đủ.
