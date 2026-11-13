@echo off
REM Sestaví HeliController.exe (okno + tray) a připraví složku pro instalátor.
REM Spusť v složce pc\. Výsledek: dist\HeliController\HeliController.exe

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onedir --noconsole --name HeliController ^
  --add-data "config.json;." tray_app.py

copy /Y config.json dist\HeliController\config.json >nul
echo.
echo Hotovo: dist\HeliController\HeliController.exe
echo Instalator: otevri installer.iss v Inno Setup (vyzaduje vendor\ViGEmBus_Setup.exe).
pause
