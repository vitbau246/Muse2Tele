@echo off
rem FoxProfile (app desktop + API http://127.0.0.1:8090). Du lieu profile nam o foxprofile\data.
call "%~dp0_python.bat"
rem Cong rieng 8090 de khong trung FoxProfile dung chung (8000). .env cua Muse2tele co the ghi de.
if not defined FOXPROFILE_API_HOST set "FOXPROFILE_API_HOST=127.0.0.1"
if not defined FOXPROFILE_API_PORT set "FOXPROFILE_API_PORT=8090"
if not exist "%~dp0foxprofile\data\" mkdir "%~dp0foxprofile\data"
if errorlevel 1 exit /b 1
cd /d "%~dp0foxprofile\data"
if errorlevel 1 exit /b 1
"%PY%" ..\repo\src\main.py
