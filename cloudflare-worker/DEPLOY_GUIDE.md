# Hướng dẫn Setup Cloudflare Worker cho Chess Stealth Pro

Cloudflare Worker sẽ chạy độc lập, giữ bí mật `SECRET_KEY` trên máy chủ Cloudflare (miễn phí 100.000 lượt request/ngày), giúp **chống hack F12 và chống tạo key giả 100%**.

---

## Cách 1: Setup trực tiếp trên Website Cloudflare (Khuyên dùng - Nhanh nhất, không cần cài gì)

1. Đăng nhập vào [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Chọn menu bên trái: **Workers & Pages** $\to$ bấm nút **Create application** (hoặc **Create Worker**).
3. Đặt tên Worker: `chess-stealth-key-api` $\to$ bấm **Deploy**.
4. Bấm nút **Edit code** (hoặc **Quick edit**).
5. Xóa hết code mặc định, copy toàn bộ nội dung file [`src/index.js`](file:///C:/Users/Windows/ChessStealthPro/cloudflare-worker/src/index.js) dán vào.
6. Bấm **Save and deploy**.
7. Bạn sẽ nhận được link Worker của mình, ví dụ:
   `https://chess-stealth-key-api.<your-name>.workers.dev`

---

## Cách 2: Deploy bằng dòng lệnh Terminal (Wrangler)

Mở PowerShell tại thư mục `cloudflare-worker`:
```powershell
cd C:\Users\Windows\ChessStealthPro\cloudflare-worker
npx wrangler login
npx wrangler deploy
```
Trình duyệt sẽ mở ra để bạn xác thực tài khoản Cloudflare, sau đó Worker sẽ tự động được đưa lên mạng.

---

## Cách cấu hình Link đích trên Web rút gọn (Link4m, ShrinkMe, LootLabs,...)

Giả sử link Cloudflare Worker của bạn là: `https://chess-stealth-key-api.<your-name>.workers.dev`

### 1. Link Rút Gọn Bước 1:
- Khi tạo link rút gọn Bước 1 trên Link4m (hoặc ShrinkMe), bạn đặt **Link đích (Destination URL)** trỏ về:
  `https://chess-stealth-key-api.<your-name>.workers.dev/callback/step1?provider=link4m`
  *(Thay `provider=link4m` bằng `shrinkme`, `lootlabs` tương ứng)*

### 2. Link Rút Gọn Bước 2:
- Khi tạo link rút gọn Bước 2, bạn đặt **Link đích (Destination URL)** trỏ về:
  `https://chess-stealth-key-api.<your-name>.workers.dev/callback/step2`

---

## Cơ chế bảo mật hoạt động như thế nào?
1. Người dùng vượt Bước 1 $\to$ Web rút gọn dẫn về Worker `/callback/step1`.
2. Worker ký một **Token HMAC bí mật có hạn 20 phút** và tự động redirect người dùng về GitHub Pages ở Bước 2.
3. Người dùng vượt Bước 2 $\to$ Web rút gọn dẫn về Worker `/callback/step2`.
4. Worker kiểm tra Token hợp lệ $\to$ Worker tự sinh mã `FREE24H-...` và chuyển hướng về Web để hiển thị Key cho người dùng.
5. Người dùng xem mã nguồn web hay mở F12 **hoàn toàn không thấy Secret** và **không thể tự tạo Key giả**.
