@echo off
chcp 65001 >nul
cd /d "%~dp0cloudflare-worker"
echo ============================================================
echo   CHESS STEALTH PRO - CLOUDFLARE WORKER 1-CLICK DEPLOY
echo ============================================================
echo.
echo [*] Bắt đầu đăng nhập và triển khai Cloudflare Worker...
echo [*] Trình duyệt sẽ mở ra để bạn bấm xác nhận "Allow"...
echo.
call npx wrangler login
echo.
echo [*] Đang tải mã nguồn lên Cloudflare Worker...
call npx wrangler deploy
echo.
echo [+] Triển khai hoàn tất! Hãy copy link .workers.dev hiển thị ở trên.
echo ============================================================
pause
