@echo off
cd /d "%~dp0"
set "AI_MODE=ollama"
set "OLLAMA_MODEL=qwen3:8b"
"%~dp0.venv\Scripts\python.exe" "%~dp0server.py"
