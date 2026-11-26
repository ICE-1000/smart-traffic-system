@echo off
cd /d %~dp0
call .venv\Scripts\activate
uvicorn backend.app.main:app --port 8000
pause
