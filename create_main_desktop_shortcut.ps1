$wshell = New-Object -ComObject WScript.Shell
$sc = $wshell.CreateShortcut("C:\Users\Windows\Desktop\Chess Stealth PRO.lnk")
$sc.TargetPath = "C:\Users\Windows\Desktop\ChessStealthPro\ChessPro.exe"
$sc.WorkingDirectory = "C:\Users\Windows\Desktop\ChessStealthPro"
$sc.IconLocation = "C:\Users\Windows\Desktop\ChessStealthPro\app_icon.ico,0"
$sc.Description = "Chess Stealth PRO - Universal AI Engine Assist"
$sc.Save()
Write-Host "Main Desktop shortcut created!"
