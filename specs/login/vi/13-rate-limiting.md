# 13 — Rate limiting (giới hạn tần suất)

## Vấn đề

Hai thứ trở nên miễn phí ngay khi server của bạn công khai:

**Đoán.** Một endpoint đăng nhập không giới hạn sẽ nhận cả nghìn lần thử mật khẩu
mỗi giây. argon2 (file 08) làm mỗi lần chậm còn ~100 ms, có giúp — nhưng mười lần
mỗi giây, chạy mãi, vẫn duyệt được rất nhiều mật khẩu phổ biến.

**Tiêu tiền.** `POST /api/predict` gọi OpenAI. Có xác thực hay không, một vòng lặp
nhắm vào nó vẫn biến credit của bạn thành trò vui của người khác. Không mất gì,
không báo động — chỉ có hoá đơn.

Cả hai đều là bài toán số lượng. Câu trả lời là làm cho số lượng trở nên đắt.

## Ý tưởng

**Rate limiting** giới hạn số lần một hành động được thử, theo từng danh tính,
trong từng khoảng thời gian. Ba cách đáng biết:

### Cửa sổ cố định (fixed window)
Đếm theo mốc đồng hồ: 5 lần mỗi phút, reset ở đầu mỗi phút.
Đơn giản; có ca biên — 5 lần lúc 10:00:59 và 5 lần lúc 10:01:00 là 10 lần trong hai
giây.

### Cửa sổ trượt (sliding window)
Đếm liên tục theo "60 giây gần nhất". Không có đỉnh ở biên; sổ sách nhiều hơn chút.

### Xô token (token bucket)
Một xô chứa N token, được nạp lại đều đặn; mỗi request tiêu một token. Cho phép
**bùng** ngắn hạn nhưng chặn mức trung bình dài hạn — thường là hành vi dễ chịu
nhất cho con người, vốn hay thao tác theo đợt.

Với endpoint đăng nhập thì chưa cái nào đủ, vì ở đó bạn cần thứ gắt hơn.

## Đăng nhập cần cách đối xử riêng

Đăng nhập thất bại nên đắt lên theo **cấp số nhân**, và bộ đếm nên gắn với **tài
khoản**, không chỉ với IP:

```
  lần 1–3   → không chờ
  lần 4     → khoá 1 phút
  lần 5     → khoá 2 phút
  lần 6     → khoá 4 phút
  lần 7     → khoá 8 phút
  …
  đăng nhập thành công → bộ đếm về 0
```

Mười lần đoán khiến kẻ tấn công mất hàng giờ. Bạn gõ nhầm hai lần thì không thấy
gì. **Bất đối xứng, nghiêng về phía bạn** — đúng tính chất mà file 08 đã chỉ ra là
dấu hiệu của một biện pháp tốt.

Lưu trên dòng của người dùng:

```
users
  … failed_attempts INT   locked_until TIMESTAMP
```

### Theo tài khoản *và* theo IP

Mỗi cái một mình đều có lỗ:

- **Chỉ theo tài khoản** → kẻ tấn công có danh sách email sẽ thử một mật khẩu lên
  hàng nghìn tài khoản (*password spraying*) và không bao giờ chạm giới hạn của
  tài khoản nào.
- **Chỉ theo IP** → một botnet rải các lần thử qua hàng nghìn địa chỉ.

Bạn chỉ có một tài khoản, nên giới hạn theo tài khoản là biện pháp chịu lực chính.
Theo IP vẫn giúp giảm nhiễu.

> ### Cái bẫy khoá tài khoản
> Một cơ chế khoá tài khoản mà ai cũng kích được bằng cách đoán bừa chính là một
> **tấn công từ chối dịch vụ nhắm vào bạn**: ai đó spam email của bạn bằng mật
> khẩu sai và bạn không bao giờ đăng nhập được. Cách giảm nhẹ: giới hạn thời gian
> khoá (ví dụ 15 phút thay vì vĩnh viễn), và đừng bao giờ khoá khi mật khẩu *đúng*
> — nếu thông tin đăng nhập đúng thì cho vào và reset bộ đếm. Tự khoá mình ra khỏi
> tài khoản của chính mình là một lỗi có thật, không phải giả định.

## Đừng để lộ phần nào sai

```
  ❌ "Không có tài khoản với email này"   ← xác nhận email nào tồn tại
  ❌ "Sai mật khẩu"                       ← xác nhận email này CÓ tồn tại
  ✅ "Email hoặc mật khẩu không đúng"      ← không nói gì cả
```

Thời gian phản hồi cũng vậy: nếu email không tồn tại thì trả lời tức thì, còn mật
khẩu sai thì tốn 100 ms argon2, *thời gian* sẽ tiết lộ điều mà câu chữ đã giấu.
Hãy chạy phép so hash với một hash giả ngay cả khi người dùng không tồn tại, để hai
nhánh tốn thời gian như nhau.

