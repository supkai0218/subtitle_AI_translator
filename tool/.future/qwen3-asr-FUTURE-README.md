# Qwen3-ASR GPU 版本說明

## 為何無法使用

RTX 3050 Ti Laptop GPU 只有 **4 GB VRAM**，無法執行 Qwen3-ASR-0.6B 模型。

### 錯誤訊息

```
CUDA out of memory. Tried to allocate 14.49 GiB.
GPU 0 has a total capacity of 4.00 GiB of which 0 bytes is free.
```

### 原因分析

- Qwen3-ASR-0.6B 即使使用 FP16 量化，推理時仍需大量 VRAM
- 模型在生成文字時需要 K/V cache，音頻越長，記憶體需求越大
- 14.49 GB 的分配需求來自於長音頻的 cache 配置

### VRAM 需求參考

| 模型/模式 | VRAM 需求 |
|-----------|-----------|
| Qwen3-ASR-0.6B BF16 | ~3-4 GB（會爆） |
| Qwen3-ASR-0.6B FP16 | ~3-4 GB（會爆） |
| Qwen3-ASR-0.6B INT8 | ~1.5-2 GB（理論上可跑，但實際仍爆） |
| Qwen3-ASR-0.6B INT4 | ~0.8-1.2 GB（理論上可跑） |

**結論**：4 GB VRAM 在理論上足夠，但實際推理時的 memory fragmentation 和 cache 配置導致 OOM。

---

## 解決方案

### 方案一：使用 OpenVINO CPU 版本（目前採用）

使用 QwenASRMiniTool 的 OpenVINO INT8 量化模型：

- **VRAM 需求**：0 GB（純 CPU）
- **RAM 需求**：~4-6 GB
- **工具位置**：`tool/qwen3-asr-ov.py`
- **模型位置**：`D:\Python\QwenASR\ov_models\qwen3_asr_int8`

### 方案二：升級 GPU

如要使用 GPU 版本，需要：
- RTX 3060 (12GB) 或更高
- 或 RTX 4070 Ti Super (16GB)

### 方案三：使用 faster-whisper

faster-whisper 對低 VRAM 優化更好，4 GB 可用 medium 模型。

---

## 模型路徑變更

### HuggingFace 模型（原 qwen-asr 使用）

**新路徑**：`D:\Python\QwenASR\Huggingface_model`

```
D:\Python\QwenASR\Huggingface_model\
├── models--Qwen--Qwen3-ASR-0.6B\
└── models--Qwen--Qwen3-ForcedAligner-0.6B\
```

**使用方式**：在批次檔中設定環境變數
```batch
set HF_HOME=D:\Python\QwenASR\Huggingface_model
```

### OpenVINO 模型（目前使用）

**路徑**：`D:\Python\QwenASR\ov_models`

```
D:\Python\QwenASR\ov_models\
├── qwen3_asr_int8\           # 0.6B INT8 模型
├── qwen3_asr_1p7b_kv_int8\  # 1.7B INT8 模型
├── silero_vad_v4.onnx        # VAD 模型
└── diarization\              # 說話者分離模型
```

---

## 未來使用方式

當有足夠 VRAM 的 GPU 時，可使用 `.future/` 目錄中的 GPU 版本：

### 啟動 GPU 版本

```batch
cd tool/.future
qwen3-asr-gui.bat
```

批次檔已設定 `HF_HOME=D:\Python\QwenASR\Huggingface_model`，會自動使用已下載的模型。

### 必要環境

1. **Conda 環境**：`qwen_asr`
2. **Python**：3.10+
3. **PyTorch**：CUDA 版本
4. **套件**：`pip install qwen-asr`
5. **VRAM**：建議 8GB 以上

### 手動設定環境

```bash
# 啟動環境
conda activate qwen_asr

# 設定模型路徑（可選，批次檔已自動設定）
set HF_HOME=D:\Python\QwenASR\Huggingface_model

# 執行
python qwen3-asr-gui.py
```

---

## 檔案位置對照

| 檔案 | 位置 | 狀態 |
|------|------|------|
| GPU 版 CLI | `tool/.future/qwen3-asr.py` | 待刪除（需 GPU） |
| GPU 版 GUI | `tool/.future/qwen3-asr-gui.py` | 待刪除（需 GPU） |
| CPU 版 CLI | `tool/qwen3-asr-ov.py` | 使用中 |
| CPU 版啟動 | `tool/qwen3-asr-ov.bat` | 使用中 |
| HuggingFace 模型 | `D:\Python\QwenASR\Huggingface_model` | 保留 |
| OpenVINO 模型 | `D:\Python\QwenASR\ov_models` | 使用中 |

---

## 參考連結

- Qwen3-ASR 模型：https://huggingface.co/Qwen/Qwen3-ASR-0.6B
- QwenASRMiniTool：https://github.com/dseditor/QwenASRMiniTool
- OpenVINO：https://docs.openvino.ai/
- faster-whisper：https://github.com/SYSTRAN/faster-whisper
