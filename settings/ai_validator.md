# AI Validator v2 操作說明書

## 版本歷史

| 版本 | 日期 | 異動 |
|------|------|------|
| v0.89.04 | 2026-04-18 | 新增 `empty_threshold` 參數，預設 1%，可由 GUI 調控 |
| v0.89.03 | 2026-04-18 | 優化驗證邏輯，區分「可修復」與「需重翻」的錯誤 |
| v0.88.02 | - | 加強驗證功能容錯能力 |

---

## 模組概述

`TranslationValidator` 是翻譯流程中的獨立驗證層，負責：
1. 解析 API 原始響應
2. 修復格式問題
3. 驗證翻譯結果的正確性

**設計原則：** 分離關注點 — AI 翻譯 (`AITranslator`) 專門處理 API 通信，驗證器專門處理格式修復與驗證。

---

## 核心類別

### ValidationStatus 枚舉

定義驗證結果的四种狀態：

| 狀態 | 意義 | caller 行為 |
|------|------|-------------|
| `PASS` | 驗證完全通過 | 接受結果 |
| `ACCEPTABLE` | 驗證通過，但有少量空白翻譯（<50%） | 接受結果，記錄警告 |
| `FIXABLE` | 格式問題已自動修復（如缺序號、空白翻譯） | 接受結果，記錄提示 |
| `RETRY_NEEDED` | 需要重新翻譯（結構性錯誤） | 触发重试逻辑 |

---

## 驗證流程（4步驟）

```
validate_response(response, expected_count)
    │
    ├── 步驟1: 檢查響應是否為空
    │           └─ 空 → RETRY_NEEDED
    │
    ├── 步驟2: _parse_response() ── 解析響應格式
    │           ├─ JSON 格式解析
    │           └─ 編號格式解析（支援 "1. "、"1:"、"51:"）
    │
    ├── 步驟3: _repair_format() ── 修復格式問題
    │           ├─ 補齊缺失的序號
    │           └─ 修正錯誤的序號
    │
    └── 步驟4: _validate_parsed_result() ── 驗證並分類錯誤
                ├─ 行數檢查
                ├─ 格式檢查（^\d+: 接受空白翻譯）
                └─ 空白翻譯比例檢查
```

---

## 回傳值格式

```python
validate_response(response: str, expected_count: int, empty_threshold: float = 0.01) -> Tuple[ValidationStatus, List[str], str]
```

| 位置 | 內容 |
|------|------|
| 第一項 | `ValidationStatus` 枚舉值 |
| 第二項 | 翻譯結果列表（格式：`"序號:內容"`） |
| 第三項 | 訊息文字 |

### empty_threshold 參數

- **類型**: `float`（0.0 ~ 1.0，代表 0% ~ 100%）
- **預設值**: `0.01`（1%）
- **用途**: 空白翻譯比例閾值。超過此比例則要求重翻（`RETRY_NEEDED`）。
- **GUI 控制**: 在 `AI翻譯編輯器` 對話框的翻譯參數區段，名为「Empty Translation Threshold」。

---

## 支援的 API 響應格式

### 1. JSON 格式
```json
{
  "translations": [
    {"translated": "翻譯內容1"},
    {"translated": "翻譯內容2"}
  ]
}
```

### 2. 編號格式（點號）
```
1. 翻譯內容1
2. 翻譯內容2
```

### 3. 編號格式（冒號）
```
1: 翻譯內容1
2: 翻譯內容2
51: 翻譯內容3
```

---

## 修復邏輯

### `_repair_format()` 修復規則

| 問題 | 修復方式 | 修復後狀態 |
|------|----------|------------|
| 無序號 | 自動添加 `1:`、`2:`、`3:`... | FIXABLE |
| 序號錯誤（如輸入51但應該是5） | 修正為正確序號 | FIXABLE |
| 空白翻譯（如 `"5:"`） | 保留空白，不填補 | ACCEPTABLE |

### 空白翻譯處理

