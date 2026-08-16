# 11 — Lưu trữ an toàn trên thiết bị

## Vấn đề

Refresh token phải sống sót qua việc đóng app, khởi động lại điện thoại, và ba
mươi ngày trôi qua — nếu không bạn phải đăng nhập liên tục và thiết kế ở file 10
chẳng đem lại gì.

Nghĩa là nó phải được ghi xuống đâu đó trên điện thoại. Đó là một credential 30
ngày cho phép truy cập toàn bộ tài khoản. Cất ở đâu?

## Có những lựa chọn nào

| Lựa chọn | Thực chất là gì | Hợp cho credential? |
|---|---|---|
| Biến JS | RAM, đóng app là mất | Chỉ hợp access token |
| `AsyncStorage` | **File không mã hoá** trong sandbox của app | ❌ Không |
| `expo-secure-store` | **Keychain** (iOS) / **Keystore** (Android) | ✅ Có |
| File bạn tự ghi | Vẫn là file không mã hoá, thêm vài bước | ❌ Không |

Dòng giữa là cái bẫy, vì `AsyncStorage` là thứ mọi hướng dẫn đều dùng và nó chạy
hoàn hảo — cho tới ngày nó quan trọng.

## Vì sao AsyncStorage sai ở đây

`AsyncStorage` trên Android là một database SQLite trong thư mục riêng của app.
"Riêng" nghĩa là *app khác* không đọc được, nghe có vẻ đủ. Nhưng không đủ trong ba
tình huống:

- **Máy đã root hoặc jailbreak** — sandbox chỉ còn mang tính khuyến nghị khi đã có
  quyền root.
- **Sao lưu (backup)** — file có thể bị cuốn vào bản backup rồi nằm trên máy tính
  hoặc trên cloud.
- **Tiếp cận vật lý kèm công cụ phù hợp** — file không mã hoá vẫn là file không mã
  hoá.

Sandbox là **kiểm soát truy cập**, không phải mã hoá. Với "chế độ tối: bật" thì
hoàn hảo. Với một credential 30 ngày vào dữ liệu tài chính của bạn thì không đủ.

## Keychain / Keystore thêm được gì

Cả hai là dịch vụ của hệ điều hành, lưu bí mật ở dạng **đã mã hoá**, với khoá mà
bản thân app không bao giờ nhìn thấy.

**iOS Keychain** — kho mã hoá, có phần cứng hỗ trợ trên máy đời mới, kèm các lớp
accessibility quy định *khi nào* bí mật được đọc (ví dụ chỉ khi máy đang mở khoá).

**Android Keystore** — vật liệu khoá nằm trong phần cứng nếu có (TEE hoặc chip bảo
mật riêng). App nhờ hệ điều hành mã hoá/giải mã; khoá thô không bao giờ vào bộ nhớ
của app. `expo-secure-store` dùng nó để mã hoá giá trị trong
`EncryptedSharedPreferences`.

Tính chất quan trọng ở cả hai: **app của bạn không bao giờ giữ khoá mã hoá.** Xâm
nhập được file của app cũng không lấy được bí mật, vì khoá không nằm trong đó.

```
  AsyncStorage                    SecureStore
  ┌──────────────┐                ┌──────────────┐
  │ sandbox app  │                │ sandbox app  │
  │  data.db     │                │  khối dữ liệu│──┐
  │  "token123"  │← đọc được      │  đã mã hoá   │  │ giải mã qua OS
  └──────────────┘                └──────────────┘  │
                                  ┌──────────────┐  │
                                  │ Keychain /   │◄─┘
                                  │ Keystore     │  khoá không rời khỏi đây
                                  │ (phần cứng)  │
                                  └──────────────┘
```

### Tuỳ chọn: bắt buộc vân tay

SecureStore có thể chặn việc đọc sau một lần xác thực thiết bị:

```js
await SecureStore.setItemAsync('refresh', token, {
  requireAuthentication: true,
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});
```

Giờ token chỉ đọc được sau khi kiểm vân tay/khuôn mặt, và `THIS_DEVICE_ONLY` giữ
nó khỏi các bản backup nên không thể khôi phục sang máy khác.

