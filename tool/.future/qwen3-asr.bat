@echo off
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "CONDA_ROOT="
set "PYTHON_EXE="

REM ========================================
REM HuggingFace 模型路徑設定
REM ========================================
set "HF_HOME=D:\Python\QwenASR\Huggingface_model"

REM Find Miniconda
if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=%USERPROFILE%\miniconda3"
) else if exist "C:\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=C:\miniconda3"
) else if exist "D:\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=D:\miniconda3"
) else if exist "D:\Python\.app\miniconda3\Scripts\conda.exe" (
    set "CONDA_ROOT=D:\Python\.app\miniconda3"
)

if "%CONDA_ROOT%"=="" (
    echo [ERROR] Miniconda not found
    exit /b 1
)

REM Find Python in qwen_asr environment
if exist "%CONDA_ROOT%\envs\qwen_asr\python.exe" (
    set "PYTHON_EXE=%CONDA_ROOT%\envs\qwen_asr\python.exe"
) else (
    echo [ERROR] qwen_asr environment not found
    exit /b 1
)

echo [INFO] HuggingFace 模型路徑: %HF_HOME%

REM Run CLI
cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" qwen3-asr.py %*