Với một người dùng thì chuyện này ít quan trọng hơn so với sản phẩm công cộng —
nhưng nó tốn một dòng và là thói quen đáng có.

## Bảo vệ các endpoint tốn tiền

Rate limiting để giữ tiền có hình dạng khác: **hạn mức theo ngày cho mỗi người
dùng**, không phải giới hạn theo giây.

| Endpoint | Tốn gì | Hạn mức hợp lý |
|---|---|---|
| `/api/predict`, `/api/positions/exit-advisor` | 1–2 lệnh gọi model | ~50/ngày |
| `/api/report` | 1 lệnh gọi model, đôi khi kèm web search | ~30/ngày |
| `/api/feed`, `/api/watchlist` | một lượt đọc database | rộng rãi hoặc không giới hạn |

Đặt hạn mức cao hơn hẳn mức dùng thật, để nó vô hình cho tới khi có chuyện. Đây là
**cầu dao**, không phải ngân sách.

Trong codebase đã có một cơ chế họ hàng đáng nhắc:
`MAX_CLASSIFICATIONS_PER_RUN` chặn chi phí cho mỗi lần chạy pipeline. Cùng tinh
thần, khác tầng.

## Cài ở đâu

**Trong ứng dụng**, không phải ở proxy. App biết *người dùng nào* đang gọi; Caddy
chỉ thấy một IP, mà theo IP là biện pháp yếu hơn.

Với một container duy nhất, bộ đếm trong tiến trình là đủ — không cần Redis. Lưu ý
một điều kiện: nó reset khi restart, và không dùng được nếu chạy nhiều tiến trình.
Cả hai đều chấp nhận được ở đây và nên ghi lại để người đọc sau biết đó là một
quyết định chứ không phải sơ suất.

> **Lỗi khiến rate limiting âm thầm vô dụng:** đứng sau reverse proxy, mọi request
> trông như đến từ `127.0.0.1` trừ khi bạn đọc `X-Forwarded-For`. Giới hạn theo IP
> khi đó gom cả Internet vào một xô — hoặc chặn tất cả cùng lúc, hoặc (thường gặp
> hơn) không bao giờ kích hoạt. Hãy kiểm tra bằng điện thoại chạy 4G, không chỉ
> bằng localhost.

## Trả về cái gì

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 120
```

`429` là mã trạng thái đúng. `Retry-After` cho client biết điều để chờ tử tế thay
vì dội liên tục. App nên hiện "thử quá nhiều lần, hãy đợi hai phút" thay vì một lỗi
chung chung — nếu không bạn sẽ tưởng server hỏng và bấm lại, làm kéo dài thời gian
khoá.

## Trong StockPulse

Là Phase 5 của kế hoạch, và là **việc cuối cùng phải có trước khi công khai**:

- Đăng nhập: `failed_attempts` + `locked_until` trên bảng `users`, giãn theo cấp số
  nhân, tối đa 15 phút, reset khi thành công.
- Thông báo lỗi đồng nhất và thời gian phản hồi đồng nhất cho sai-email và
  sai-mật-khẩu.
- Hạn mức theo ngày cho mỗi người dùng trên các endpoint gọi model, đặt rộng rãi.
- Bộ đếm trong tiến trình; không Redis.
- Tôn trọng `X-Forwarded-For` để giới hạn theo IP có ý nghĩa khi đứng sau Caddy.

## Hiểu lầm thường gặp

**"argon2 chậm rồi nên khỏi cần rate limiting."** Hash chậm bảo vệ *database sau
khi bị lộ*. Rate limiting bảo vệ *endpoint đang chạy*. Hai kiểu tấn công khác nhau,
cần cả hai.

**"Rate limiting sẽ làm phiền tôi."** Đặt ngưỡng cao hơn mức dùng thật một bậc độ
lớn. Bạn sẽ không bao giờ chạm tới; kẻ tấn công chạm ngay lập tức.

**"Ra mắt xong rồi thêm."** Ra mắt là lúc các lượt dò bắt đầu. Đây là phần bắt buộc
phải có ngay ngày đầu.

**"Khoá tài khoản vĩnh viễn sau 5 lần sai."** Thế thì ai biết email của bạn cũng
khoá vĩnh viễn được bạn. Hãy giới hạn thời lượng.

## Nhớ điều này

- Làm mỗi lần thử đắt lên theo **cấp số nhân**; reset khi thành công.
- Theo tài khoản *và* theo IP — mỗi cái bù điểm mù của cái kia.
- Đừng tiết lộ *phần nào* sai, cả trong câu chữ **lẫn** trong thời gian phản hồi.
- Đứng sau proxy, phải đọc `X-Forwarded-For` nếu không giới hạn theo IP là vô
  nghĩa.
