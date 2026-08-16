# 04 — Chứng chỉ và niềm tin

## Vấn đề

File 03 kết thúc bằng một câu hỏi chưa trả lời. Trong handshake, server nói *"tôi
là stockpulse.yourdomain.com."*

Tại sao điện thoại phải tin?

Ai cũng có thể tự nhận bất kỳ cái tên nào. Nếu DNS của bạn bị chiếm, hoặc bạn đang
ở trên một mạng độc hại, cái máy trả lời có thể không phải máy của bạn. Mã hoá một
cuộc trò chuyện với kẻ mạo danh còn tệ hơn không mã hoá — vì nó *có cảm giác* an
toàn.

## Ý tưởng

**Chứng chỉ (certificate)** là một file gắn một **cái tên** với một **khoá công
khai**, được ký bởi một bên mà điện thoại đã tin sẵn.

```
  CHỨNG CHỈ
  ├─ Subject:      stockpulse.yourdomain.com     ← cái tên
  ├─ Public key:   30 82 01 0a 02 82 01 01 …     ← khoá đi kèm
  ├─ Hiệu lực:     2026-08-13 → 2026-11-11       ← ~90 ngày
  ├─ Issuer:       Let's Encrypt R3              ← ai bảo lãnh
  └─ Chữ ký:       (chữ ký của Issuer lên tất cả những cái trên)
```

Server còn giữ **khoá riêng (private key)** khớp với khoá công khai đó, và khoá
riêng không bao giờ rời khỏi máy. Trong handshake, server chứng minh nó đang giữ
khoá riêng. Chuỗi lập luận là:

1. Tôi tin bên cấp (issuer).
2. Bên cấp đã ký "khoá công khai này thuộc về `stockpulse.yourdomain.com`".
3. Server này vừa chứng minh nó giữ khoá riêng tương ứng.
4. Vậy server này đúng là `stockpulse.yourdomain.com`.

### Niềm tin đặt đáy ở đâu

Điện thoại của bạn xuất xưởng kèm một **root store** — vài chục chứng chỉ của các
Certificate Authority được Apple/Google nhúng sẵn vào hệ điều hành. Đó là các tiên
đề.

```
  Root CA  (nằm trong hệ điều hành, tin theo định nghĩa)
     │ ký
  Intermediate CA  (Let's Encrypt R3)
     │ ký
  Chứng chỉ của bạn  (stockpulse.yourdomain.com)
```

Root ký intermediate, intermediate ký chứng chỉ của bạn. Root nằm offline trong
két; intermediate làm việc hằng ngày và có thể bị thu hồi nếu lộ mà không cần nạp
lại firmware cho mọi điện thoại trên đời.

### CA thực sự kiểm tra cái gì

Với chứng chỉ thường (Domain Validated), đúng một thứ: **bạn có kiểm soát tên miền
này không?** Không phải bạn là ai, không phải bạn có đáng tin không. Hai cách
chứng minh:

- **HTTP-01** — CA đưa bạn một token; bạn phục vụ nó tại
  `http://yourdomain/.well-known/acme-challenge/<token>`. Cần mở cổng 80.
- **DNS-01** — bạn đăng token thành bản ghi TXT. Không cần web server nào, và là
  cách duy nhất để lấy chứng chỉ **wildcard** (`*.yourdomain.com`).

**ACME** là giao thức tự động hoá toàn bộ màn này. **Let's Encrypt** là một CA
miễn phí nói ACME. Caddy có sẵn ACME client bên trong — đó là lý do cấu hình của
nó chỉ 5 dòng và việc gia hạn không còn là việc của bạn.

### Vì sao chỉ 90 ngày

Chứng chỉ Let's Encrypt cố tình ngắn hạn:

- Khoá riêng bị trộm chỉ dùng được tới lúc hết hạn.
- Hạn ngắn *ép* phải tự động hoá, và việc tự động thì không bị quên như một lời
  nhắc lịch mỗi năm một lần.

Caddy gia hạn quanh ngày thứ 60, âm thầm. Nỗi sợ "hết hạn chứng chỉ, sập web" là
đặc sản của quản lý chứng chỉ *thủ công*.

