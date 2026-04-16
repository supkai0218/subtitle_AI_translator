# Qwen3-ASR-OV (OpenVINO CPU 版本)

基於 QwenASRMiniTool 專案，使用 OpenVINO INT8 量化模型進行 CPU 推理的 ASR 工具。

## 目錄結構

```
tool/
├── qwen3-asr-ov.py          # CLI 主程式
├── qwen3-asr-ov.bat         # 啟動腳本（自動建立 conda 環境）
├── processor_numpy.py        # 音頻處理模組（Mel 特徵提取、BPE 解碼）
└── prompt_template.json      # Prompt 範本

D:\Python\QwenASR\           # QwenASRMiniTool 資源（需自行下載）
├── ov_models/               # OpenVINO 量化模型
│   ├── qwen3_asr_int8/      # 0.6B INT8 模型
│   │   ├── audio_encoder_model.xml
│   │   ├── decoder_model.xml
│   │   └── ...
│   ├── qwen3_asr_1p7b_kv_int8/  # 1.7B INT8 模型（可選）
│   ├── silero_vad_v4.onnx   # VAD 語音偵測模型
│   └── diarization/         # 說話者分離模型（可選）
```

## 依賴套件

| 套件 | 版本 | 用途 |
|------|------|------|
| openvino | >=2024.0.0 | OpenVINO 推理引擎 |
| onnxruntime | >=1.17.0 | VAD ONNX 推理 |
| librosa | >=0.10.0 | 音頻載入與處理 |
| opencc-python-reimplemented | >=0.1.7 | 簡體→繁體轉換 |
| soundfile | >=0.12.0 | 音頻檔案讀寫 |
| numpy | >=1.24.0 | 數值計算 |

## 模型路徑

### 自動偵測路徑

程式會自動搜尋以下路徑：
1. `D:\Python\QwenASR\ov_models`
2. `D:\Python\QwenASR\source\ov_models`

### 手動指定

```bash
qwen3-asr-ov.py -i audio.mp3 -o output.srt -m "你的模型路徑"
```

### 模型下載

若無模型，需從 QwenASRMiniTool 下載：
1. 至 https://github.com/dseditor/QwenASRMiniTool 下載 EXE 版本
2. 首次執行會自動下載模型（約 1.2 GB）
3. 模型會存放於 `QwenASR\ov_models\` 目錄

## 使用方式

### 基本用法

```bash
# 單一檔案
qwen3-asr-ov.bat -i "audio.mp3" -o "output.srt"

# 指定語言
qwen3-asr-ov.bat -i "audio.mp3" -o "output.srt" -l Japanese

# 批次處理資料夾
qwen3-asr-ov.bat -i "Y:\Music" -o "D:\Output"
```

### 完整參數

| 參數 | 說明 |
|------|------|
| `-i, --input` | 輸入音頻檔案或資料夾（必填） |
| `-o, --output` | 輸出 SRT 檔案路徑或資料夾 |
| `-l, --language` | 語言（預設自動偵測） |
| `-m, --model-dir` | 模型目錄路徑 |
| `-t, --threads` | CPU 執行緒數（0=自動） |
| `--diarize` | 啟用說話者分離 |
| `--speakers N` | 指定說話者人數 |
| `--list-languages` | 顯示支援的語言列表 |
| `-v, --verbose` | 顯示詳細資訊 |

### 支援語言

```
Chinese, English, Japanese, Korean, French, German,
Spanish, Portuguese, Russian, Arabic, Thai, Vietnamese,
Indonesian, Malay, Cantonese
```

## conda 環境

啟動腳本會自動管理 `qwen_ov` conda 環境：

```bash
# 首次執行：自動建立環境並安裝套件
qwen3-asr-ov.bat -i audio.mp3

# 以後執行：直接使用已建立的環境
qwen3-asr-ov.bat -i audio.mp3
```

### 手動管理環境

```bash
# 建立環境
conda create -n qwen_ov python=3.11 -y

# 安裝套件
conda activate qwen_ov
pip install openvino onnxruntime librosa opencc-python-reimplemented soundfile numpy
```

## 輸出格式

產出的 SRT 字幕檔：
- 編碼：UTF-8
- 格式：標準 SRT 時間軸格式
- 文字：繁體中文（如模型輸出簡體，自動轉換）

### 範例

```
1
00:00:00,512 --> 00:00:01,785
です

2
00:00:01,865 --> 00:00:02,465
で
```

## 技術細節

### 處理流程

1. **VAD 語音偵測**：使用 Silero VAD 找出語音區段
2. **音頻分段**：將長音頻切分為 ≤30 秒的片段
3. **特徵提取**：使用 numpy 計算 Mel spectrogram
4. **ASR 推理**：OpenVINO INT8 量化模型推理
5. **文字解碼**：BPE decode 轉換為文字
6. **繁簡轉換**：OpenCC 簡→繁轉換

### VRAM / 記憶體需求

| 模式 | VRAM | RAM |
|------|------|-----|
| OpenVINO CPU | 0 GB | ~4-6 GB |
| GPU (Vulkan) | 需 GPU | - |

## 疑難排解

### 找不到模型

```
[ERROR] 找不到 Qwen3-ASR OpenVINO 模型！
```

解決：確認模型路徑存在，或使用 `-m` 參數指定：
```bash
qwen3-asr-ov.bat -i audio.mp3 -m "D:\你的模型路徑"
```

### 模型路徑含中文

建議避免使用含中文的路徑，或將模型放在純英文路徑下。

### conda 環境問題

刪除並重新建立環境：
```bash
conda env remove -n qwen_ov
qwen3-asr-ov.bat
```

## 整合至主專案

此工具可作為獨立 CLI 使用，或整合進字幕翻譯流程：

```
影片檔 → 音頻提取 → qwen3-asr-ov.py (音轉文字) → srt_separator.py
       → 字幕處理 → AI 翻譯 → 輸出字幕檔
```

## 參考資源

- QwenASRMiniTool GitHub: https://github.com/dseditor/QwenASRMiniTool
- OpenVINO: https://docs.openvino.ai/
- Silero VAD: https://github.com/snakers4/silero-vad
