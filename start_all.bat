@echo off
rem Mo FoxProfile, cho API san sang roi mo bot, moi cai 1 cua so.
cd /d "%~dp0"
rem Chi cai dat khi Python dang dung (xem _python.bat) chua co thu vien cua FoxProfile + bot.
call "%~dp0_python.bat"
"%PY%" -c "import flet, telebot, camoufox" >nul 2>&1
if errorlevel 1 (
  echo Chua cai dat. Dang chay setup.bat...
  call setup.bat || exit /b 1
)
rem Thanh phan nao dang chay (vd watchdog apps_monitor da mo) thi bo qua, khong mo ban trung.
"%PY%" "%~dp0updater.py" running foxprofile >nul 2>&1 || start "Muse2tele_FoxProfile" cmd /c "%~dp0start_foxprofile.bat"
echo Dang cho FoxProfile khoi dong (http://127.0.0.1:8090)...
:wait
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8090/api/v1/health | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 goto wait
"%PY%" "%~dp0updater.py" running bot >nul 2>&1 || start "Muse2tele_Bot" cmd /k "%~dp0start_bot.bat"
"%PY%" "%~dp0updater.py" running autopost >nul 2>&1 || start "Muse2tele_AutoPost" cmd /k "%~dp0start_autopost.bat"
echo Da mo FoxProfile, bot va tu dong dang bai. Co the dong cua so nay.
