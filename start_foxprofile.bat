@echo off
rem FoxProfile (app desktop + API http://127.0.0.1:8090). Du lieu profile nam o foxprofile\data.
call "%~dp0_python.bat"
rem Dang chay roi (mo tu start_all / watchdog) thi khong mo them ban thu 2.
"%PY%" "%~dp0updater.py" running foxprofile >nul 2>&1 && (echo foxprofile dang chay, bo qua. & exit /b 0)
rem Cong rieng 8090 de khong trung FoxProfile dung chung (8000). .env cua Muse2tele co the ghi de.
if not defined FOXPROFILE_API_HOST set "FOXPROFILE_API_HOST=127.0.0.1"
if not defined FOXPROFILE_API_PORT set "FOXPROFILE_API_PORT=8090"
rem Khong dung "if errorlevel" o day: lenh "updater.py running" o tren tra 1 khi chua chay -> se thoat nham.
if not exist "%~dp0foxprofile\data\" (mkdir "%~dp0foxprofile\data" || exit /b 1)
cd /d "%~dp0foxprofile\data" || exit /b 1
"%PY%" ..\repo\src\main.py