## Certificate Transparency: phần làm đổi mô hình mối đe doạ của bạn

Mọi chứng chỉ do CA công khai cấp đều được nộp vào **Certificate Transparency
log**: bản ghi công khai, chỉ-thêm, kiểm chứng được bằng mật mã.

Nó tồn tại vì một lý do rất tốt. Năm 2011 một CA bị xâm nhập và cấp một chứng chỉ
hợp lệ cho `*.google.com` cho kẻ tấn công. Không ai phát hiện được, vì việc cấp
phát là vô hình. CT làm cho việc cấp phát có thể kiểm toán: chủ domain có thể theo
dõi những chứng chỉ mà mình không hề yêu cầu.

**Hệ quả phụ mới là thứ liên quan tới bạn.** Ngay khi Caddy lấy chứng chỉ,
hostname `stockpulse.yourdomain.com` được công bố vào một log công khai ai cũng
đọc được — và bot thì đọc liên tục, để tìm host mới mà dò.

Bạn tự xem được tại [crt.sh](https://crt.sh) — gõ bất kỳ domain nào và đọc mọi
chứng chỉ từng cấp cho nó.

```
  Bạn chạy Caddy  ──►  Let's Encrypt cấp  ──►  bản ghi CT (công khai)
                                                      │
                                   scanner nuốt dữ liệu
                                                      │
                        vài giờ sau: dò /, /admin, /run
```

Đây *chính là* lý do `specs/STOCKPULSE_AUTH_PLAN.md` đặt xác thực trước công khai.
Phòng thủ của bạn không thể là "không ai biết địa chỉ", vì công bố địa chỉ là một
phần bắt buộc của việc lấy chứng chỉ.

## Trong StockPulse

- Caddy tự lấy và tự gia hạn chứng chỉ. Bạn chỉ khai một tên miền, không gì khác.
- **Cổng 80 phải tới được** cho thử thách HTTP-01 (Caddy cũng dùng nó để chuyển
  hướng sang HTTPS). Nếu không muốn mở 80, dùng DNS-01 qua API của registrar.
- **Đừng** dùng chứng chỉ tự ký. React Native từ chối chứng chỉ không tin cậy, và
  mọi cách lách đều quy về tắt kiểm tra — tức là bỏ luôn phần chống giả mạo, vốn
  là phần lớn giá trị của TLS.
- Hãy coi hostname của bạn là công khai ngay từ ngày đầu.

## Hiểu lầm thường gặp

**"Ổ khoá nghĩa là trang web chính danh."** Nó nghĩa là ai đó đã chứng minh quyền
kiểm soát tên miền. Trang lừa đảo cũng có chứng chỉ hợp lệ. Ổ khoá nói về *đường
truyền*, không bao giờ nói về *tư cách* người vận hành.

**"Chứng chỉ thì tốn tiền."** Trước kia thì có. Let's Encrypt miễn phí và đã cấp
hàng trăm triệu cái. Chứng chỉ trả phí bán kèm bảo hiểm và xác minh tổ chức — bạn
không cần cả hai.

**"Hết hạn là web sập."** Với gia hạn tự động thì không. Với gia hạn thủ công thì
chắc chắn — đó là lý lẽ ủng hộ tự động hoá, không phải ủng hộ hạn dài.

**"Có chứng chỉ chứng tỏ server tôi an toàn."** Nó chứng tỏ *cái tên* khớp. Server
của bạn có thể có chứng chỉ hoàn hảo mà vẫn mở toang — đúng tình trạng bạn sẽ rơi
vào nếu bỏ qua phần xác thực.

## Nhớ điều này

- Chứng chỉ gắn một **cái tên** với một **khoá**, được ký bởi bên điện thoại đã
  tin sẵn.
- Chứng chỉ DV chỉ chứng minh **quyền kiểm soát một cái tên** — không hơn.
- **Certificate Transparency công bố hostname của bạn ngay khi bạn lấy chứng
  chỉ.** Bạn không có lựa chọn "ẩn danh". Hãy lên kế hoạch theo đó.
