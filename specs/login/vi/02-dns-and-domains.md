# 02 — DNS và domain

## Vấn đề

Máy tính tìm nhau bằng **địa chỉ IP** — droplet của bạn kiểu `164.90.х.х`. Con
người không nhớ nổi, IP lại đổi khi dựng lại server, và — quan trọng nhất với
chúng ta — **bạn gần như không thể xin chứng chỉ HTTPS cho một IP trần**.

Vậy nên cần một cái tên ổn định, dễ đọc, trỏ tới một máy.

## Ý tưởng

**DNS** (Domain Name System) là một cuốn danh bạ phân tán. Bạn hỏi "địa chỉ của
`stockpulse.example.com` là gì?" và nhận về một IP.

Nó *phân tán* và *phân cấp* — không máy nào giữ toàn bộ bản ghi của Internet. Đọc
từ phải sang trái:

```
        stockpulse   .   example   .   com   .
             │             │           │      │
             │             │           │      └── gốc (root, ngầm định)
             │             │           └───────── TLD, do một registry quản lý
             │             └───────────────────── domain BẠN đăng ký
             └─────────────────────────────────── subdomain, bạn tự đặt
```

Khi đã sở hữu `example.com`, mọi subdomain bên dưới là của bạn, miễn phí. Bạn
không cần mua `stockpulse.example.com` — bạn tự tạo ra nó.

### Một lượt tra cứu chạy thế nào

```
  Điện thoại: "stockpulse.example.com ở đâu?"
     │
     ├─► Resolver (của ISP, hoặc 1.1.1.1) — xem cache trước
     │      │  (không có)
     │      ├─► Root server:    "hỏi registry .com"
     │      ├─► Registry .com:  "hỏi nameserver của example.com"
     │      └─► Nameserver:     "164.90.х.х"   ← câu trả lời
     │
     └─◄ 164.90.х.х  (cache trong TTL giây)
```

Resolver cache câu trả lời trong khoảng **TTL** (time to live). Đây là lý do đổi
DNS "mất thời gian lan truyền" — thực ra chẳng có gì lan truyền cả, chỉ là câu trả
lời cũ vẫn còn trong cache.

### Các loại bản ghi bạn sẽ gặp

| Loại | Ánh xạ | Ví dụ |
|---|---|---|
| **A** | tên → IPv4 | `stockpulse.example.com → 164.90.х.х` |
| **AAAA** | tên → IPv6 | như trên, cho IPv6 |
| **CNAME** | tên → một *tên* khác | `www → example.com` |
| **MX** | máy chủ mail | định tuyến email |
| **TXT** | văn bản tuỳ ý | chứng minh quyền sở hữu domain |

Bạn chỉ cần đúng một cái: một bản ghi **A** trỏ về droplet.

**TXT** đáng biết vì lý do thứ hai: đó là cách chứng minh quyền sở hữu domain với
CA mà không cần mở web server (thử thách DNS-01 — xem file 04).

## Trong StockPulse

Bạn chưa có domain, nên mọi thứ liên quan tới công khai đều phải chờ. Cụ thể:

1. Đăng ký domain (~10–15 USD/năm) hoặc dùng subdomain của domain bạn đã có.
2. Tạo bản ghi **A**: `stockpulse.yourdomain.com → IP của droplet`.
3. Đặt **TTL thấp** (300 giây) *trước khi* bắt đầu, để sửa sai cho rẻ.
4. Kiểm tra từ máy bạn:

```bash
dig +short stockpulse.yourdomain.com     # phải in ra IP droplet
```

Làm và xác nhận bước này **trước khi** đụng vào Caddy. Việc cấp chứng chỉ phụ
thuộc vào DNS đã đúng sẵn, và gỡ hai thứ hỏng cùng lúc là cách mất cả buổi chiều.

### Về nhà đăng ký (registrar)

Registrar là nơi bạn mua (Namecheap, Cloudflare, Porkbun…). Điều thực sự quan
trọng: họ có miễn phí **WHOIS privacy** không (nếu không, tên, địa chỉ và email
của bạn bị công bố trong cơ sở dữ liệu đăng ký công khai), và bảng điều khiển DNS
có dễ dùng không. Cloudflare và Porkbun miễn phí khoản privacy; vài nơi khác thu
tiền hằng năm.

## Hiểu lầm thường gặp

**"Đổi DNS mất 24–48 tiếng."** Phần lớn là truyền thuyết. Chẳng có gì "lan truyền"
— resolver chỉ giữ cache đúng bằng TTL bạn đặt. Đặt TTL 300 giây từ trước thì thay
đổi thấy sau 5 phút. Con số 24 tiếng đến từ những bản ghi để TTL một ngày.

**"CNAME với A dùng thay nhau được."** CNAME trỏ tới một *tên*, và tên đó lại cần
tra cứu tiếp. Trong DNS cổ điển bạn không đặt được CNAME ở gốc domain
(`example.com`), chỉ ở subdomain.

**"DNS là một lớp bảo mật."** Hoàn toàn không. DNS là danh bạ công khai. Ai cũng
tra được bản ghi của bạn; việc một cái tên phân giải được không cho ai quyền gì
cả. Bảo mật bắt đầu *sau khi* kết nối được thiết lập.

**"Dùng thẳng IP cũng được mà."** Bạn tới được server, nhưng CA thực tế không cấp
chứng chỉ cho IP trần, nghĩa là không có HTTPS — nghĩa là mật khẩu của bạn đi qua
Internet ở dạng chữ thường.

## Nhớ điều này

- DNS biến tên thành IP; nó là **danh bạ công khai**, không bao giờ là ổ khoá.
- Bạn cần một bản ghi **A**. Đặt TTL thấp trước để sai sót chỉ tốn vài phút.
- Không domain → không chứng chỉ → không HTTPS → không login an toàn. Đây là điều
  kiện tiên quyết mà mọi thứ khác đang chờ.
