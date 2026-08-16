# 06 — Cổng (port) và binding

## Vấn đề

Một server có một địa chỉ IP nhưng chạy nhiều chương trình. Khi một gói tin tới,
chương trình nào nhận?

Và một câu hỏi sắc hơn dành cho chúng ta: droplet của bạn chạy FastAPI với 11
route không xác thực, trên một máy có IP công khai, đang nối Internet. Vì sao đó
chưa phải thảm hoạ?

Câu trả lời nằm ở một dòng cấu hình, và rất đáng hiểu cho chính xác.

## Ý tưởng

**Port** là một con số (0–65535) xác định kết nối này dành cho chương trình nào
trên máy. Địa chỉ thật ra là `IP : port`.

| Port | Thường là |
|---|---|
| 22 | SSH |
| 80 | HTTP |
| 443 | HTTPS |
| 8000 | thứ bạn đang phát triển (thói quen của uvicorn) |

Khi một chương trình bắt đầu lắng nghe, nó **bind** vào một địa chỉ và một port.
Phần địa chỉ là phần người ta hay đọc lướt, và nó quyết định mọi thứ:

```
  bind 127.0.0.1:8000   ← "chỉ kết nối xuất phát từ CHÍNH máy này"
  bind 0.0.0.0:8000     ← "kết nối từ MỌI giao diện mạng"
```

`127.0.0.1` (**localhost**, giao diện loopback) là một mạng ảo không bao giờ chạm
tới sợi cáp nào. Gói tin từ bên ngoài không thể tới đó — kernel sẽ không định
tuyến. Đây không phải một luật firewall có thể cấu hình sai; đây là tính chất của
giao diện.

```
   ┌──────────────── droplet ────────────────┐
   │                                          │
   │  loopback 127.0.0.1  ← ngoài không bao giờ với tới
   │     └── app của bạn :8000                │
   │                                          │
   │  eth0 công khai 164.90.х.х ← Internet tới được
   │     ├── sshd :22                         │
   │     └── (hiện chưa có gì khác)           │
   │                                          │
   └──────────────────────────────────────────┘
```

## Trong StockPulse — dòng đang cứu bạn

`docker-compose.yml`:

```yaml
    ports:
      # Chỉ bind localhost — vào dashboard bằng SSH tunnel:
      #   ssh -L 8000:127.0.0.1:8000 user@your-server
      - "127.0.0.1:8000:8000"
```

Tiền tố `127.0.0.1:` đó là lý do `POST /run` hiện chưa phải một cái nút vô danh
trên Internet. Xoá chín ký tự ấy đi, mọi route không xác thực ở file 01 lập tức
công khai.

Docker khiến việc này đặc biệt dễ sai: `- "8000:8000"` — dạng viết trong hầu hết
hướng dẫn — bind vào **mọi** giao diện. Tệ hơn, Docker tự viết luật iptables riêng,
nên một port đã publish có thể đi vòng qua luật UFW mà bạn tưởng đang bảo vệ mình.
Đã có người phơi cả database ra Internet theo cách này trong khi nhìn vào firewall
thấy ghi "deny".

### Hiện tại bạn vào bằng cách nào

Hai cách, không cách nào công khai:

- **Tailscale** — điện thoại nằm trong mạng riêng, nên `127.0.0.1` trên droplet
  tới được qua giao diện của Tailscale.
- **SSH tunnel** — `ssh -L 8000:127.0.0.1:8000 user@droplet` chuyển tiếp cổng 8000
  của laptop qua kết nối SSH. Dashboard hiện ở `http://localhost:8000` trong
  trình duyệt. Không phơi gì ra ngoài; SSH đã xác thực bạn rồi.

Cách thứ hai đáng nhớ: đó là câu trả lời trung thực cho các trang dashboard HTML
(`/`, `/alerts`, `/evaluation`) ngay cả sau khi công khai. Chúng là công cụ cho lập
trình viên; cứ để trên localhost mãi mãi và mở tunnel khi thật sự cần.

### Sau khi đổi

```
   Internet ──► :443 Caddy ──► 127.0.0.1:8000 app
                :80  Caddy (chuyển hướng + thử thách ACME)
                :22  sshd
```

App **vẫn** bind localhost. Caddy ở cùng máy nên tới được; người khác thì không.
Chỉ Caddy phơi ra ngoài, và việc của Caddy đúng là để phơi ra ngoài.

## Firewall, nói ngắn

Firewall (`ufw` trên Ubuntu) là lớp thứ hai: kể cả khi thứ gì đó lỡ bind vào
`0.0.0.0`, firewall vẫn từ chối được kết nối.

```bash
sudo ufw default deny incoming
sudo ufw allow 22        # đừng tự khoá mình ra ngoài — làm cái này TRƯỚC
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

Hai cơ chế độc lập cùng làm một việc không phải thừa thãi — đó là **phòng thủ
nhiều lớp**. Binding là bảo đảm; firewall là lưới an toàn cho ngày ai đó đổi
binding mà không nghĩ kỹ.

**Lưu ý Docker lần nữa:** port publish của Docker chèn luật iptables có thể đi vòng
qua ufw. Bảo vệ đáng tin cho container là địa chỉ bind, không phải firewall.

## Hiểu lầm thường gặp

**"Port 8000 hiếm, ai mà dò ra."** Quét toàn bộ 65.535 port trên một host mất vài
giây. Mọi port đều bị tìm thấy, liên tục. Không có port nào "hiếm", chỉ có kỳ vọng
sai.

**"Firewall bảo vệ container Docker của tôi."** Thường là không — Docker can thiệp
iptables trực tiếp và có thể vượt luật ufw. Hãy bind `127.0.0.1` và đừng trông cậy
vào firewall cho container.

**"Bind 0.0.0.0 cũng được, app có auth rồi."** Có thể, nhưng bạn vừa biến một bảo
đảm thành một giả định. Bind hẹp lại và để auth làm lớp *thứ hai*, không phải lớp
duy nhất.

**"localhost và 127.0.0.1 là hai thứ khác nhau."** Cùng một thứ; `localhost` là
cái tên phân giải ra `127.0.0.1` (và `::1` với IPv6 — đôi khi chuyện này gây phiền
khi một bên bind cái này còn bên kia kết nối cái kia).

## Nhớ điều này

- Địa chỉ là `IP : port`, và **nửa IP trong lệnh bind quyết định ai tới được bạn**.
- `127.0.0.1:8000:8000` trong compose hiện đang bảo vệ bạn nhiều hơn bất cứ dòng
  code nào.
- Cứ để app trên localhost mãi mãi. Chỉ phơi proxy ra ngoài.
