# 05 — Reverse proxy

## Vấn đề

App của bạn là `uvicorn` chạy FastAPI ở cổng 8000, nói HTTP thường. Để ra Internet
công khai, nó cần thêm:

- nói HTTPS ở cổng 443, kèm chứng chỉ
- xin và gia hạn chứng chỉ đó
- chuyển hướng ai vào cổng 80
- lý tưởng nữa: nén response, giới hạn kích thước request, ghi log, khởi động lại
  mà không rớt kết nối

Bạn *có thể* bắt uvicorn tự làm TLS. Khi đó bạn đang chạy việc gia hạn chứng chỉ
bên trong tiến trình Python, phải restart API để nạp chứng chỉ mới, và sẽ viết lại
toàn bộ vào ngày bạn thêm dịch vụ thứ hai.

## Ý tưởng

Một **reverse proxy** đứng phía trước, gánh phần việc hướng ra mạng, rồi chuyển
HTTP thường vào trong.

```
                    ┌─────────── droplet của bạn ─────────┐
                    │                                      │
  Điện thoại ─HTTPS─►  Caddy :443        App :8000         │
                    │  ├ kết thúc TLS     (chỉ 127.0.0.1)  │
                    │  ├ chứng chỉ                          │
                    │  └ proxy ──HTTP thường──►             │
                    │                                      │
                    └──────────────────────────────────────┘
```

"Forward proxy" đứng trước *client* (kiểu bộ lọc web của công ty). "Reverse proxy"
đứng trước *server*. Cùng cơ chế, ngược chiều.

**Tách bạch trách nhiệm** mới là lý lẽ thật sự. App của bạn biết về cổ phiếu và vị
thế. Nó không nên biết gì về chứng chỉ. Mỗi bên thay được mà không đụng bên kia.

## Chọn cái nào

| | Caddy | nginx + certbot | Cloudflare Tunnel |
|---|---|---|---|
| Cấu hình cho việc này | ~5 dòng | ~30 dòng + cron | dashboard + daemon |
| HTTPS | tự động | cài tay, cron gia hạn | tự động |
| Cần mở cổng | 80, 443 | 80, 443 | **không cổng nào** |
| Mặc định stream SSE | có | **không — buffer** | có |
| Phụ thuộc thêm | không | không | Cloudflare nằm trên đường request |

**Caddy** là lựa chọn khuyến nghị: HTTPS tự động là tính năng gốc chứ không phải
phần cắm thêm, và cấu hình đúng là thế này:

```caddyfile
stockpulse.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

Chừng đó lấy chứng chỉ, gia hạn, chuyển hướng HTTP→HTTPS, và proxy. Không phải
viết gì thêm.

**nginx** là chuẩn mực ngành và cực mạnh; bị loại ở đây vì gia hạn chứng chỉ trở
thành một cron job riêng có thể hỏng âm thầm, và vì vấn đề buffer bên dưới.

**Cloudflare Tunnel** thật sự hấp dẫn — một daemon trên droplet quay *ra ngoài* để
kết nối tới Cloudflare, nên bạn **không mở cổng vào nào cả** và IP droplet vẫn kín.
Đánh đổi là có bên thứ ba nằm trên đường request. Đáng cân nhắc lại nếu domain của
bạn bắt đầu bị dò nhiều.

## Cái bẫy buffer — cái này cắn StockPulse rất cụ thể

StockPulse có streaming. Report, Predict và Exit Advisor đều gửi **Server-Sent
Events** để màn hình loading hiện tiến độ thật:

```
event: stage   data: {"stage":"prices"}      ← ở giây 0.6
event: stage   data: {"stage":"news"}        ← ở giây 1.3
event: result  data: {...}                   ← ở giây 11
```

Một proxy có **buffer** sẽ gom toàn bộ response rồi mới chuyển đi. Khi đó mọi
stage cùng về một lúc, ở cuối. Tính năng không báo lỗi — nó chỉ lặng lẽ hết là
tính năng.

- **nginx mặc định buffer response được proxy.** Phải đặt `proxy_buffering off;`
  cho các route streaming.
- **Caddy mặc định stream** và flush ngay với `text/event-stream`.
- **Tailscale** (hiện tại) flush đúng, nên streaming đang chạy tốt.

Codebase đã gửi sẵn header `X-Accel-Buffering: no`, vốn **chỉ dành cho nginx**. Nó
đang vô tác dụng và được giữ lại đúng để nếu sau này đặt nginx thì chạy ngay. Xem
`STREAMING_AND_PROXIES.md`.

**Hãy kiểm tra thật, bằng công cụ thật:**

```bash
curl -N https://stockpulse.yourdomain.com/api/report/stream -H "Authorization: Bearer …"
```

Các event phải hiện ra **đúng lúc chúng xảy ra**. Nếu chúng đổ về cùng lúc ở cuối,
bạn đang bị buffer.

> Một cái bẫy chính dự án này từng dính: `TestClient` của FastAPI **buffer toàn bộ
> response**, nên mọi event đều báo cùng một mốc thời gian. Nó không đo được
> streaming và sẽ "pass" trong cả hai trường hợp. Dùng `curl -N` hoặc
> `httpx.stream` thật.

## Vài việc khác proxy nên làm

- **Giới hạn kích thước request** — chặn body (ví dụ 1 MB) để không ai upload vài
  GB.
- **Timeout** — nhưng nhớ request exit-advisor mất ~20 giây một cách chính đáng,
  nên đừng đặt read timeout quá gắt.
- **Header bảo mật** — bật HSTS khi đã yên tâm với HTTPS.
- **IP thật của client** — Caddy đặt `X-Forwarded-For`; bộ rate limit (file 13)
  cần nó, nếu không mọi request đều trông như đến từ `127.0.0.1` và giới hạn theo
  IP lặng lẽ vô hiệu.

Cái cuối là lỗi thật sự phổ biến: rate limiting nhìn thì đúng, test thì chạy, mà
lên production thì chẳng giới hạn ai cả.

## Trong StockPulse

- Caddy chạy **trên host**, không phải trong container.
- `docker-compose.yml` vẫn bind `127.0.0.1:8000` — container không bao giờ tới
  thẳng được (xem file 06).
- Sau khi chuyển, kiểm tra lại SSE bằng `curl -N` **trước khi** tắt Tailscale.
  Đừng phỏng đoán; lịch sử dự án này là một danh sách các phỏng đoán đã sai.

## Hiểu lầm thường gặp

**"Có reverse proxy là an toàn."** Nó kết thúc TLS và áp được giới hạn. Nó không
biết bạn là ai — đó là việc của xác thực, và proxy sẽ vui vẻ chuyển tiếp một
`POST /run` vô danh.

**"Thêm proxy làm chậm đáng kể."** Dưới một mili giây trên cùng máy. Không đáng kể
so với một lệnh gọi AI 20 giây.

**"Tôi cho uvicorn nghe thẳng 443."** Rồi bạn tự ôm việc gia hạn chứng chỉ trong
Python, restart API để nạp chứng chỉ mới, và làm lại tất cả khi thêm dịch vụ thứ
hai.

## Nhớ điều này

- Proxy lo phần mạng; app lo phần nghiệp vụ. Đừng để bên nào học việc của bên kia.
- **Buffer giết SSE trong im lặng.** Caddy mặc định ổn; nginx thì không. Kiểm tra
  bằng `curl -N`, đừng bao giờ bằng `TestClient`.
- Đứng sau proxy, rate limit theo IP cần `X-Forwarded-For`, nếu không nó chẳng
  giới hạn gì.
