@echo off
rem Tu dong dang bai len fanpage / TikTok cho cac profile da tick tren dashboard FoxProfile.
rem Can FoxProfile dang chay. Bo file vao Videos\downloads\social_queue\(ten profile)\ de dang.
call "%~dp0_python.bat"
cd /d "%~dp0social_post"
"%PY%" auto_post.py
