@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [*] Đang biên dịch ChessPro.exe và KeyGen.exe với Luxury Icon mới...
"C:\Users\Windows\AppData\Local\Programs\Python\Python314\Scripts\pyinstaller.exe" --noconfirm --distpath "." --workpath ".\build" "ChessPro.spec"
"C:\Users\Windows\AppData\Local\Programs\Python\Python314\Scripts\pyinstaller.exe" --noconfirm --distpath "." --workpath ".\build" "KeyGen.spec"
copy /y "ChessPro.exe" "%USERPROFILE%\Desktop\ChessStealthPro\ChessPro.exe" >nul 2>&1
copy /y "KeyGen.exe" "%USERPROFILE%\Desktop\ChessStealthPro\KeyGen.exe" >nul 2>&1
echo [+] Hoàn tất! File ChessPro.exe và KeyGen.exe đã sẵn sàng với Icon Luxury mới.
pause
