@echo off

:: Überprüfung, ob Python installiert ist
python --version
if %errorlevel% neq 0 (
    echo Python not found. Please install Python.
    start https://www.python.org/downloads/
    exit /b
) else (
    echo Python found.
)

:: Installieren der erforderlichen Pakete aus requirements.txt
pip install -r requirements.txt
@echo requirements installed

pause