- **空白比例 ≤ empty_threshold** → `ACCEPTABLE`（可接受，預設 1%）
- **空白比例 > empty_threshold** → `RETRY_NEEDED`（需要重翻）
- **空白但有正確序號（如 `"5:"`）** → `ACCEPTABLE`（非結構性錯誤）

---

## 錯誤分類決策樹

```
輸入: parsed_result, expected_count
                    │
                    ▼
        ┌───────────────────────┐
        │ 行數 = expected_count? │
        └───────────────────────┘
                │
        否──────┤──────是
        │              │
        ▼              ▼
  ┌─────────┐   ┌─────────────────┐
  │ < 50%?  │   │ 格式 = ^\d+:  ?  │
  └─────────┘   └─────────────────┘
        │              │
   是───┤     否───────┤──────是
   │    │      │              │
   ▼    ▼      ▼              ▼
FIXABLE RETRY  FIXABLE    ┌─────────────────┐
 (已補   (行數   (自動       │ 空白翻譯 > 50%? │
 空白)   嚴重     修復序號)  └─────────────────┘
               │              │
               │        否────┤──────是
               │        │            │
               │        ▼            ▼
               │    ACCEPTABLE   RETRY_NEEDED
               │     (少量空白)
               ▼
           ┌─────────────────┐
           │ 空白翻譯 > 50%? │
           └─────────────────┘
```

---

## 與 AITranslator 的互動

```
Caller (AITranslationWorker)
    │
    ├─→ AITranslator.translate_batch() ──→ API ──→ 原始響應字串
    │
    └─→ TranslationValidator.validate_response()
            │
            ├─ PASS/ACCEPTABLE/FIXABLE → 使用結果，流程繼續
            │
            └─ RETRY_NEEDED → 重新呼叫翻譯（最多 max_retries 次）
```

---

## 使用範例

```python
from modules.ai_validator import TranslationValidator, ValidationStatus

validator = TranslationValidator({"log_level": "INFO"})

status, translations, msg = validator.validate_response(
    response="1: 你好\n2: 謝謝",
    expected_count=2
)

if status == ValidationStatus.PASS:
    print("驗證通過")
elif status == ValidationStatus.ACCEPTABLE:
    print(f"有少量空白: {msg}")
elif status == ValidationStatus.FIXABLE:
    print(f"格式已修復: {msg}")
elif status == ValidationStatus.RETRY_NEEDED:
    print(f"需要重翻: {msg}")
```

---

## AITranslationWorker 重試邏輯

位置：`modules/ai_translation_editor_dialog.py`

```python
for attempt in range(max_retries):
    success, raw_response, error_msg = translator.translate_batch(...)

    if success:
        status, parsed, msg = validator.validate_response(raw_response, ...)

        # PASS、ACCEPTABLE、FIXABLE 都接受結果
        if status in (PASS, ACCEPTABLE, FIXABLE):
            self.translation_completed.emit(parsed)
            return
        else:
            # RETRY_NEEDED: 重試
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue

# 所有重試都失敗
self.error_occurred.emit("AI翻譯失敗")
```

---

## 日誌級別建議

| 場景 | 建議 log_level |
|------|----------------|
| 正式環境 | `WARNING` |
| 開發/除錯 | `DEBUG` |

DEBUG 模式下會輸出：
- 前 5 個格式錯誤的詳細資訊
- 空白翻譯的行號位置
- 長度異常警告

---

## 版本差異 (v1 vs v2)

| 項目 | v1 | v2 |
|------|----|----|
| 回傳類型 | `Tuple[bool, List, str]` | `Tuple[ValidationStatus, List, str]` |
| 空白翻譯 | 導致格式錯誤 → 重翻 | 接受為 ACCEPTABLE |
| 格式驗證 | `^\d+:.+`（內容不可為空） | `^\d+:`（內容可為空） |
| 重翻觸發 | 幾乎任何格式問題 | 僅結構性錯誤（行數嚴重不足、空白>閾值） |
| 空白閾值 | 固定 50% | **可調參數，預設 1%** |
