@echo off
chcp 65001 >nul
set "BROWSER=C:\Users\Windows\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"
set "GCM_BROWSER=C:\Users\Windows\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"
cd /d "C:\Users\Windows\ChessStealthPro\cloudflare-worker"
echo ============================================================
echo   CHESS STEALTH PRO - CLOUDFLARE WORKER 1-CLICK DEPLOY
echo ============================================================
echo.
call npx wrangler whoami 2>&1 | findstr /i "not authenticated" >nul
if %errorlevel% equ 0 (
    echo [*] Chua xac thuc Cloudflare. Dang mo trinh duyet de dang nhap...
    echo [*] Vui long bam "Allow" / "Chap nhan" tren trang Cloudflare vua mo ra.
    call npx wrangler login
) else (
    echo [+] Da dang nhap Cloudflare san sang!
)
echo.
echo [*] Dang tai ma nguon len Cloudflare Worker...
call npx wrangler deploy
if %errorlevel% neq 0 (
    echo [!] Cloudflare Worker deploy that bai!
) else (
    echo.
    echo ============================================================
    echo [+] Trien khai hoan tat!
    echo     API Worker: https://chess-stealth-key-api.pubgclone123-vn.workers.dev
    echo ============================================================
)
pause
