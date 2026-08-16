# 07 — Nền tảng về xác thực

## Vấn đề

Phần 1 đã đưa được kết nối tới server, có mã hoá và có kiểm chứng. Server giờ biết
kết nối là riêng tư và biết *nó* đúng là nó.

Nhưng nó vẫn chẳng biết ai đang gọi.

Mọi request đều tới dưới dạng byte. Không có khuôn mặt, không có giọng nói, không
có gì tự thân là "bạn". Danh tính phải được *dựng nên* từ một thứ mà người gọi có
thể chứng minh.

## Hai từ hay bị dùng lẫn (và không nên)

| | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** (authn) | *Bạn là ai?* | Đăng nhập bằng mật khẩu |
| **Authorization** (authz) | *Bạn được làm gì?* | "Chỉ admin mới được xoá user" |

Authn đi trước và trả lời về danh tính. Authz dùng danh tính đó để ra quyết định.
Trộn hai cái này sinh ra hệ thống biết tên bạn rồi cho bạn làm mọi thứ — hoặc kiểm
tra quyền cho một người chưa ai xác minh.

**StockPulse cần authn.** Với một người dùng, authz chỉ đơn giản là "người đã đăng
nhập được làm mọi thứ". Nó chỉ thành việc thật khi có người dùng thứ hai — mà đó
là quyết định sản phẩm, không phải quyết định bảo mật.

## Ba yếu tố (factor)

Xác thực dựa trên việc chứng minh một trong:

| Yếu tố | Nghĩa là | Ví dụ |
|---|---|---|
| **Cái bạn biết** | bí mật trong đầu | mật khẩu, mã PIN |
| **Cái bạn có** | vật thể | điện thoại, khoá bảo mật, app TOTP |
| **Cái bạn là** | số đo cơ thể | vân tay, khuôn mặt |

**Đa yếu tố (MFA)** nghĩa là hai *nhóm khác nhau*. Mật khẩu cộng câu hỏi bảo mật
không phải MFA — cả hai đều là "cái bạn biết", và cùng rò rỉ từ một vụ lộ dữ liệu.

StockPulse dùng một yếu tố (mật khẩu). Đó là lựa chọn cân xứng có chủ đích: một
người dùng, công cụ cá nhân, và mối đe doạ thực tế là bot chứ không phải kẻ nhắm
vào bạn. Thiết kế vẫn chừa chỗ cho TOTP sau này mà không phải làm lại.

> Đáng chú ý: vân tay/khuôn mặt **của điện thoại** không xác thực bạn với
> StockPulse. Nó mở khoá Keychain (file 11), nơi nhả ra một token đã được mật khẩu
> của bạn tạo ra từ trước. Sinh trắc học là cái cổng cục bộ trên một credential đã
> lưu — phân biệt này quan trọng khi nghĩ về việc một chiếc điện thoại đang mở khoá
> bị mất thì kẻ nhặt được có gì.

## Credential

**Credential** là bất cứ thứ gì chứng minh danh tính: mật khẩu, token, API key,
khoá riêng. Quy tắc làm việc:

> **Đối xử với mọi credential như đối xử với mật khẩu.**
> Không ghi log. Không lưu dạng chữ thường. Không nhét vào URL.

Vế cuối hay bị dính. URL kết thúc trong log truy cập của server, lịch sử trình
duyệt, header `Referer` gửi sang bên thứ ba, và công cụ phân tích. `?token=abc123`
là một vụ rò credential có thêm vài bước — đó là lý do token đi trong header
`Authorization`, không phải trong query string.

## Danh tính stateless và stateful

Hai cách để nhớ rằng ai đó đã đăng nhập:

**Stateful (session).** Server lưu một bản ghi phiên và đưa client một ID mờ. Mỗi
request tốn một lượt tra cứu. Thu hồi tức thì — xoá dòng đó là xong.

**Stateless (token).** Server phát ra một token đã ký chứa sẵn các dữ kiện. Mỗi
request chỉ kiểm chữ ký — không đụng database. Không có gì để xoá, nên *không thể*
thu hồi trước khi hết hạn.

```
  STATEFUL                          STATELESS
  client: "session abc123"          client: "đây là token đã ký"
  server: tra cứu ───► DB           server: kiểm chữ ký (chỉ toán)
  ✓ thu hồi tức thì                 ✗ không thu hồi được
  ✗ mỗi request một lượt tra         ✓ không tra cứu
```

Không cái nào thắng tuyệt đối. StockPulse dùng **cả hai, cho hai việc khác nhau** —
access token stateless để nhanh, refresh token stateful để kiểm soát. Đó là nội
dung file 10, và nó tồn tại chính vì đánh đổi này không có đáp án duy nhất.

## Đăng nhập thực chất lập ra điều gì

Khi đăng nhập, bạn đổi một credential **dài hạn** (mật khẩu — không đổi, mở được
mọi thứ) lấy một credential **ngắn hạn** (token có hạn, có thể giới hạn phạm vi).

Chính cuộc đổi chác đó là toàn bộ ý nghĩa:

- Mật khẩu đi qua mạng **một lần mỗi phiên đăng nhập**, không phải mỗi request.
- Điện thoại lưu token, không bao giờ lưu mật khẩu.
- Token bị trộm sẽ hết hạn; mật khẩu bị trộm thì không.
- Token theo từng thiết bị, nên thu hồi một cái không đụng các cái khác.

So với thiết kế hiện tại: một bí mật dùng chung được biên dịch thẳng vào app,
giống hệt nhau trên mọi bản cài, không bao giờ hết hạn, chỉ thu hồi được bằng cách
build lại app. Mọi tính chất ở trên đều thiếu.

## Trong StockPulse

- **Một yếu tố**: email + mật khẩu.
- **Không có đăng ký công khai.** Một người dùng, tạo bằng lệnh CLI trên droplet.
  Một endpoint đăng ký sẽ cho phép bất kỳ ai tạo tài khoản và tiêu tiền OpenAI của
  bạn — cuộc tấn công đơn giản đúng như vậy.
- **Đặt lại mật khẩu** là "SSH vào rồi chạy lệnh". Ổn với một người dùng; thành
  việc thật với hai người, vì lúc đó cần email.
- **Danh tính thay thế token dùng chung ở mọi nơi** — kể cả
  `/api/push/register`, để thông báo đi theo tài khoản chứ không theo bản build.

## Hiểu lầm thường gặp

**"Authentication với authorization về cơ bản giống nhau."** Chúng liền kề nhưng
khác nhau. Trộn lẫn sinh ra "đã đăng nhập nên được làm mọi thứ" — vô hại với một
người dùng, nguy hiểm với hai.

**"Để mật khẩu trong URL cũng được vì có HTTPS."** TLS bảo vệ lúc truyền, rồi nó
rơi vào log truy cập, lịch sử trình duyệt và header `Referer`. Dùng header.

**"Càng nhiều yếu tố càng tốt."** Nhiều yếu tố tốn trải nghiệm, mà trải nghiệm tệ
đẻ ra những cách lách còn tệ hơn. Một yếu tố cộng rate limiting là lựa chọn hợp lý
và bảo vệ được cho một công cụ cá nhân một người dùng.

## Nhớ điều này

- Authn là *ai*, authz là *được làm gì*. Làm đúng cái đầu trước.
- Đăng nhập đổi credential vĩnh viễn lấy credential tạm thời — cuộc đổi chác đó là
  toàn bộ giá trị.
- Stateless thì nhanh nhưng không thu hồi được; stateful thu hồi được nhưng tốn
  một lượt tra cứu. StockPulse dùng mỗi cái ở chỗ nó mạnh.
