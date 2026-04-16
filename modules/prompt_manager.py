#v0.89.04 新增環境變數替換功能，設定檔中可使用 ${VAR_NAME} 來引用環境變數
#V0.87.06 支援Prompt_manager模板資料庫路徑設定

import json
from typing import Dict, List, Optional
from pathlib import Path

try:
    from .settings_path import resolve_settings_file, substitute_env_vars
except ImportError:  # pragma: no cover - 兼容直接執行模組
    try:
        from modules.settings_path import resolve_settings_file, substitute_env_vars  # type: ignore
    except ImportError:  # pragma: no cover - 若無法匯入則保持 None
        resolve_settings_file = None  # type: ignore

class PromptManager:
    """Prompt模板管理器"""
    
    def __init__(self, settings_paths: Optional[Dict] = None):
        self.settings_paths = dict(settings_paths) if settings_paths else {}
        self.settings_path = self._resolve_prompt_templates_path()
        # 將回填後的路徑寫回，以便後續程式取得實際使用位置
        if "prompt_templates_db" not in self.settings_paths:
            self.settings_paths["prompt_templates_db"] = str(self.settings_path)
        self._debug_log("init", {
            "settings_keys": list(self.settings_paths.keys()),
            "selected_path": str(self.settings_path)
        })
        self.system_templates = {}
        self.user_templates = {}
        self.load_templates()
    
    def load_templates(self):
        """從設定檔載入模板"""
        try:
            settings_file = Path(self.settings_path)
            self._debug_log("load_templates:start", {
                "resolved_path": str(settings_file.resolve()),
                "exists": settings_file.exists()
            })
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.system_templates = data.get("system_templates", {})
                    self.user_templates = data.get("user_templates", {})
            else:
                self._create_default_templates()
                self.save_templates()
        except Exception as e:
            print(f"載入Prompt模板失敗: {e}")
            self._create_default_templates()
    
    def save_templates(self):
        """儲存模板到設定檔"""
        try:
            settings_file = Path(self.settings_path)
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            self._debug_log("save_templates:start", {
                "resolved_path": str(settings_file.resolve()),
                "parent_exists": settings_file.parent.exists()
            })
            
            data = {
                "system_templates": self.system_templates,
                "user_templates": self.user_templates
            }
            
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"儲存Prompt模板失敗: {e}")
    
    def get_system_prompt(self, template_name: str = "default", **kwargs) -> str:
        """取得系統提示詞"""
        template = self.system_templates.get(template_name, self.system_templates.get("default", ""))
        return self._replace_variables(template, kwargs)
    
    def get_user_prompt(self, template_name: str = "default", **kwargs) -> str:
        """取得使用者提示詞"""
        template = self.user_templates.get(template_name, self.user_templates.get("default", ""))
        return self._replace_variables(template, kwargs)
    
    def add_system_template(self, name: str, template: str):
        """新增系統提示詞模板"""
        self.system_templates[name] = template
        self.save_templates()
    
    def add_user_template(self, name: str, template: str):
        """新增使用者提示詞模板"""
        self.user_templates[name] = template
        self.save_templates()
    
    def delete_template(self, template_type: str, name: str) -> bool:
        """刪除模板"""
        try:
            if template_type == "system" and name in self.system_templates:
                del self.system_templates[name]
                self.save_templates()
                return True
            elif template_type == "user" and name in self.user_templates:
                del self.user_templates[name]
                self.save_templates()
                return True
            return False
        except Exception:
            return False
    
    def get_template_list(self, template_type: str) -> List[str]:
        """取得模板列表"""
        if template_type == "system":
            return list(self.system_templates.keys())
        elif template_type == "user":
            return list(self.user_templates.keys())
        return []
    
    def validate_prompt(self, prompt_text: str) -> tuple[bool, str]:
        """驗證提示詞格式"""
        if not prompt_text or not prompt_text.strip():
            return False, "提示詞不能為空"
        
        # 檢查變數格式
        import re
        variables = re.findall(r'\{([^}]+)\}', prompt_text)
        invalid_vars = [var for var in variables if not var.replace('_', '').isalnum()]
        
        if invalid_vars:
            return False, f"無效的變數名稱: {', '.join(invalid_vars)}"
        
        return True, "提示詞格式正確"
    
    def get_available_variables(self) -> Dict[str, str]:
        """取得可用的變數列表"""
        return {
            "source_lang": "來源語言",
            "target_lang": "目標語言",
            "translation_style": "翻譯風格",
            "video_type": "影片類型",
            "character_info": "角色資訊",
            "subtitle_content": "字幕內容",
            "context_info": "上下文資訊",
            "line_number": "行號",
            "total_lines": "總行數"
        }
    
    def _replace_variables(self, template: str, variables: Dict[str, str]) -> str:
        """替換模板中的變數"""
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result
    
    def _create_default_templates(self):
        """建立預設模板"""
        self.system_templates = {
            "default": """你是一位專業的{source_lang}到{target_lang}字幕翻譯專家。請遵循以下原則：

1. 保持原文的語氣和情感
2. 考慮字幕的時間限制，翻譯要簡潔明瞭
3. 保持上下文的連貫性
4. 對於專有名詞，請保持一致性
5. 如果遇到文化特定的內容，請適當本地化
6. 翻譯風格：{translation_style}

請按照原文的編號順序回傳翻譯結果，每行一個翻譯，保持相同的編號格式。""",
            
            "anime": """你是一位專精動畫字幕翻譯的專家，擅長{source_lang}到{target_lang}的翻譯。請遵循以下原則：

1. 保持動畫角色的語氣特色和個性
2. 適當保留日式表達方式，但要讓中文觀眾容易理解
3. 對於動畫特有的擬聲詞和感嘆詞，請適當本地化
4. 保持對話的節奏感和情感張力
5. 專有名詞（人名、地名、技能名）請保持一致性
6. 翻譯風格：{translation_style}

請按照原文的編號順序回傳翻譯結果，每行一個翻譯，保持相同的編號格式。""",
            
            "drama": """你是一位專精日劇字幕翻譯的專家，擅長{source_lang}到{target_lang}的翻譯。請遵循以下原則：

1. 保持日劇特有的情感表達和文化背景
2. 適當保留敬語和社會階層的語言差異
3. 對於日本文化特有的概念，請適當解釋或本地化
4. 保持對話的自然流暢，符合中文表達習慣
5. 注意角色關係和社會地位在語言上的體現
6. 翻譯風格：{translation_style}

請按照原文的編號順序回傳翻譯結果，每行一個翻譯，保持相同的編號格式。""",
            
            "technical": """你是一位專精技術內容翻譯的專家，擅長{source_lang}到{target_lang}的翻譯。請遵循以下原則：

1. 保持技術術語的準確性和一致性
2. 對於專業概念，使用標準的中文技術用語
3. 保持邏輯清晰，條理分明
4. 如遇到新技術或概念，請適當保留原文並加註解釋
5. 確保翻譯的專業性和可讀性
6. 翻譯風格：{translation_style}

請按照原文的編號順序回傳翻譯結果，每行一個翻譯，保持相同的編號格式。"""
        }
        
        self.user_templates = {
            "default": """請翻譯以下字幕內容：

上下文資訊：
- 影片類型：{video_type}
- 角色設定：{character_info}
- 來源語言：{source_lang}
- 目標語言：{target_lang}

待翻譯字幕：
{subtitle_content}

請注意前後文的連貫性，並確保翻譯自然流暢。請按照原文的編號順序回傳翻譯結果。""",
            
            "batch": """請翻譯以下批次字幕內容：

翻譯要求：
- 來源語言：{source_lang}
- 目標語言：{target_lang}
- 影片類型：{video_type}
- 角色設定：{character_info}
- 翻譯風格：{translation_style}

待翻譯字幕（共{total_lines}行）：
{subtitle_content}

請保持上下文連貫性，確保翻譯自然流暢。請按照原文的編號順序回傳翻譯結果，每行一個翻譯。""",
            
            "context_aware": """請翻譯以下字幕內容，特別注意上下文的連貫性：

上下文資訊：
{context_info}

當前翻譯段落：
- 影片類型：{video_type}
- 角色設定：{character_info}
- 來源語言：{source_lang}
- 目標語言：{target_lang}

待翻譯字幕：
{subtitle_content}

請根據上下文資訊，確保翻譯的連貫性和一致性。請按照原文的編號順序回傳翻譯結果。""",
            
            "quality_focus": """請以高品質標準翻譯以下字幕內容：

品質要求：
1. 語言自然流暢，符合{target_lang}表達習慣
2. 保持原文的情感色彩和語氣
3. 確保專有名詞的一致性
4. 適當的文化本地化
5. 字幕長度適中，便於閱讀

翻譯資訊：
- 影片類型：{video_type}
- 角色設定：{character_info}
- 來源語言：{source_lang}
- 目標語言：{target_lang}

待翻譯字幕：
{subtitle_content}

請按照原文的編號順序回傳高品質的翻譯結果。"""
        }

    def _debug_log(self, phase: str, payload: Optional[Dict] = None):
        try:
            info = payload or {}
            info_str = ", ".join(f"{k}={v}" for k, v in info.items()) if info else ""
            print(f"[PromptManager][DEBUG] phase={phase}{' ' + info_str if info_str else ''}")
        except Exception:
            pass

    def _resolve_prompt_templates_path(self) -> Path:
        """決定Prompt模板資料庫實際路徑，並確保為絕對路徑"""
        # 1. 優先使用呼叫端提供的設定
        candidate = self.settings_paths.get("prompt_templates_db") if self.settings_paths else None
        if candidate:
            return self._normalize_path(candidate)

        # 2. 從設定檔讀取 paths.prompt_templates_db（若有）
        settings_path = self._load_path_from_settings_file()
        if settings_path:
            return settings_path

        # 3. 回退到專案內建預設路徑
        return self._normalize_path("json/prompt_templates.json")

    def _load_path_from_settings_file(self) -> Optional[Path]:
        if resolve_settings_file is None:
            return None
        try:
            settings_file = resolve_settings_file()
            with open(settings_file, "r", encoding="utf-8") as f:
                settings_data = substitute_env_vars(json.load(f))
            candidate = settings_data.get("paths", {}).get("prompt_templates_db")
            if candidate:
                resolved = self._normalize_path(candidate)
                self._debug_log("resolve_from_settings", {
                    "settings_file": str(settings_file),
                    "resolved_path": str(resolved)
                })
                return resolved
        except Exception as e:  # pragma: no cover - 設定檔缺失時僅記錄
            self._debug_log("resolve_from_settings:error", {"error": str(e)})
        return None

    def _normalize_path(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            project_root = Path(__file__).resolve().parent.parent
            path = (project_root / path).resolve()
        return path
    
    def export_templates(self, file_path: str) -> bool:
        """匯出模板到檔案"""
        try:
            data = {
                "system_templates": self.system_templates,
                "user_templates": self.user_templates,
                "export_info": {
                    "version": "1.0",
                    "export_time": str(Path().cwd())
                }
            }
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"匯出模板失敗: {e}")
            return False
    
    def import_templates(self, file_path: str, overwrite: bool = False) -> bool:
        """從檔案匯入模板"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if overwrite:
                self.system_templates = data.get("system_templates", {})
                self.user_templates = data.get("user_templates", {})
            else:
                # 合併模板，不覆蓋現有的
                for name, template in data.get("system_templates", {}).items():
                    if name not in self.system_templates:
                        self.system_templates[name] = template
                
                for name, template in data.get("user_templates", {}).items():
                    if name not in self.user_templates:
                        self.user_templates[name] = template
            
            self.save_templates()
            return True
        except Exception as e:
            print(f"匯入模板失敗: {e}")
            return False
