@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   CHESS STEALTH PRO - DONG BO TOAN BO HE THONG (ALL-IN-ONE)
echo ============================================================
echo.

echo ============================================================
echo [1/2] DONG BO GITHUB PAGES (Web Nhan Key)...
echo ============================================================
git add index.html
git diff-index --quiet HEAD || git commit -m "feat(web): update static key claim portal with polished UI/UX"
git push origin main
if %errorlevel% neq 0 (
    echo [!] Dong bo GitHub chua thanh cong. Vui long xem cua so xac thuc GitHub neu co.
) else (
    echo [+] GitHub Pages da dong bo thanh cong: https://nghihi16.github.io/chess-stealth-pro/
)

echo.
echo ============================================================
echo [2/2] TRIEN KHAI CLOUDFLARE WORKER...
echo ============================================================
cd /d "%~dp0cloudflare-worker"
call npx wrangler whoami 2>&1 | findstr /i "not authenticated" >nul
if %errorlevel% equ 0 (
    echo [*] Chua xac thuc Cloudflare. Dang mo trinh duyet...
    echo [*] Hay bam "Allow" / "Chap nhan" tren trang Cloudflare vua hien ra.
    call npx wrangler login
)
call npx wrangler deploy
if %errorlevel% neq 0 (
    echo [!] Cloudflare Worker deploy that bai!
) else (
    echo [+] Cloudflare Worker da cap nhat thanh cong!
    echo     Trang Admin: https://chess-stealth-key-api.quitworks.workers.dev/admin
)

echo.
echo ============================================================
echo HOAN TAT DONG BO HE THONG!
echo ============================================================
pause
