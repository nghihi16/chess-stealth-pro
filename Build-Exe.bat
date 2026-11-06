@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [*] Đang biên dịch ChessPro.exe và KeyGen.exe...
"C:\Users\Windows\AppData\Local\Programs\Python\Python314\Scripts\pyinstaller.exe" --noconfirm --onefile --noconsole --distpath "." --workpath ".\build" --specpath ".\build" -n "ChessPro" "main.py"
"C:\Users\Windows\AppData\Local\Programs\Python\Python314\Scripts\pyinstaller.exe" --noconfirm --onefile --noconsole --distpath "." --workpath ".\build" --specpath ".\build" -n "KeyGen" "keygen.py"
echo [+] Hoàn tất! File ChessPro.exe và KeyGen.exe đã sẵn sàng trong thư mục hiện tại.
pause
