@echo off
rem Bot Telegram <-> muse.ai. Can FoxProfile dang chay (start_foxprofile.bat).
call "%~dp0_python.bat"
rem Dang chay roi (mo tu start_all / watchdog) thi khong mo them ban thu 2.
"%PY%" "%~dp0updater.py" running bot >nul 2>&1 && (echo bot dang chay, bo qua. & exit /b 0)
cd /d "%~dp0muse_telebot"
"%PY%" muse_telebot.py
