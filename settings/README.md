# 設定檔案說明

## 📋 初次使用

### 1. 複製範例檔案
```bash
# 在 settings 資料夾內執行
cp .example/settings.json.example settings.json
cp .example/AI_config.json.example AI_config.json
cp .example/AI_prompt.json.example AI_prompt.json
cp .example/filter_patterns.json.example filter_patterns.json
cp .example/markers_db.json.example markers_db.json
cp .example/prompt_templates.json.example prompt_templates.json
cp .example/prompt.json.example prompt.json
cp .example/.env.example .env
```

### 2. 編輯 `.env` 檔案
填入你的 API 金鑰：
```bash
OPENROUTER_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
# 等等...
```

### 3. 編輯 `settings.json`
修改本地路徑設定，替換 `${PROJECT_ROOT}` 為實際路徑

### 4. 編輯其他設定檔案
根據你的需求自訂翻譯配置、過濾規則等

---

## 📁 檔案說明

### `settings.json` - 主設定檔案
- **paths**: 各種工作資料夾路徑
- **ai_translation**: AI 翻譯的基礎設定
- **text_filter**: 文字過濾設定
- **raw_subtitle**: 原始字幕輸出設定
- **language**: 介面語言設定

### `AI_config.json` - API 提供商配置
- 定義多個 API 提供商和模型
- 每個模型可設定不同的翻譯參數
- 支援 OpenRouter、Anthropic 等提供商

### `AI_prompt.json` - AI 提示詞配置
- 主要的 system_prompt（系統指令）
- user_prompt_template（用戶提示詞模板）

### `filter_patterns.json` - 文字過濾規則
- **moan**: 喘息聲、呻吟聲過濾
- **custom**: 自訂過濾規則

### `markers_db.json` - 敏感詞標記資料庫
- 定義敏感詞彙的分類和標記
- 用於翻譯時取代直接表述

### `prompt_templates.json` - Prompt 模板庫
- 多種翻譯場景的系統和用戶提示詞
- 支援自訂翻譯風格

### `prompt.json` - AI 翻譯流程 Prompt
- 針對不同 AI 模型的特定翻譯指令
- 可設定多個版本供不同場景使用

### `.env` - 環境變數（機密）
- **勿提交到版本控制！**
- 存放所有 API 密鑰
- 由程式自動讀取

---

## 🔒 隱私說明

### 公開到 GitHub
✅ `.example` 資料夾內的所有檔案

### 本地保存（.gitignore 忽略）
❌ `settings.json`  
❌ `AI_config.json`  
❌ `AI_prompt.json`  
❌ `filter_patterns.json`  
❌ `markers_db.json`  
❌ `prompt.json`  
❌ `.env`

---

## 🚀 進階用法

### 環境變數替換
在設定檔中可使用 `${VAR_NAME}` 語法引用環境變數：
```json
{
    "paths": {
        "ai": "${PROJECT_ROOT}/temp/output"
    }
}
```

### 多 API 配置
在 `AI_config.json` 中定義多個 API 提供商，程式可動態切換

### 自訂 Prompt
編輯 `prompt.json` 為不同的 AI 模型調整翻譯指令

---

## ⚠️ 常見問題

**Q: 我應該提交 `settings.json` 到 GitHub 嗎？**  
A: 不應該。提交 `.example` 版本即可，讓用戶自行複製設定。

**Q: API Key 遺露了怎麼辦？**  
A: 立即更換金鑰，並在 Git 歷史中清除該提交。

**Q: 如何同時支援多個翻譯服務？**  
A: 在 `AI_config.json` 中定義多個 API 設定，程式可根據 `last_selected` 選擇預設服務。

---

## 📞 支援

如有問題，請參考專案的 README.md 或提交 Issue。
