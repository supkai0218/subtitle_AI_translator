import json
import os
from pathlib import Path

class LanguageManager:
    """
    語言包管理類別，用於加載和切換應用程式的語言
    """
    
    def __init__(self):
        self.current_language = "zh-TW"
        self.translations = {}
        self.language_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "languages"
        self.language_dir.mkdir(exist_ok=True)
        self.available_languages = self._get_available_languages()
        
    def _get_available_languages(self):
        """
        獲取可用的語言列表
        """
        languages = []
        if self.language_dir.exists():
            for file in self.language_dir.glob("*.json"):
                lang_code = file.stem
                languages.append(lang_code)
        return languages
        
    def load_language(self, language_code):
        """
        加載指定語言的翻譯資源
        """
        if language_code not in self.available_languages:
            print(f"警告: 語言 '{language_code}' 不可用，使用預設語言 'zh-TW'")
            language_code = "zh-TW"
            
        language_file = self.language_dir / f"{language_code}.json"
        
        if language_file.exists():
            try:
                with open(language_file, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
                self.current_language = language_code
                print(f"已加載語言: {language_code}")
                return True
            except Exception as e:
                print(f"加載語言包時發生錯誤: {e}")
                self.translations = {}
                return False
        else:
            print(f"警告: 語言包文件 '{language_file}' 不存在")
            self.translations = {}
            return False
            
    def get_text(self, key, default=""):
        """
        獲取指定鍵的翻譯文本
        """
        return self.translations.get(key, default)
        
    def get_current_language(self):
        """
        獲取當前選定的語言代碼
        """
        return self.current_language
        
    def get_available_languages(self):
        """
        獲取可用的語言代碼列表
        """
        return self.available_languages
        
    def get_language_name(self, language_code):
        """
        獲取語言代碼對應的顯示名稱
        """
        language_names = {
            "zh-TW": "繁體中文",
            "en": "English"
        }
        return language_names.get(language_code, language_code)
