@echo off
chcp 65001 >nul
setlocal

REM ========================================
REM Qwen3 ASR GUI Launcher
REM ========================================

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
    echo Please install from: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

REM Find Python in qwen_asr environment
if exist "%CONDA_ROOT%\envs\qwen_asr\python.exe" (
    set "PYTHON_EXE=%CONDA_ROOT%\envs\qwen_asr\python.exe"
) else (
    echo [ERROR] qwen_asr environment not found
    echo.
    echo Please create the environment first:
    echo   conda create -n qwen_asr python=3.10 -y
    echo   conda activate qwen_asr
    echo   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    echo   pip install qwen-asr
    pause
    exit /b 1
)

REM Check PyTorch
"%PYTHON_EXE%" -c "import torch" 2>nul
if errorlevel 1 (
    echo [ERROR] PyTorch not installed in qwen_asr environment
    echo.
    echo Please activate the environment and install:
    echo   conda activate qwen_asr
    echo   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    echo   pip install qwen-asr
    pause
    exit /b 1
)

REM Set CUDA memory config to reduce fragmentation
set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

REM Show GPU info
echo [INFO] HuggingFace 模型路徑: %HF_HOME%
"%PYTHON_EXE%" -c "import torch; print('[OK] GPU:', torch.cuda.get_device_name(0))"

REM Launch GUI
cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" qwen3-asr-gui.py