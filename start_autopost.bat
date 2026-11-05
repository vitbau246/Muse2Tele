@echo off
rem Tu dong dang bai len fanpage / TikTok cho cac profile da tick tren dashboard FoxProfile.
rem Can FoxProfile dang chay. Bo file vao Videos\downloads\social_queue\(ten profile)\ de dang.
call "%~dp0_python.bat"
rem Dang chay roi (mo tu start_all / watchdog) thi khong mo them ban thu 2.
"%PY%" "%~dp0updater.py" running autopost >nul 2>&1 && (echo autopost dang chay, bo qua. & exit /b 0)
cd /d "%~dp0social_post"
"%PY%" auto_post.py
