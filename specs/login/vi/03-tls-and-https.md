# 03 — TLS và HTTPS

## Vấn đề

Một request từ điện thoại tới droplet không đi qua một sợi dây riêng. Nó nhảy qua
router nhà bạn, ISP, vài mạng đường trục, rồi switch của nhà cung cấp hosting. Với
HTTP thường, **mọi chặng đó đều đọc và sửa được dữ liệu**.

Cụ thể: gửi mật khẩu qua HTTP nghĩa là quán cà phê, mọi người trong quán, ISP, và
bất kỳ ai đã lặng lẽ chen vào đường truyền — tất cả đều nhận được mật khẩu ở dạng
đọc được.

Ba mối nguy khác nhau, đáng tách bạch:

1. **Nghe lén (eavesdropping)** — ai đó đọc dữ liệu
2. **Sửa đổi (tampering)** — ai đó thay đổi dữ liệu giữa đường
3. **Giả mạo (impersonation)** — bạn kết nối tới server của kẻ tấn công mà tưởng
   là của mình

## Ý tưởng

**TLS** (Transport Layer Security) giải quyết cả ba. HTTPS đơn giản là HTTP chạy
bên trong một đường hầm TLS. HTTP không đổi gì cả — vẫn verb đó, header đó, JSON
đó. Nó chỉ được bọc lại.

> "SSL" là tiền thân đã chết của TLS. Ai cũng nói SSL; ai cũng đang nói về TLS.
> Thấy "SSL certificate" thì hiểu là "TLS certificate".

### TLS cho bạn những gì

| Tính chất | Nghĩa là | Chặn được |
|---|---|---|
| **Bí mật (confidentiality)** | Chỉ hai đầu đọc được | Nghe lén |
| **Toàn vẹn (integrity)** | Sửa đổi bị phát hiện | Sửa dữ liệu |
| **Xác thực (authentication)** | Server chứng minh nó là nó | Giả mạo |

Cái thứ ba là cái người ta hay quên, và chính nó làm hai cái đầu có giá trị. Mã
hoá tới kẻ tấn công thì vừa an toàn hoàn hảo vừa vô dụng hoàn toàn.

### Bắt tay (handshake), về mặt ý niệm

```
  ĐIỆN THOẠI                                        SERVER
    │  "chào, tôi nói TLS 1.3, đây là các cipher"     │
    │ ───────────────────────────────────────────────►│
    │                                                 │
    │  "chào, dùng cái này. Đây là CHỨNG CHỈ của tôi  │
    │   chứng minh tôi là stockpulse.you.com"         │
    │ ◄───────────────────────────────────────────────│
    │                                                 │
    │  Điện thoại kiểm tra: chứng chỉ này có được ký   │
    │  bởi ai đó tôi tin không? Tên có khớp cái tôi    │
    │  gõ không? Còn hạn không?                       │
    │                                                 │
    │  ── trao đổi khoá ─────────────────────────────►│
    │  Hai bên tự suy ra CÙNG một session key mà       │
    │  không hề gửi nó qua đường truyền.               │
    │                                                 │
    │ ═══════ từ đây trở đi mọi thứ đều mã hoá ══════ │
    │  GET /api/feed  Authorization: Bearer …         │
```

Hai ý đáng nhớ kỹ:

**Bất đối xứng → đối xứng.** Handshake dùng mã hoá khoá công khai (chậm) vừa đủ
lâu để thống nhất một khoá chung (nhanh), rồi chuyển sang dùng khoá đó. Bạn được
tính bảo mật của cái đầu và tốc độ của cái sau.

**Session key không bao giờ được truyền đi.** Hai bên *suy ra* nó từ các giá trị
công khai đã trao đổi. Kẻ ghi lại toàn bộ cuộc trò chuyện vẫn không dựng lại được.
Với TLS hiện đại điều này còn cho **forward secrecy**: khoá là tạm thời, nên kẻ
trộm được khoá riêng của server *về sau* cũng không giải mã được dữ liệu đã bắt
*trước đó*.

### Cái gì **không** được mã hoá

TLS giấu đường dẫn, header, body và response. Nó **không** giấu:

- **bạn kết nối tới server nào** — IP nằm trên gói tin, và hostname lộ ra trong
  handshake (qua SNI) trừ khi dùng Encrypted Client Hello
- **bao nhiêu dữ liệu đã đi qua, và vào lúc nào**

Nên người quan sát biết *rằng* điện thoại bạn đã nói chuyện với
`stockpulse.yourdomain.com` và khoảng bao nhiêu dữ liệu. Họ không biết bạn hỏi về
WDC.

## Trong StockPulse

- TLS kết thúc tại **Caddy** trên droplet. Caddy giải mã rồi chuyển HTTP thường
  tới `127.0.0.1:8000`. Chặng bên trong đó không mã hoá — không sao, vì nó không
  bao giờ rời khỏi máy.
- **Mật khẩu** chỉ đi qua mạng lúc đăng nhập, và luôn nằm trong TLS.
- **Access token và refresh token** đi qua ở mọi request. Chúng là bearer token —
  ai cầm thì dùng được — nên TLS là thứ duy nhất giữ chúng kín trên đường. Không
  có TLS thì toàn bộ thiết kế token trở nên vô nghĩa.
- **HSTS** (`Strict-Transport-Security`) nên bật khi bạn đã yên tâm: nó bảo điện
  thoại "đừng bao giờ nói HTTP thường với host này nữa", đóng lại khe hở nhỏ ở
  request đầu tiên.

## Hiểu lầm thường gặp

**"Có HTTPS nghĩa là trang web an toàn."** Nghĩa là *đường truyền* riêng tư và
server đúng là nó. Một trang lừa đảo vẫn có HTTPS hoàn hảo. Và API của chính bạn
có thể được mã hoá hoàn hảo trong khi cho phép cả thế giới gọi `/run`. Mã hoá
không phải là phân quyền — đúng cái sai mà file 01 cảnh báo.

**"Ổ khoá nghĩa là công ty đã được xác minh."** Với chứng chỉ thường, nó chỉ nghĩa
là ai đó đã chứng minh quyền kiểm soát tên miền. Không nói gì về họ là ai.

**"TLS bảo vệ dữ liệu trên server."** Nó bảo vệ dữ liệu *đang truyền*. Khi đã tới
nơi, dữ liệu là chữ thường trong bộ nhớ app và trong database. Bảo mật lưu trữ là
việc khác — và đó là lý do mật khẩu phải hash (file 08).

**"Tôi nên mã hoá mật khẩu trước khi gửi."** Không. Gửi qua TLS và hash *ở phía
server*. Hash ở client chỉ biến cái hash thành mật khẩu mới — ai bắt được nó là
phát lại được. Hãy để TLS làm việc vận chuyển.

## Nhớ điều này

- TLS cho bí mật, toàn vẹn **và** xác thực server; cái thứ ba làm hai cái kia có
  ý nghĩa.
- HTTPS bảo vệ cái ống. Nó không nói gì về việc ai được gọi API của bạn.
- Token của bạn là bearer credential trên mọi request — TLS là thứ giữ chúng
  không bị đọc trên đường.
