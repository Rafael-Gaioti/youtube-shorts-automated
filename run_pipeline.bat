@echo off
:: Wrapper script for n8n Hybrid Orchestration
echo [Autogravity] Starting Pipeline...
cd /d "c:\Users\gaiot\Projetos\shorts_cortes_ai"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found in %CD%
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\master_pipeline.py"
echo [Autogravity] Pipeline Finished.
