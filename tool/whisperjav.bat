@echo off
chcp 65001 >nul
setlocal

set "WHISPERJAV_DIR=D:\Python\whisperjav"
set "VENV_PYTHON=%WHISPERJAV_DIR%\.venv\Scripts\python.exe"
set "HF_HOME=D:\Python\whisperjav\hub\huggingface"
set "TORCH_HOME=D:\Python\whisperjav\hub\torch"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Venv not found: %VENV_PYTHON%
    pause
    exit /b 1
)

echo ========================================
echo WhisperJAV CLI (CUDA 12.8)
echo ========================================
echo.
echo [OK] HF_HOME: %HF_HOME%
echo [OK] TORCH_HOME: %TORCH_HOME%
"%VENV_PYTHON%" -c "import torch; print('[OK] torch:', torch.__version__, '| CUDA:', torch.cuda.is_available())"
"%VENV_PYTHON%" -c "import whisperjav; print('[OK] WhisperJAV:', whisperjav.__version__)"
echo.

cd /d "%~dp0"
echo Running whisperjav %*
echo.
"%WHISPERJAV_DIR%\.venv\Scripts\whisperjav.exe" %*

pause