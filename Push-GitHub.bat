@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   CHESS STEALTH PRO - DONG BO GITHUB PAGES (TU DONG HOA)
echo ============================================================
echo.

echo [*] 1. Kiem tra va commit thay doi moi nhat cua index.html...
git add index.html
git diff-index --quiet HEAD || git commit -m "feat(web): update static key claim portal with polished UI/UX"

echo.
echo [*] 2. Dang dong bo len GitHub Pages (Fast-forward push)...
git push origin main

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo [!] DONG BO GITHUB CHUA HOAN TAT!
    echo.
    echo [*] Neu trinh duyet vua mo len hop thoai "Sign in to GitHub",
    echo     ban chi can bam "Sign in with your browser" va bam "Authorize".
    echo.
    echo [*] Hoac neu duoc hoi mat khau trong terminal:
    echo     Hay nhap Personal Access Token (PAT) cua GitHub.
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo [+] THANH CONG 100%!
    echo     Trang web GitHub Pages da duoc cap nhat truc tiep tai:
    echo     https://nghihi16.github.io/chess-stealth-pro/
    echo ============================================================
)

echo.
pause
