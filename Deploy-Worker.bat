@echo off
chcp 65001 >nul
cd /d "%~dp0cloudflare-worker"
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
    echo     Trang Quan Tri: https://chess-stealth-key-api.quitworks.workers.dev/admin
    echo ============================================================
)
pause
