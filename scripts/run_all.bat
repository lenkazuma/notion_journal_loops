@echo off
REM ============================================================
REM Notion Journal Loops - Run Full Pipeline (Windows Batch)
REM ============================================================

echo [Notion Journal Loops] Starting full pipeline...

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [INFO] Virtual environment activated.
)

REM Run full pipeline (steps 1-7)
python -m src.pipeline.run_pipeline --from-step 1 --to-step 7 %*

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Pipeline failed with exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo [SUCCESS] Pipeline complete! Check data\outputs\ for results.
pause
