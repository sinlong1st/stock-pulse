# 01 — Vấn đề

## Triệu chứng

Điện thoại tụt pin nhanh hơn trước. Nguyên nhân là Tailscale: một VPN client phải
giữ **kết nối thường trực** để duy trì đường hầm, nghĩa là định kỳ đánh thức sóng
ngay cả khi bạn không dùng app. Đây không phải lỗi cấu hình để chỉnh cho hết —
một đường hầm mở liên tục thì tốn pin. Đó là cái giá của thiết kế này.

Mục tiêu: **vào được backend bằng HTTPS thông thường, không cần VPN trên điện
thoại.**

## Cái bẫy

Đây là chỗ hầu hết mọi người sai, và đáng để đọc chậm.

Tailscale trông như một việc ("làm sao điện thoại tới được server"). Thực ra nó
đang làm **hai** việc chẳng liên quan gì nhau:

```
        ┌──────────────────── TAILSCALE ────────────────────┐
        │                                                    │
        │  VIỆC 1: KHẢ NĂNG KẾT NỐI (reachability)           │
        │  Điện thoại tìm và kết nối được tới droplet dù      │
        │  droplet không mở cổng công khai nào.               │
        │                                                    │
        │  VIỆC 2: XÁC THỰC (authentication)                 │
        │  Chỉ thiết bị trong mạng riêng của bạn mới "tồn      │
        │  tại" dưới góc nhìn của server. Người khác thậm      │
        │  chí không thể thử kết nối.                         │
        │                                                    │
        └────────────────────────────────────────────────────┘
```

"Thay Tailscale bằng domain + HTTPS" chỉ thay **việc 1**. Việc 2 lặng lẽ biến
mất. Đó là toàn bộ mối nguy của dự án này.

## Vì sao việc 2 quan trọng hơn bạn tưởng

`app/main.py` hiện có **11 route hoàn toàn không xác thực**:

```
GET  /                  trang dashboard HTML
GET  /alerts            cảnh báo của bạn
GET  /evaluation        trang độ chính xác
POST /run               chạy cả pipeline      ← tốn tiền OpenAI
POST /classify          phân loại tin         ← tốn tiền OpenAI
POST /report            tạo bản tin           ← tốn tiền OpenAI
POST /alerts/send       gửi tin Telegram      ← về điện thoại bạn
POST /evaluate          chấm điểm dự đoán
POST /evaluate/digest   gửi tổng kết Telegram
GET  /collect           lấy tin tức
GET  /health            trạng thái
```

Chúng được viết khi cách duy nhất để tới server là đã ở sẵn trong mạng riêng của
bạn — nên câu hỏi "ai đang gọi?" có câu trả lời hiển nhiên: *bạn*. Giả định đó
đang **gánh** toàn bộ phần an toàn, và nó sắp bị gỡ đi.

Chỉ cần mở cổng 443 → 8000 mà không làm gì thêm, mọi route trên thành URL công
khai. Kẻ tấn công không cần dữ liệu của bạn để gây thiệt hại — gọi `POST /run`
trong vòng lặp là đủ để đội hoá đơn OpenAI.

## "Nhưng có ai biết URL của tôi đâu"

Họ sẽ biết, trong vài giờ, và không phải vì ai đó quan tâm tới bạn.

Khi bạn xin chứng chỉ HTTPS, nó được công bố vào **Certificate Transparency
log** — bản ghi công khai, chỉ-thêm, của mọi chứng chỉ từng được cấp. Nó tồn tại
vì lý do chính đáng (để một CA không thể lén cấp chứng chỉ cho ngân hàng của
bạn), nhưng hệ quả phụ là **mọi hostname mới đều được thông báo cho cả thế giới
ngay khi vừa ra đời**. Bot theo dõi các log này và tự động dò tên mới.

Chi tiết ở [04-certificates-and-trust.md](04-certificates-and-trust.md). Tạm thời
nhớ: giấu địa chỉ không phải là một biện pháp bảo mật. Hãy lên kế hoạch như thể
địa chỉ đang được dán trên bảng quảng cáo — vì thực tế đúng là vậy.

## Cần đúng những gì trước khi bỏ VPN

| Việc Tailscale đang làm | Thay bằng | Ở file |
|---|---|---|
| Khả năng kết nối | Domain + TLS + reverse proxy | 02–05 |
| Xác thực | Login: mật khẩu, token, session | 07–11 |
| "Chỉ thiết bị của tôi mới được thử" | Rate limiting + đóng các route hở | 12–13 |

**Thứ tự rất quan trọng.** Xác thực xong *trước*, rồi mới công khai — không bao
giờ ngược lại. Ràng buộc đó là lý do các phase trong kế hoạch được xếp như vậy.

## Hiểu lầm thường gặp

**"Có HTTPS là an toàn rồi."** HTTPS bảo vệ *đường truyền* — không ai đọc hay sửa
được dữ liệu trên đường. Nó không nói gì về *ai được phép gửi request*. Một API
công khai với TLS hoàn hảo và không có login thì được mã hoá hoàn hảo và mở toang
hoàn toàn.

**"Dự án cá nhân thôi, ai thèm."** Đúng là không ai thèm — và đó chính xác là mô
hình mối đe doạ. Bạn sẽ không bị tấn công bởi một người *chọn* bạn. Bạn sẽ bị quét
bởi bot tấn công tất cả mọi thứ, không phân biệt, mãi mãi.

**"Để sau rồi thêm auth."** "Để sau" nghĩa là có một khoảng thời gian server vừa
công khai vừa mở. Không có phiên bản nào của việc này mà công khai đi trước.

## Nhớ điều này

- Tailscale đang làm hai việc, và chỉ một việc là dễ thấy.
- 11 route hiện chỉ được bảo vệ bởi mạng, không phải bởi code.
- Xác thực trước, công khai sau. Luôn luôn theo thứ tự đó.