Cần nói chính xác điều này làm gì: **sinh trắc học không xác thực bạn với
StockPulse.** Nó là cái cổng cục bộ trên một credential mà *mật khẩu* của bạn đã
tạo ra trước đó. Hữu ích — nghĩa là một chiếc điện thoại vừa mở khoá không tự động
giao ra token — nhưng dưới mắt server nó không phải yếu tố thứ hai.

## Cái giá: cái này cần build lại APK

`expo-secure-store` là **native module**. Nó không phải JavaScript, nên không thể
đi qua OTA.

> ⚠️ Mọi thứ khác trong dự án login này ship bằng `eas update` trong khoảng một
> phút. **Riêng dòng này cần một lần `eas build` đầy đủ** và cài APK mới, kèm tăng
> version trong `app.json`. Hãy gộp nó chung với các thay đổi native khác nếu bạn
> đang có. Xem `mobile/AGENTS.md`.

## Và cái bí mật bạn sắp bỏ đi

Hiện app ship kèm `EXPO_PUBLIC_API_TOKEN` nhúng sẵn bên trong.

Biến `EXPO_PUBLIC_*` được **biên dịch vào bundle JavaScript**. Ai tải APK về đều
trích ra được — giải nén, tìm bundle, tìm chuỗi. Không có cách làm rối nào cứu
được; code phải đọc được nó, nên ai cầm code là cầm bí mật.

Hiện tại chấp nhận được *chỉ vì* Tailscale khiến việc có token cũng vô nghĩa nếu
không ở trong mạng riêng. Làm ổ khoá duy nhất cho một endpoint công khai thì nó là
một mật khẩu dùng chung, giống nhau trên mọi bản cài, không bao giờ hết hạn.

**Sau dự án này app không ship theo bí mật nào cả.** Mật khẩu ở trong đầu bạn;
token được tạo riêng cho từng thiết bị và tự hết hạn. Đó mới là phần thưởng thật
sự — lớn hơn chuyện pin.

```
  TRƯỚC                               SAU
  APK chứa một API token              APK không chứa gì bí mật
  dùng chung vĩnh viễn                Keychain giữ token riêng
  ↓                                   theo thiết bị, có hạn, thu hồi được
  trích xuất được, không thu hồi      ↓
  (trừ khi build lại)                 thu hồi từng thiết bị từ server
```

## Trong StockPulse

- **Refresh token** → `expo-secure-store`, khoá `stockpulse.refresh`.
- **Access token** → chỉ trong bộ nhớ. Nó sống 15 phút; ghi ra đĩa thêm rủi ro mà
  không tiết kiệm gì.
- **Mật khẩu** → không lưu, ở đâu, dưới dạng nào.
- Đăng xuất: xoá khỏi SecureStore **và** gọi `/api/auth/logout` để server thu hồi
  dòng đó. Chỉ xoá cục bộ thì trong database vẫn còn một token hợp lệ.

## Hiểu lầm thường gặp

**"Sandbox nghĩa là app khác không đọc được, vậy là đã mã hoá."** Sandbox là kiểm
soát truy cập; mã hoá là mã hoá. Root, backup và công cụ điều tra đều đi vòng qua
sandbox.

**"Tôi tự mã hoá rồi mới bỏ vào AsyncStorage."** Thế khoá để đâu? Trong app — đúng
cái vấn đề bạn đang định giải. Keystore tồn tại chính vì khoá phải nằm ở nơi app
không đọc được.

**"Mở khoá bằng sinh trắc học là yếu tố thứ hai."** Nó là cổng cục bộ trên một
credential đã lưu. Server thấy một token hợp lệ trong cả hai trường hợp. Là phòng
thủ nhiều lớp hữu ích; không phải MFA.

**"Tôi làm rối code để giấu token."** Bạn khiến việc đó mất mười phút thay vì hai
phút. Bất cứ bí mật nào ship tới client đều đọc được bởi người cầm nó.

## Nhớ điều này

- `AsyncStorage` là **file không mã hoá**. Đừng bao giờ để credential vào đó.
- Keychain/Keystore giữ khoá mã hoá **bên ngoài app** — đó là toàn bộ ý nghĩa.
- SecureStore là native → **một lần build lại APK**, không phải OTA.
- Hãy giả định mọi bí mật bạn ship đều đọc được. Kết quả tốt nhất là không ship bí
  mật nào — và đó đúng là điều dự án này đạt được.
