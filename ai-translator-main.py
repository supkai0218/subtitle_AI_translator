#v0.89.06 加入預設命名邏輯：CapCut使用父目錄名稱，SRT使用檔名_ai，提升使用便利性
#v0.89.05 新增批次翻譯失敗重試機制、調控空白翻譯閾值、移除main檔名版本號
#v0.89.04 新增環境變數替換功能，設定檔中可使用 ${VAR_NAME} 來引用環境變數
#v0.89.03 新增音頻分離獨立工具，其他獨立工具路徑及檔名變更
#v0.89.02 新增介面語言包切換功能(繁中/英文)
#v0.89.01 新增自訂3B流程原文字幕自定義後綴檔名功能
#v0.89.00 新增1B時間碼過濾及修正功能：支援設定最大時長閾值和目標時長


import sys
import os
import json
import shutil
import glob
import subprocess
import copy
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QMessageBox, QDialog, QLineEdit, QFormLayout, QRadioButton, QGroupBox,
    QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# --- 真實自訂模組匯入 ---
# 請確保您的專案目錄下有 "modules" 資料夾，且包含以下檔案
from modules.capcut_converter import CapcutConverter
from modules.text_filter import TextFilter
from modules.text_marker import SensitiveWordReplacer
from modules.translation_editor_dialog import TranslationEditorDialog
from modules.markreplacer import MarkerReplacer
from modules.srt_merger_v01 import SRTMerger
from modules.srt_separator import SrtSeparator
from modules.settings_path import (
    resolve_settings_file,
    resolve_settings_file_from_data,
    make_portable_path,
    clear_settings_cache,
    update_bootstrap_pointer,
)

# --- AI翻譯相關模組匯入 ---
from modules.ai_translator import AITranslator
from modules.ai_validator import TranslationValidator, ValidationStatus
from modules.prompt_manager import PromptManager
from modules.ai_translation_editor_dialog import AITranslationEditorDialog

# ----------------- 流程定義 -----------------
FLOWS = {
    "full_flow": {
        "name": "完整流程 (過濾->標記->翻譯)",
        "steps": ["1A", "1B", "1C", "1D", "2C", "3A", "3B"]
    },
    "parse_only": {
        "name": "字幕轉換解析 (僅生成SRT)",
        "steps": ["1A", "3B"]
    },
    "translate_raw": {
        "name": "原字幕翻譯 (不過濾不標記)",
        "steps": ["1A", "1D", "2C", "3B"]
    },
    "filter_only": {
        "name": "只過濾不翻譯",
        "steps": ["1A", "1B", "3B"]
    },
    "filter_translate": {
        "name": "只過濾且翻譯",
        "steps": ["1A", "1B", "1D", "2C", "3B"]
    },
    "mark_translate": {
        "name": "只標記且翻譯 (不過濾)",
        "steps": ["1A", "1C", "1D", "2C", "3A", "3B"]
    }
}

# STEP_DESCRIPTIONS 移至類中作為方法

# ----------------- 設定檔相關函式與預設值 -----------------
DEFAULT_SETTINGS = {
    "paths": {
        "txt_1A": "txt/1A", "txt_1B": "txt/1B", "txt_1C": "txt/1C",
        "txt_2B": "txt/2B", "txt_3A": "txt/3A", "ai": "AI",
        "json_capcut": "json/capcut", "json_bak_markers": "json/bak_markers",
        "markers_db": "json/markers_db.json", "script_2A": "2A_prompt-manager_*.py",
        "script_2B": "2B_markers-manager_*.py", "srt_output": ".",
        "script_1B_filter": "1B_filter_patterns_editor_*.py",
        "filter_patterns_db": "json/filter_patterns.json",
        "prompt_templates_db": "json/prompt_templates.json",
        "srt_input": "srt/in",
        "capcut_drafts_dir": "",
        "settings_file": "settings/settings.json"
    },
    "ai_translation": {
        "api_provider": "openrouter",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key": "",
        "model": "anthropic/claude-3-sonnet",
        "source_language": "ja",
        "target_language": "zh-TW",
        "batch_size": 10,
        "max_retries": 3,
        "retry_delay": 2,
        "batch_failed_retry_count": 3,
        "max_concurrent_requests": 5,
        "enable_validation": True,
        "prompts": {
            "system_prompt": "",
            "user_prompt_template": ""
        }
    },
    "text_filter": {
        "timecode_correction_enabled": False,
        "timecode_max_duration": 5.0,
        "timecode_target_duration": 3.0
    },
    "raw_subtitle": {
        "enabled": True,
        "suffix": "_raw"
    },
    "language": {
        "interface_language": "zh-TW"
    }
}

def get_settings_filepath():
    return resolve_settings_file()

def load_settings():
    settings_file = get_settings_filepath()
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            settings.setdefault("paths", {})
            settings["paths"]["settings_file"] = make_portable_path(settings_file)
            update_bootstrap_pointer(settings_file)

            # 移除舊的prompt鍵以確保向後相容
            if "ai_translation" in settings and "prompts" in settings["ai_translation"]:
                old_keys = ["translation_style", "video_type", "character_info"]
                for key in old_keys:
                    if key in settings["ai_translation"]["prompts"]:
                        del settings["ai_translation"]["prompts"][key]

            # 確保paths設定完整
            for key, value in DEFAULT_SETTINGS["paths"].items():
                if key not in settings.get("paths", {}):
                    settings.setdefault("paths", {})[key] = value

            # 確保ai_translation設定完整
            if "ai_translation" not in settings:
                settings["ai_translation"] = DEFAULT_SETTINGS["ai_translation"].copy()
            else:
                # 移除舊的enabled鍵（如果存在）
                if "enabled" in settings["ai_translation"]:
                    del settings["ai_translation"]["enabled"]

                # 補充缺失的AI翻譯設定
                for key, value in DEFAULT_SETTINGS["ai_translation"].items():
                    if key not in settings["ai_translation"]:
                        settings["ai_translation"][key] = value

                # 特別處理prompts子設定
                if "prompts" not in settings["ai_translation"]:
                    settings["ai_translation"]["prompts"] = DEFAULT_SETTINGS["ai_translation"]["prompts"].copy()
                else:
                    for key, value in DEFAULT_SETTINGS["ai_translation"]["prompts"].items():
                        if key not in settings["ai_translation"]["prompts"]:
                            settings["ai_translation"]["prompts"][key] = value

            # 確保text_filter設定完整
            if "text_filter" not in settings:
                settings["text_filter"] = DEFAULT_SETTINGS["text_filter"].copy()
            else:
                # 補充缺失的文字過濾設定
                for key, value in DEFAULT_SETTINGS["text_filter"].items():
                    if key not in settings["text_filter"]:
                        settings["text_filter"][key] = value

            # 確保raw_subtitle設定完整
            if "raw_subtitle" not in settings:
                settings["raw_subtitle"] = DEFAULT_SETTINGS["raw_subtitle"].copy()
            else:
                for key, value in DEFAULT_SETTINGS["raw_subtitle"].items():
                    if key not in settings["raw_subtitle"]:
                        settings["raw_subtitle"][key] = value
            
            # 確保語言設定完整
            if "language" not in settings:
                settings["language"] = DEFAULT_SETTINGS["language"].copy()
            else:
                for key, value in DEFAULT_SETTINGS["language"].items():
                    if key not in settings["language"]:
                        settings["language"][key] = value

            return settings
        except Exception:
            pass
    default_settings = copy.deepcopy(DEFAULT_SETTINGS)
    default_settings.setdefault("paths", {})
    default_settings["paths"]["settings_file"] = make_portable_path(settings_file)
    default_settings.setdefault("language", {})
    update_bootstrap_pointer(settings_file)
    return default_settings

def save_settings(settings):
    target_path = resolve_settings_file_from_data(settings)
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        update_bootstrap_pointer(target_path)
        clear_settings_cache()
    except Exception as e:
        print(f"儲存設定檔失敗：{e}")

# ----------------- 設定對話框 -----------------
from PyQt6.QtWidgets import QTabWidget, QCheckBox, QSpinBox

class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None, language_manager=None):
        super().__init__(parent)
        self.language_manager = language_manager
        self.setWindowTitle(self._get_text("settings_dialog_title", "系統設定"))
        self.resize(700, 650)
        self.current_settings = current_settings.copy()
        self.inputs = {}
        self.ai_inputs = {}
        self.language_inputs = {}
        self.init_ui()

    def _get_text(self, key, default=""):
        """獲取翻譯文字的輔助方法"""
        if self.language_manager:
            return self.language_manager.get_text(key, default)
        return default

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 使用分頁式界面
        tab_widget = QTabWidget()
        
        # 路徑設定分頁
        paths_tab = QWidget()
        self.setup_paths_tab(paths_tab)
        tab_widget.addTab(paths_tab, self._get_text("paths_tab_title", "路徑設定"))
        
        # AI翻譯設定分頁
        ai_tab = QWidget()
        self.setup_ai_tab(ai_tab)
        tab_widget.addTab(ai_tab, self._get_text("ai_tab_title", "AI翻譯設定"))
        
        # 語言設定分頁
        language_tab = QWidget()
        self.setup_language_tab(language_tab)
        tab_widget.addTab(language_tab, self._get_text("language_tab_title", "語言設定"))
        
        layout.addWidget(tab_widget)
        
        # 按鈕區域
        btn_layout = QHBoxLayout()
        restore_btn = QPushButton(self._get_text("restore_defaults_button", "恢復預設值"))
        restore_btn.clicked.connect(self.restore_defaults)
        save_btn = QPushButton(self._get_text("save_button", "儲存"))
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(self._get_text("cancel_button", "取消"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(restore_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def setup_paths_tab(self, tab):
        layout = QVBoxLayout(tab)
        form_layout = QFormLayout()
        
        dir_keys = ["capcut_drafts_dir", "txt_1A", "txt_1B", "txt_1C", "txt_2B", "txt_3A", "ai", "json_capcut", "json_bak_markers", "srt_input", "srt_output"]
        file_keys = ["markers_db", "script_2A", "script_2B", "script_1B_filter", "filter_patterns_db", "prompt_templates_db", "settings_file"]
        
        key_descriptions = {
            "capcut_drafts_dir": self._get_text("capcut_drafts_dir_label", "CapCut專案預設開啟目錄:"),
            "txt_1A": self._get_text("txt_1a_label", "1A 字幕/時間軸資料夾:"),
            "txt_1B": self._get_text("txt_1b_label", "1B 過濾後文字資料夾:"),
            "txt_1C": self._get_text("txt_1c_label", "1C 標記後文字資料夾:"),
            "txt_2B": self._get_text("txt_2b_label", "2C 翻譯結果資料夾:"),
            "txt_3A": self._get_text("txt_3a_label", "3A 標記還原資料夾:"),
            "ai": self._get_text("ai_folder_label", "AI 交換資料夾:"),
            "json_capcut": self._get_text("json_capcut_label", "CapCut JSON 儲存資料夾:"),
            "json_bak_markers": self._get_text("json_bak_markers_label", "標記備份資料夾:"),
            "srt_input": self._get_text("srt_input_label", "SRT 來源資料夾:"),
            "srt_output": self._get_text("srt_output_label", "SRT 輸出資料夾:"),
            "markers_db": self._get_text("markers_db_label", "標記資料庫檔案:"),
            "script_2A": self._get_text("script_2a_label", "2A prompt管理腳本:"),
            "script_2B": self._get_text("script_2b_label", "2B 標記管理腳本:"),
            "script_1B_filter": self._get_text("script_1b_filter_label", "1B 過濾管理腳本:"),
            "filter_patterns_db": self._get_text("filter_patterns_db_label", "1B 過濾文字資料庫檔案:"),
            "prompt_templates_db": self._get_text("prompt_templates_db_label", "Prompt 模板資料庫檔案:"),
            "settings_file": self._get_text("settings_file_label", "系統設定檔案位置:")
        }

        for key in dir_keys:
            le = QLineEdit(self.current_settings["paths"].get(key, ""))
            btn = QPushButton(self._get_text("browse_button", "瀏覽"))
            btn.clicked.connect(lambda checked, le=le: self.browse_directory(le))
            hlayout = QHBoxLayout()
            hlayout.addWidget(le)
            hlayout.addWidget(btn)
            form_layout.addRow(key_descriptions.get(key, f"{key}:"), hlayout)
            self.inputs[key] = le

        for key in file_keys:
            le = QLineEdit(self.current_settings["paths"].get(key, ""))
            btn = QPushButton(self._get_text("browse_button", "瀏覽"))
            btn.clicked.connect(lambda checked, le=le: self.browse_file(le))
            hlayout = QHBoxLayout()
            hlayout.addWidget(le)
            hlayout.addWidget(btn)
            form_layout.addRow(key_descriptions.get(key, f"{key}:"), hlayout)
            self.inputs[key] = le

        layout.addLayout(form_layout)

    def setup_ai_tab(self, tab):
        layout = QVBoxLayout(tab)
        form_layout = QFormLayout()

        ai_config = self.current_settings.get("ai_translation", {})

        # API設定
        api_group = QGroupBox(self._get_text("api_settings_group", "API設定"))
        api_layout = QFormLayout(api_group)
        
        # API供應商
        self.ai_inputs["api_provider"] = QComboBox()
        providers = ["openrouter", "openai", "anthropic", "custom"]
        self.ai_inputs["api_provider"].addItems(providers)
        current_provider = ai_config.get("api_provider", "openrouter")
        if current_provider in providers:
            self.ai_inputs["api_provider"].setCurrentText(current_provider)
        api_layout.addRow(self._get_text("api_provider_label", "API供應商:"), self.ai_inputs["api_provider"])
        
        # API URL
        self.ai_inputs["api_url"] = QLineEdit(ai_config.get("api_url", "https://openrouter.ai/api/v1/chat/completions"))
        api_layout.addRow(self._get_text("api_url_label", "API網址:"), self.ai_inputs["api_url"])
        
        # API Key
        self.ai_inputs["api_key"] = QLineEdit(ai_config.get("api_key", ""))
        self.ai_inputs["api_key"].setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow(self._get_text("api_key_label", "API金鑰:"), self.ai_inputs["api_key"])
        
        # 模型
        self.ai_inputs["model"] = QLineEdit(ai_config.get("model", "anthropic/claude-3-sonnet"))
        api_layout.addRow(self._get_text("model_label", "模型名稱:"), self.ai_inputs["model"])
        
        form_layout.addRow("", api_group)
        
        # 翻譯設定
        translate_group = QGroupBox(self._get_text("translation_settings_group", "翻譯設定"))
        translate_layout = QFormLayout(translate_group)
        
        # 來源語言
        self.ai_inputs["source_language"] = QComboBox()
        languages = ["ja", "en", "ko", "zh-CN", "zh-TW"]
        self.ai_inputs["source_language"].addItems(languages)
        current_source = ai_config.get("source_language", "ja")
        if current_source in languages:
            self.ai_inputs["source_language"].setCurrentText(current_source)
        translate_layout.addRow(self._get_text("source_language_label", "來源語言:"), self.ai_inputs["source_language"])
        
        # 目標語言
        self.ai_inputs["target_language"] = QComboBox()
        self.ai_inputs["target_language"].addItems(languages)
        current_target = ai_config.get("target_language", "zh-TW")
        if current_target in languages:
            self.ai_inputs["target_language"].setCurrentText(current_target)
        translate_layout.addRow(self._get_text("target_language_label", "目標語言:"), self.ai_inputs["target_language"])
        
        # 批次大小（移除上限限制）
        self.ai_inputs["batch_size"] = QSpinBox()
        self.ai_inputs["batch_size"].setRange(1, 9999)
        self.ai_inputs["batch_size"].setValue(ai_config.get("batch_size", 10))
        translate_layout.addRow(self._get_text("batch_size_label", "批次大小:"), self.ai_inputs["batch_size"])
        
        # 並行請求數
        self.ai_inputs["max_concurrent_requests"] = QSpinBox()
        self.ai_inputs["max_concurrent_requests"].setRange(1, 20)
        self.ai_inputs["max_concurrent_requests"].setValue(ai_config.get("max_concurrent_requests", 5))
        translate_layout.addRow(self._get_text("max_concurrent_requests_label", "最大並行請求數:"), self.ai_inputs["max_concurrent_requests"])
        
        # 翻譯驗證
        self.ai_inputs["enable_validation"] = QCheckBox(self._get_text("enable_validation_label", "啟用翻譯結果驗證"))
        self.ai_inputs["enable_validation"].setChecked(ai_config.get("enable_validation", True))
        translate_layout.addRow("", self.ai_inputs["enable_validation"])
        
        # 重試設定
        self.ai_inputs["max_retries"] = QSpinBox()
        self.ai_inputs["max_retries"].setRange(1, 10)
        self.ai_inputs["max_retries"].setValue(ai_config.get("max_retries", 3))
        translate_layout.addRow(self._get_text("max_retries_label", "最大重試次數:"), self.ai_inputs["max_retries"])
        
        self.ai_inputs["retry_delay"] = QSpinBox()
        self.ai_inputs["retry_delay"].setRange(1, 30)
        self.ai_inputs["retry_delay"].setValue(ai_config.get("retry_delay", 2))
        translate_layout.addRow(self._get_text("retry_delay_label", "重試延遲(秒):"), self.ai_inputs["retry_delay"])

        self.ai_inputs["batch_failed_retry_count"] = QSpinBox()
        self.ai_inputs["batch_failed_retry_count"].setRange(0, 10)
        self.ai_inputs["batch_failed_retry_count"].setValue(ai_config.get("batch_failed_retry_count", 3))
        translate_layout.addRow(self._get_text("batch_failed_retry_count_label", "批次失敗重試次數:"), self.ai_inputs["batch_failed_retry_count"])

        form_layout.addRow("", translate_group)
        
        # Prompt設定
        prompt_group = QGroupBox(self._get_text("prompt_settings_group", "Prompt設定"))
        prompt_layout = QFormLayout(prompt_group)

        prompts_config = ai_config.get("prompts", {})

        # System Prompt
        self.ai_inputs["system_prompt"] = QTextEdit()
        self.ai_inputs["system_prompt"].setMaximumHeight(80)
        self.ai_inputs["system_prompt"].setPlainText(prompts_config.get("system_prompt", ""))
        prompt_layout.addRow(self._get_text("system_prompt_label", "系統提示詞:"), self.ai_inputs["system_prompt"])

        # User Prompt Template
        self.ai_inputs["user_prompt_template"] = QTextEdit()
        self.ai_inputs["user_prompt_template"].setMaximumHeight(80)
        self.ai_inputs["user_prompt_template"].setPlainText(prompts_config.get("user_prompt_template", ""))
        prompt_layout.addRow(self._get_text("user_prompt_template_label", "用戶提示詞模板:"), self.ai_inputs["user_prompt_template"])

        form_layout.addRow("", prompt_group)
        
        layout.addLayout(form_layout)

    def browse_directory(self, line_edit):
        directory = QFileDialog.getExistingDirectory(self, self._get_text("folder_dialog_title", "選擇目錄"), line_edit.text())
        if directory:
            line_edit.setText(directory)

    def browse_file(self, line_edit):
        filename, _ = QFileDialog.getOpenFileName(self, self._get_text("file_dialog_title", "選擇檔案"), line_edit.text())
        if filename:
            line_edit.setText(filename)

    def setup_language_tab(self, tab):
        layout = QVBoxLayout(tab)
        form_layout = QFormLayout()
        
        # 介面語言設定
        language_group = QGroupBox(self._get_text("interface_language_group", "介面語言設定"))
        language_layout = QFormLayout(language_group)
        
        self.language_inputs["interface_language"] = QComboBox()
        languages = ["zh-TW", "en"]
        self.language_inputs["interface_language"].addItems(languages)
        current_language = self.current_settings.get("language", {}).get("interface_language", "zh-TW")
        if current_language in languages:
            self.language_inputs["interface_language"].setCurrentText(current_language)
        language_layout.addRow(self._get_text("language_select_label", "選擇介面語言:"), self.language_inputs["interface_language"])
        
        form_layout.addRow("", language_group)
        layout.addLayout(form_layout)

    def restore_defaults(self):
        # 恢復路徑設定預設值
        for key, default_value in DEFAULT_SETTINGS["paths"].items():
            if key in self.inputs:
                self.inputs[key].setText(default_value)

        # 恢復AI翻譯設定預設值
        ai_defaults = DEFAULT_SETTINGS["ai_translation"]
        self.ai_inputs["api_provider"].setCurrentText(ai_defaults["api_provider"])
        self.ai_inputs["api_url"].setText(ai_defaults["api_url"])
        self.ai_inputs["api_key"].setText(ai_defaults["api_key"])
        self.ai_inputs["model"].setText(ai_defaults["model"])
        self.ai_inputs["source_language"].setCurrentText(ai_defaults["source_language"])
        self.ai_inputs["target_language"].setCurrentText(ai_defaults["target_language"])
        self.ai_inputs["batch_size"].setValue(ai_defaults["batch_size"])
        self.ai_inputs["max_concurrent_requests"].setValue(ai_defaults["max_concurrent_requests"])
        self.ai_inputs["enable_validation"].setChecked(ai_defaults["enable_validation"])
        self.ai_inputs["max_retries"].setValue(ai_defaults["max_retries"])
        self.ai_inputs["retry_delay"].setValue(ai_defaults["retry_delay"])
        self.ai_inputs["batch_failed_retry_count"].setValue(ai_defaults["batch_failed_retry_count"])

        # 恢復Prompt設定預設值
        prompt_defaults = ai_defaults["prompts"]
        self.ai_inputs["system_prompt"].setPlainText(prompt_defaults["system_prompt"])
        self.ai_inputs["user_prompt_template"].setPlainText(prompt_defaults["user_prompt_template"])
        
        # 恢復語言設定預設值
        language_defaults = DEFAULT_SETTINGS["language"]
        self.language_inputs["interface_language"].setCurrentText(language_defaults["interface_language"])

    def get_settings(self):
        new_settings = {
            "paths": {},
            "ai_translation": {
                "prompts": {}
            },
            "language": {}
        }

        # 保存路徑設定
        for key, line_edit in self.inputs.items():
            new_settings["paths"][key] = line_edit.text().strip()

        # 保存AI翻譯設定
        new_settings["ai_translation"]["api_provider"] = self.ai_inputs["api_provider"].currentText()
        new_settings["ai_translation"]["api_url"] = self.ai_inputs["api_url"].text().strip()
        new_settings["ai_translation"]["api_key"] = self.ai_inputs["api_key"].text().strip()
        new_settings["ai_translation"]["model"] = self.ai_inputs["model"].text().strip()
        new_settings["ai_translation"]["source_language"] = self.ai_inputs["source_language"].currentText()
        new_settings["ai_translation"]["target_language"] = self.ai_inputs["target_language"].currentText()
        new_settings["ai_translation"]["batch_size"] = self.ai_inputs["batch_size"].value()
        new_settings["ai_translation"]["max_concurrent_requests"] = self.ai_inputs["max_concurrent_requests"].value()
        new_settings["ai_translation"]["enable_validation"] = self.ai_inputs["enable_validation"].isChecked()
        new_settings["ai_translation"]["max_retries"] = self.ai_inputs["max_retries"].value()
        new_settings["ai_translation"]["retry_delay"] = self.ai_inputs["retry_delay"].value()
        new_settings["ai_translation"]["batch_failed_retry_count"] = self.ai_inputs["batch_failed_retry_count"].value()

        # 保存Prompt設定
        new_settings["ai_translation"]["prompts"]["system_prompt"] = self.ai_inputs["system_prompt"].toPlainText().strip()
        new_settings["ai_translation"]["prompts"]["user_prompt_template"] = self.ai_inputs["user_prompt_template"].toPlainText().strip()
        
        # 保存語言設定
        new_settings["language"]["interface_language"] = self.language_inputs["interface_language"].currentText()

        return new_settings

# ----------------- 處理工作執行緒 -----------------
class ProcessWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    process_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)
    show_translation_editor = pyqtSignal(str, str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.input_file = None
        self.output_filename = None
        self.source_mode = "capcut"
        self.flow_mode = "full_flow"
        self.is_paused = False
        self.ai_folder_opened = False
        self.auto_mode = False

    def set_task(self, input_file, output_filename, source_mode, flow_mode, auto_mode=False):
        self.input_file = input_file
        self.output_filename = output_filename
        self.source_mode = source_mode
        self.flow_mode = flow_mode
        self.auto_mode = auto_mode

    def run(self):
        try:
            if not self.input_file or not self.output_filename:
                raise ValueError("未設定輸入或輸出檔案")

            self.base_path = Path(os.getcwd())
            self.settings = self.main_window.settings["paths"]
            self.ai_folder_opened = False # 重置標記
            
            for key in ["txt_1A", "txt_1B", "txt_1C", "txt_2B", "txt_3A", "ai"]:
                (self.base_path / self.settings[key]).mkdir(parents=True, exist_ok=True)
            
            self.log(f"[診斷] 開始執行流程，flow_mode={self.flow_mode}, auto_mode={self.auto_mode}")
            self.progress_updated.emit(10, "執行 1A: 字幕/時間軸拆解...")
            self.run_1A_parse()

            if self.flow_mode == "full_flow":
                self.log(f"[診斷] full_flow 流程開始")
                self.run_1B_filter()
                self.log(f"[診斷] 1B完成，準備執行1C")
                self.run_1C_mark(from_stage='1B')
                self.log(f"[診斷] 1C完成，準備執行1D")
                self.run_1D_copy_for_ai(from_stage='1C')
                self.log(f"[診斷] 1D完成，準備執行2C")
                self.run_2C_get_translation()
                self.log(f"[診斷] 2C完成，準備執行3A")
                self.run_3A_replace_markers()
                self.log(f"[診斷] 3A完成，準備執行3B")
                self.run_3B_merge(text_stage='3A', time_stage='1B')
            
            elif self.flow_mode == "parse_only":
                self.run_3B_merge(text_stage='1A', time_stage='1A')

            elif self.flow_mode == "translate_raw":
                self.run_1D_copy_for_ai(from_stage='1A')
                self.run_2C_get_translation()
                self.run_3B_merge(text_stage='2B', time_stage='1A')

            elif self.flow_mode == "filter_only":
                self.run_1B_filter()
                self.run_3B_merge(text_stage='1B', time_stage='1B')

            elif self.flow_mode == "filter_translate":
                self.run_1B_filter()
                self.run_1D_copy_for_ai(from_stage='1B')
                self.run_2C_get_translation()
                self.run_3B_merge(text_stage='2B', time_stage='1B')
            
            elif self.flow_mode == "mark_translate":
                self.run_1C_mark(from_stage='1A')
                self.run_1D_copy_for_ai(from_stage='1C')
                self.run_2C_get_translation()
                self.run_3A_replace_markers()
                self.run_3B_merge(text_stage='3A', time_stage='1A')
            
            self.progress_updated.emit(100, "流程處理完成!")
            self.process_complete.emit()
        except Exception as e:
            import traceback
            self.error_occurred.emit(f"執行失敗: {e}\n{traceback.format_exc()}")
            
    def run_1A_parse(self):
        if self.source_mode == "capcut":
            converter = CapcutConverter()
            success, msg = converter.process_file(self.input_file, self.output_filename, self.settings)
        else:
            separator = SrtSeparator()
            default_srt_path = Path(os.getcwd()) / "srt" / "in" / f"{self.output_filename}.srt"
            self.log(f"[偵錯] 1A SRT 模式 input_file={self.input_file}, output_filename={self.output_filename}, convert預設路徑={default_srt_path}")
            success, msg = separator.convert(
                str(self.base_path / self.settings["txt_1A"]),
                self.output_filename,
                input_srt_path=self.input_file
            )
        if not success: raise Exception(f"1A 階段失敗: {msg}")
        self.log(f"1A: 拆解完成。")

    def run_1B_filter(self):
        self.progress_updated.emit(20, "執行 1B: 文字過濾...")
        txt_in_file = self.base_path / self.settings['txt_1A'] / f"1A-txt_{self.output_filename}.txt"
        
        # 讀取時間碼修正參數
        timecode_max = None
        timecode_target = None
        
        if self.main_window.timecode_correction_enabled:
            try:
                timecode_max = float(self.main_window.timecode_max_input.text())
                timecode_target = float(self.main_window.timecode_target_input.text())
                self.log(f"時間碼修正已啟用: 最大時長={timecode_max}秒, 修正為={timecode_target}秒")
            except ValueError:
                self.log("警告：時間碼參數格式錯誤，將不套用時間碼修正")
        
        text_filter = TextFilter(
            settings_paths=self.settings,
            timecode_max_duration=timecode_max,
            timecode_target_duration=timecode_target
        )
        success, msg = text_filter.process_file(str(txt_in_file), self.output_filename)
        if not success: raise Exception(f"1B 階段失敗: {msg}")
        self.log(f"1B: 過濾完成。{msg}")

    def run_1C_mark(self, from_stage='1B'):
        self.progress_updated.emit(30, f"執行 1C: 特殊詞標記 (來源: {from_stage})...")
        in_file = self.base_path / self.settings[f'txt_{from_stage}'] / f"{from_stage}-txt_{self.output_filename}.txt"

        marker = SensitiveWordReplacer(filename=self.output_filename, settings_paths=self.settings)
        # 直接呼叫並傳遞來源路徑，不再需要 try...except
        success, msg = marker.process_files(input_path=str(in_file))
        if not success: raise Exception(f"1C 階段失敗: {msg}")
        self.log(f"1C: 標記完成。")

    def run_1D_copy_for_ai(self, from_stage='1C'):
        self.progress_updated.emit(40, f"執行 1D: 準備翻譯檔案 (來源: {from_stage})...")
        ai_folder = self.base_path / self.settings["ai"]
        for f in ai_folder.glob('*'): f.unlink()
        
        src_file = self.base_path / self.settings[f'txt_{from_stage}'] / f"{from_stage}-txt_{self.output_filename}.txt"
        shutil.copy2(src_file, ai_folder / src_file.name)
        
        if not self.auto_mode: # 自動模式下不開啟資料夾
            if os.name == 'nt': os.startfile(ai_folder)
            else: subprocess.call(['xdg-open', str(ai_folder)])
            self.ai_folder_opened = True # 標記資料夾已開啟
        else:
             self.log(f"1D: 全自動模式 - 跳過開啟 AI 資料夾。")
             
        self.log(f"1D: 檔案已複製到 AI 資料夾。")
        
    def run_2C_get_translation(self):
        self.log(f"[診斷] 進入 run_2C_get_translation，auto_mode={self.auto_mode}")
        if self.auto_mode:
            self.log(f"[診斷] 全自動模式啟用，將呼叫 run_2C_auto_translation")
            self.run_2C_auto_translation()
            self.log(f"[診斷] run_2C_auto_translation 完成，準備返回並繼續下一步")
            return

        self.log(f"[診斷] 手動模式，等待使用者輸入翻譯")
        self.progress_updated.emit(50, "等待 2C: AI翻譯結果輸入...")
        ai_folder = self.base_path / self.settings["ai"]
        source_filename = next( (f for f in ai_folder.iterdir() if f.is_file()), None)
        if not source_filename: raise Exception("找不到AI資料夾中的來源檔案")

        target_file = self.base_path / self.settings["txt_2B"] / f'2B-txt_{self.output_filename}.txt'
        
        self.show_translation_editor.emit(str(source_filename), str(target_file))
        self.is_paused = True
        while self.is_paused: self.msleep(100)
        self.log(f"2C: 已接收翻譯結果。")
        
    def run_2C_auto_translation(self):
        self.progress_updated.emit(50, "執行 2C: AI 自動翻譯中 (背景執行)...")
        
        # 準備路徑
        ai_folder = self.base_path / self.settings["ai"]
        source_filename = next( (f for f in ai_folder.iterdir() if f.is_file()), None)
        if not source_filename: raise Exception("找不到AI資料夾中的來源檔案")
        
        target_file = self.base_path / self.settings["txt_2B"] / f'2B-txt_{self.output_filename}.txt'
        
        # 讀取來源檔案
        with open(source_filename, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]
            
        # 讀取 AI 設定 (使用系統設定)
        ai_config = self.main_window.settings.get("ai_translation", {}).copy()
        ai_config["paths"] = self.main_window.settings.get("paths", {})
        
        # 初始化翻譯器
        translator = AITranslator(ai_config)
        
        # 驗證連線
        success, msg = translator.validate_api_connection()
        if not success:
             raise Exception(f"AI API 連線失敗: {msg}")
        self.log(f"API 連線確認: {msg}")
        
        # 執行翻譯
        self.log(f"開始批次翻譯 {len(lines)} 行...請稍候")
        
        # 定義進度回調
        def progress_callback(msg):
             self.progress_updated.emit(60, f"2C AI翻譯中: {msg}")
        
        success, response, error_msg = translator.translate_batch(lines, progress_callback=progress_callback)
        
        if not success:
            raise Exception(f"AI 翻譯失敗: {error_msg}")
            
        # --- v2驗證：區分重翻時機 ---
        self.log("正在驗證並清理翻譯結果...")
        validator = TranslationValidator(ai_config)
        empty_threshold = ai_config.get("empty_threshold", 0.01)  # v2: 空白翻譯閾值，預設1%
        validation_status, repaired_result, validation_msg = validator.validate_response(response, len(lines), empty_threshold)

        # 只在需要重翻時才發出警告（FIXABLE 已自動修復）
        if validation_status == ValidationStatus.RETRY_NEEDED:
            self.log(f"警告: 需要重新翻譯: {validation_msg}")
        elif validation_status in (ValidationStatus.ACCEPTABLE, ValidationStatus.FIXABLE):
            self.log(f"提示: {validation_msg}")
        
        # 將 repaired_result (List[str]) 轉換回文字內容
        # 【修正】保留序號格式 "序號:內容"，因為後續的3A步驟需要這個格式
        cleaned_translations = []
        for line in repaired_result:
            # repaired_result已經是"序號:內容"格式，直接使用
            cleaned_translations.append(line.strip())
        
        combined_cleaned_response = "\n".join(cleaned_translations)
            
        # 儲存結果
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(combined_cleaned_response)
            
        self.log(f"2C: AI 自動翻譯完成 (與驗證)，已寫入 {target_file.name}")
        
    def run_3A_replace_markers(self):
        self.log(f"[診斷] 進入 run_3A_replace_markers")
        self.progress_updated.emit(80, "執行 3A: 標記文字還原...")
        markers_path = self.settings.get('markers_db')
        txt_2b_path = self.settings.get('txt_2B')
        txt_3a_path = self.settings.get('txt_3A')
        self.log(f"[偵錯] 3A 設定快照 markers_db={markers_path}, txt_2B={txt_2b_path}, txt_3A={txt_3a_path}, cwd={Path.cwd()}")
        replacer = MarkerReplacer(
            progress_callback=lambda pct, msg: self.progress_updated.emit(pct, msg),
            settings_paths=self.settings
        )
        # 傳遞 input_stage='2B'，因為 3A 的來源固定是 2B
        success, msg = replacer.process_file(self.output_filename, input_stage='2B')
        if not success: raise Exception(f"3A 階段失敗: {msg}")
        self.log(f"3A: 標記還原完成。")
        
    def run_3B_merge(self, text_stage, time_stage):
        self.progress_updated.emit(90, f"執行 3B: 合併SRT (文字: {text_stage}, 時間: {time_stage})...")
        output_dir = self.base_path / self.settings["srt_output"]
        ai_folder = self.base_path / self.settings["ai"]
        
        text_file = self.base_path / self.settings[f'txt_{text_stage}'] / f"{text_stage}-txt_{self.output_filename}.txt"
        time_file = self.base_path / self.settings[f'txt_{time_stage}'] / f"{time_stage}-time_{self.output_filename}.txt"
        
        if not text_file.exists(): raise FileNotFoundError(f"找不到字幕文字檔案: {text_file}")
        if not time_file.exists(): raise FileNotFoundError(f"找不到時間軸檔案: {time_file}")

        merger = SRTMerger()
        
        # 合併主要字幕
        srt_out_file = output_dir / f"{self.output_filename}.srt"
        success, msg = merger.merge_files(self.output_filename, str(text_file), str(time_file), str(srt_out_file))
        if not success: raise Exception(f"合併主要字幕失敗: {msg}")
        shutil.copy2(srt_out_file, ai_folder / srt_out_file.name) # 複製到 AI 資料夾

        # 條件式生成 raw 版字幕（根據設定決定）
        if self.main_window.raw_subtitle_enabled:
            raw_text_file = self.base_path / self.settings['txt_1B'] / f"1B-txt_{self.output_filename}.txt"
            raw_time_file = self.base_path / self.settings['txt_1B'] / f"1B-time_{self.output_filename}.txt"
            if raw_text_file.exists() and raw_time_file.exists():
                # 使用自定義後綴
                suffix = self.main_window.raw_subtitle_suffix if self.main_window.raw_subtitle_suffix else "_raw"
                srt_raw_out_file = output_dir / f"{self.output_filename}{suffix}.srt"
                success, msg = merger.merge_files(self.output_filename, str(raw_text_file), str(raw_time_file), str(srt_raw_out_file))
                if not success:
                    self.log(f"警告: 合併原文raw字幕失敗: {msg}")
                else:
                    shutil.copy2(srt_raw_out_file, ai_folder / srt_raw_out_file.name) # 複製到 AI 資料夾
                    self.log(f"已生成原文字幕: {srt_raw_out_file.name}")
            else:
                self.log("資訊: 找不到1B階段檔案，跳過生成原文raw字幕。")
        else:
            self.log("資訊: 原文字幕生成功能已停用，跳過生成。")
        
        # 檢查並開啟 AI 資料夾（全自動模式下不開啟）
        if not self.ai_folder_opened and not self.auto_mode:
            if os.name == 'nt': os.startfile(ai_folder)
            else: subprocess.call(['xdg-open', str(ai_folder)])
            self.ai_folder_opened = True

        self.log(f"3B: SRT檔案生成並複製完成。")

    def resume_process(self): self.is_paused = False
    def log(self, message): self.progress_updated.emit(-1, message)

# --- 手動工具執行緒 ---
class Manual1BFilterWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
    def run(self):
        try:
            settings = self.main_window.settings["paths"]
            script_pattern = str(Path(os.getcwd()) / settings["script_1B_filter"])
            scripts = glob.glob(script_pattern)
            if not scripts: raise FileNotFoundError(f"找不到符合的腳本: {script_pattern}")
            script = max(scripts)
            subprocess.run(['python', script], check=True)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
class Manual2AWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
    def run(self):
        try:
            settings = self.main_window.settings["paths"]
            script_pattern = str(Path(os.getcwd()) / settings["script_2A"])
            scripts = glob.glob(script_pattern)
            if not scripts: raise FileNotFoundError(f"找不到符合的腳本: {script_pattern}")
            script = max(scripts)
            subprocess.run(['python', script], check=True)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
class Manual2BWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
    def run(self):
        try:
            settings = self.main_window.settings["paths"]
            script_pattern = str(Path(os.getcwd()) / settings["script_2B"])
            scripts = glob.glob(script_pattern)
            if not scripts: raise FileNotFoundError(f"找不到符合的腳本: {script_pattern}")
            script = max(scripts)
            subprocess.run(['python', script], check=True)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# ----------------- 主介面 -----------------
class FilenameDialog(QDialog):
    def __init__(self, parent=None, default_name=""):
        super().__init__(parent)
        self.setWindowTitle("設定輸出檔案名稱")
        self.setModal(True)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel("請輸入輸出檔名 (不含副檔名):"))
        self.name_input = QLineEdit(default_name)
        self.name_input.selectAll()
        self.layout.addWidget(self.name_input)
        
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("確定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        self.layout.addLayout(button_layout)

    def get_filename(self):
        return self.name_input.text().strip()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("字幕AI翻譯系統")
        self.resize(700, 750)
        self.setMinimumSize(700, 750)  # 設定最小尺寸，防止視窗縮小
        # 視窗大小不鎖定，允許使用者手動放大（如需完全鎖定可加上 self.setMaximumSize(700, 750)）
        self.output_filename = None
        self.settings = load_settings()
        
        # 初始化語言管理器
        from modules.language_manager import LanguageManager
        self.language_manager = LanguageManager()
        self.language_manager.load_language(self.settings.get("language", {}).get("interface_language", "zh-TW"))
        
        self.ai_auto_translate_enabled = False  # 新增:追蹤AI自動翻譯啟用狀態
        self.one_click_auto_mode = False # 新增:一鍵全自動模式狀態
        self.include_subfolders = True  # 新增:批次處理時是否包含子資料夾（預設包含）
        
        # 新增：時間碼修正參數
        text_filter_config = self.settings.get("text_filter", {})
        self.timecode_correction_enabled = text_filter_config.get("timecode_correction_enabled", False)
        self.timecode_max_duration = text_filter_config.get("timecode_max_duration", 5.0)
        self.timecode_target_duration = text_filter_config.get("timecode_target_duration", 3.0)
        
        # 新增：raw字幕設定參數
        raw_subtitle_config = self.settings.get("raw_subtitle", {})
        self.raw_subtitle_enabled = raw_subtitle_config.get("enabled", True)
        self.raw_subtitle_suffix = raw_subtitle_config.get("suffix", "_raw")
        
        # 批次處理相關屬性
        self.batch_mode = False  # 是否為批次處理模式
        self.batch_files = []  # 待處理的檔案列表
        self.current_batch_index = 0  # 當前處理的檔案索引
        self.batch_errors = []  # 記錄批次處理中的錯誤
        self.setup_ui()
        self.retranslate_ui()  # 初始化時調用翻譯
        self.worker = ProcessWorker(self)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.process_complete.connect(self.process_completed)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.show_translation_editor.connect(self.show_translation_editor)
        self.manual_worker = None

    def get_step_descriptions(self):
        """獲取步驟描述，使用語言管理器"""
        return {
            "1A": self.language_manager.get_text("step_1a", "1A: CapCut字幕解析或SRT檔案拆解"),
            "1B": self.language_manager.get_text("step_1b", "1B: 文字過濾 (同步處理時間軸)"),
            "1C": self.language_manager.get_text("step_1c", "1C: 特殊詞標記"),
            "1D": self.language_manager.get_text("step_1d", "1D: 準備AI翻譯檔案"),
            "2C": self.language_manager.get_text("step_2c", "2C: AI自動翻譯或手動翻譯"),
            "3A": self.language_manager.get_text("step_3a", "3A: 標記文字還原"),
            "3B": self.language_manager.get_text("step_3b", "3B: 生成SRT檔案 (翻譯+原文)")
        }

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        top_layout = QHBoxLayout()
        self.settings_btn = QPushButton("系統設定")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        top_layout.addStretch()
        top_layout.addWidget(self.settings_btn)
        layout.addLayout(top_layout)

        source_group = QGroupBox("步驟 1: 選擇來源")
        source_group.setObjectName("source_group")
        source_layout = QVBoxLayout(source_group)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel(self.language_manager.get_text("source_mode_label", "來源模式:")))
        self.mode_capcut = QRadioButton(self.language_manager.get_text("capcut_subtitle_parsing", "CapCut字幕解析"))
        self.mode_srt = QRadioButton(self.language_manager.get_text("srt_file_parsing", "SRT檔案拆解"))
        self.mode_capcut.setChecked(True)
        mode_layout.addWidget(self.mode_capcut)
        mode_layout.addWidget(self.mode_srt)

        # 新增：一鍵全自動模式勾選框
        self.auto_mode_checkbox = QCheckBox(self.language_manager.get_text("one_click_auto_mode", "一鍵全自動模式 (One-Click Auto)"))
        self.auto_mode_checkbox.setChecked(False)
        self.auto_mode_checkbox.stateChanged.connect(self.on_auto_mode_changed)
        mode_layout.addWidget(self.auto_mode_checkbox)

        # 新增：子資料夾處理選項（略微縮排）
        subfolder_layout = QHBoxLayout()
        subfolder_layout.addSpacing(20)  # 左側縮排
        self.include_subfolders_checkbox = QCheckBox(self.language_manager.get_text("include_subfolders", "包含子資料夾"))
        self.include_subfolders_checkbox.setChecked(True)  # 預設啟用
        self.include_subfolders_checkbox.setEnabled(False)  # 預設停用，等待全自動模式啟用
        self.include_subfolders_checkbox.stateChanged.connect(self.on_include_subfolders_changed)
        subfolder_layout.addWidget(self.include_subfolders_checkbox)
        subfolder_layout.addStretch()
        mode_layout.addLayout(subfolder_layout)
        
        mode_layout.addStretch()
        source_layout.addLayout(mode_layout)

        self.file_btn = QPushButton("選擇來源檔案並設定輸出檔名")
        self.file_btn.clicked.connect(self.select_file)
        source_layout.addWidget(self.file_btn)
        
        self.file_label = QLabel("來源檔案: 尚未選擇")
        self.output_label = QLabel("輸出檔名: 尚未設定")
        source_layout.addWidget(self.file_label)
        source_layout.addWidget(self.output_label)
        layout.addWidget(source_group)

        flow_group = QGroupBox("步驟 2: 選擇執行流程")
        flow_group.setObjectName("flow_group")
        flow_layout = QVBoxLayout(flow_group)
        self.flow_combo = QComboBox()
        flow_map = {
            "full_flow": "flow_full",
            "parse_only": "flow_parse",
            "translate_raw": "flow_translate_raw",
            "filter_only": "flow_filter",
            "filter_translate": "flow_filter_translate",
            "mark_translate": "flow_mark_translate"
        }
        for flow_id, flow_data in FLOWS.items():
            self.flow_combo.addItem(self.language_manager.get_text(flow_map.get(flow_id, flow_id), flow_data["name"]), flow_id)
        self.flow_combo.currentIndexChanged.connect(self.update_flow_description)
        flow_layout.addWidget(self.flow_combo)

        self.workflow_preview_box = QGroupBox("流程預覽")
        self.workflow_preview_layout = QVBoxLayout(self.workflow_preview_box)
        flow_layout.addWidget(self.workflow_preview_box)
        layout.addWidget(flow_group)
        self.update_flow_description()

        manual_tools_group = QGroupBox("手動工具")
        manual_tools_group.setObjectName("manual_tools_group")
        manual_tools_layout = QHBoxLayout(manual_tools_group)
        btn_1b = QPushButton("1B 過濾文字管理")
        btn_1b.setObjectName("btn_1b")
        btn_2a = QPushButton("2A prompt管理")
        btn_2a.setObjectName("btn_2a")
        btn_2b = QPushButton("2B 標記資料庫管理")
        btn_2b.setObjectName("btn_2b")
        self.ai_settings_dialog_btn = QPushButton("AI 翻譯設定 / Prompt")
        btn_1b.clicked.connect(self.run_manual_1B_filter)
        btn_2a.clicked.connect(self.run_manual_2A)
        btn_2b.clicked.connect(self.run_manual_2B)
        self.ai_settings_dialog_btn.clicked.connect(self.open_ai_settings_dialog)
        manual_tools_layout.addWidget(btn_1b)
        manual_tools_layout.addWidget(btn_2a)
        manual_tools_layout.addWidget(btn_2b)
        manual_tools_layout.addWidget(self.ai_settings_dialog_btn)
        layout.addWidget(manual_tools_group)

        run_group = QGroupBox("步驟 3: 執行與狀態")
        run_group.setObjectName("run_group")
        run_layout = QVBoxLayout(run_group)
        self.run_btn = QPushButton("開始執行")
        self.run_btn.setStyleSheet("font-size: 16px; padding: 10px;")
        self.run_btn.clicked.connect(self.start_processing)
        run_layout.addWidget(self.run_btn)
        
        self.progress_bar = QProgressBar()
        run_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("就緒")
        run_layout.addWidget(self.status_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        run_layout.addWidget(self.log_text)
        layout.addWidget(run_group)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self, language_manager=self.language_manager)
        if dialog.exec():
            new_settings = dialog.get_settings()
            # 檢查語言設定是否有變更
            if self.settings.get("language", {}).get("interface_language") != new_settings.get("language", {}).get("interface_language"):
                self.language_manager.load_language(new_settings.get("language", {}).get("interface_language", "zh-TW"))
                self.retranslate_ui()  # 重新翻譯界面
            
            self.settings = new_settings
            save_settings(self.settings)
            self.log_message(self.language_manager.get_text("settings_saved", "系統設定已儲存。"))
            
    def on_auto_mode_changed(self, state):
        self.one_click_auto_mode = bool(state)
        self.update_flow_description() # 更新流程描述以反映自動模式狀態
        mode_text = self.language_manager.get_text("enabled", "啟用") if self.one_click_auto_mode else self.language_manager.get_text("disabled", "停用")
        self.log_message(self.language_manager.get_text("auto_mode_status", "一鍵全自動模式已{mode}").format(mode=mode_text))
        
        # 新增：控制子資料夾選項的啟用狀態
        self.include_subfolders_checkbox.setEnabled(self.one_click_auto_mode)
    
    def on_include_subfolders_changed(self, state):
        """當使用者切換「包含子資料夾」選項時"""
        self.include_subfolders = bool(state)
        mode_text = self.language_manager.get_text("include_subfolders", "包含子資料夾") if self.include_subfolders else self.language_manager.get_text("current_folder_only", "僅目前資料夾")
        self.log_message(self.language_manager.get_text("batch_mode_switch", "批次處理模式已切換為: {mode}").format(mode=mode_text))

    def update_flow_description(self):
        # 完全清空布局中的所有項（包括 layout 和 widget）
        while self.workflow_preview_layout.count() > 0:
            item = self.workflow_preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

        flow_id = self.flow_combo.currentData()
        if flow_id:
            steps = FLOWS[flow_id]["steps"]
            step_descriptions = self.get_step_descriptions()
            for step_id in steps:
                # 處理 '3B_raw' 這種特殊標記
                clean_step_id = step_id.split('_')[0]
                desc = step_descriptions.get(step_id, step_descriptions.get(clean_step_id, f"{step_id}: {self.language_manager.get_text('unknown_step', '未知步驟')}"))

                if step_id == "1B":
                    # 為 1B 步驟添加標籤
                    label = QLabel(desc)
                    self.workflow_preview_layout.addWidget(label)
                    
                    # 時間碼修正勾選框及參數
                    timecode_layout = QHBoxLayout()
                    timecode_layout.addSpacing(20)  # 縮排
                    
                    self.timecode_toggle = QCheckBox(self.language_manager.get_text("enable_timecode_correction", "啟用時間碼修正"))
                    self.timecode_toggle.setChecked(self.timecode_correction_enabled)
                    self.timecode_toggle.stateChanged.connect(self.on_timecode_toggle_changed)
                    timecode_layout.addWidget(self.timecode_toggle)
                    
                    # 參數輸入欄位
                    timecode_layout.addWidget(QLabel(self.language_manager.get_text("max_duration_label", "最大時長(秒):")))
                    self.timecode_max_input = QLineEdit(str(self.timecode_max_duration))
                    self.timecode_max_input.setMaximumWidth(60)
                    self.timecode_max_input.setEnabled(self.timecode_correction_enabled)
                    timecode_layout.addWidget(self.timecode_max_input)
                    
                    timecode_layout.addWidget(QLabel(self.language_manager.get_text("target_duration_label", "修正為(秒):")))
                    self.timecode_target_input = QLineEdit(str(self.timecode_target_duration))
                    self.timecode_target_input.setMaximumWidth(60)
                    self.timecode_target_input.setEnabled(self.timecode_correction_enabled)
                    timecode_layout.addWidget(self.timecode_target_input)
                    
                    timecode_layout.addStretch()
                    self.workflow_preview_layout.addLayout(timecode_layout)
                    
                elif step_id == "2C":
                    # 為 2C 步驟添加切換按鈕
                    hlayout = QHBoxLayout()
                    label = QLabel(desc)
                    self.ai_toggle_btn = QCheckBox(self.language_manager.get_text("enable_ai_translation", "啟用AI自動翻譯"))
                    
                    if self.one_click_auto_mode:
                        self.ai_toggle_btn.setChecked(True)
                        self.ai_toggle_btn.setEnabled(False)
                        self.ai_toggle_btn.setText(self.language_manager.get_text("ai_translation_forced", "AI自動翻譯 (全自動模式強制啟用)"))
                    else:
                        self.ai_toggle_btn.setChecked(self.ai_auto_translate_enabled)
                        self.ai_toggle_btn.setEnabled(True)
                        
                    self.ai_toggle_btn.stateChanged.connect(self.on_ai_toggle_changed)
                    hlayout.addWidget(label)
                    hlayout.addStretch()
                    hlayout.addWidget(self.ai_toggle_btn)
                    self.workflow_preview_layout.addLayout(hlayout)
                elif step_id == "3B":
                    # 為 3B 步驟添加標籤和 raw 字幕設定
                    hlayout = QHBoxLayout()
                    label = QLabel(desc)
                    hlayout.addWidget(label)
                    hlayout.addStretch()
                    
                    # raw 字幕啟用勾選框
                    self.raw_subtitle_checkbox = QCheckBox(self.language_manager.get_text("generate_raw_subtitle", "生成原文字幕"))
                    self.raw_subtitle_checkbox.setChecked(self.raw_subtitle_enabled)
                    self.raw_subtitle_checkbox.stateChanged.connect(self.on_raw_subtitle_toggle_changed)
                    hlayout.addWidget(self.raw_subtitle_checkbox)
                    
                    # 後綴名稱輸入
                    hlayout.addWidget(QLabel(self.language_manager.get_text("suffix_label", "後綴:")))
                    self.raw_subtitle_suffix_input = QLineEdit(self.raw_subtitle_suffix)
                    self.raw_subtitle_suffix_input.setMaximumWidth(80)
                    self.raw_subtitle_suffix_input.setEnabled(self.raw_subtitle_enabled)
                    self.raw_subtitle_suffix_input.textChanged.connect(self.on_raw_subtitle_suffix_changed)
                    hlayout.addWidget(self.raw_subtitle_suffix_input)
                    
                    self.workflow_preview_layout.addLayout(hlayout)
                else:
                    self.workflow_preview_layout.addWidget(QLabel(desc))

    def clear_layout(self, layout):
        """遞迴清理布局中的所有項"""
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    def on_timecode_toggle_changed(self, state):
        """時間碼修正開關切換事件"""
        self.timecode_correction_enabled = bool(state)
        self.timecode_max_input.setEnabled(self.timecode_correction_enabled)
        self.timecode_target_input.setEnabled(self.timecode_correction_enabled)
        status_text = self.language_manager.get_text("enabled", "啟用") if self.timecode_correction_enabled else self.language_manager.get_text("disabled", "停用")
        self.log_message(self.language_manager.get_text("timecode_status", "時間碼修正已{status}").format(status=status_text))
        
        # 保存設定
        self.settings.setdefault("text_filter", {})
        self.settings["text_filter"]["timecode_correction_enabled"] = self.timecode_correction_enabled
        save_settings(self.settings)

    def on_ai_toggle_changed(self, state):
        self.ai_auto_translate_enabled = bool(state)
        status_text = self.language_manager.get_text("enabled", "啟用") if self.ai_auto_translate_enabled else self.language_manager.get_text("disabled", "停用")
        self.log_message(self.language_manager.get_text("ai_translation_status", "AI自動翻譯已{status}").format(status=status_text))

    def on_raw_subtitle_toggle_changed(self, state):
        """raw字幕生成開關切換事件"""
        self.raw_subtitle_enabled = bool(state)
        if hasattr(self, 'raw_subtitle_suffix_input'):
            self.raw_subtitle_suffix_input.setEnabled(self.raw_subtitle_enabled)
        status_text = self.language_manager.get_text("enabled", "啟用") if self.raw_subtitle_enabled else self.language_manager.get_text("disabled", "停用")
        self.log_message(self.language_manager.get_text("raw_subtitle_status", "原文字幕生成已{status}").format(status=status_text))
        
        # 保存設定
        self.settings.setdefault("raw_subtitle", {})
        self.settings["raw_subtitle"]["enabled"] = self.raw_subtitle_enabled
        save_settings(self.settings)

    def on_raw_subtitle_suffix_changed(self, text):
        """raw字幕後綴名稱變更事件"""
        self.raw_subtitle_suffix = text.strip()
        
        # 保存設定
        self.settings.setdefault("raw_subtitle", {})
        self.settings["raw_subtitle"]["suffix"] = self.raw_subtitle_suffix
        save_settings(self.settings)

    def select_file(self):
        # 重置批次模式狀態
        self.batch_mode = False
        self.batch_files = []
        self.current_batch_index = 0
        self.batch_errors = []
        
        if self.mode_capcut.isChecked():
            default_dir = self.settings["paths"].get("capcut_drafts_dir", os.path.expanduser("~"))
            if not Path(default_dir).is_dir(): default_dir = os.path.expanduser("~")
            file_name, _ = QFileDialog.getOpenFileName(self, self.language_manager.get_text("select_capcut_draft", "選擇 CapCut 的 draft_content.json"), default_dir, "JSON Files (draft_content.json)")
        else:
            # SRT模式
            default_dir = self.settings["paths"].get("srt_input", os.path.expanduser("~"))
            if not Path(default_dir).is_dir(): default_dir = os.path.expanduser("~")
            
            # 如果是SRT模式且啟用全自動模式,提供選擇檔案或資料夾的選項
            if self.one_click_auto_mode:
                # 建立選擇對話框
                choice_dialog = QMessageBox(self)
                choice_dialog.setWindowTitle(self.language_manager.get_text("select_source_type_title", "選擇來源類型"))
                choice_dialog.setText(self.language_manager.get_text("select_source_type_message", "請選擇要處理的來源類型:"))
                choice_dialog.setIcon(QMessageBox.Icon.Question)
                
                btn_file = choice_dialog.addButton(self.language_manager.get_text("single_file_option", "單一SRT檔案"), QMessageBox.ButtonRole.AcceptRole)
                btn_folder = choice_dialog.addButton(self.language_manager.get_text("folder_option", "資料夾(批次處理)"), QMessageBox.ButtonRole.AcceptRole)
                choice_dialog.addButton(self.language_manager.get_text("cancel_button", "取消"), QMessageBox.ButtonRole.RejectRole)
                
                choice_dialog.exec()
                clicked_button = choice_dialog.clickedButton()
                
                if clicked_button == btn_file:
                    # 選擇單一檔案
                    file_name, _ = QFileDialog.getOpenFileName(self, self.language_manager.get_text("file_dialog_title", "選擇來源 SRT 檔案"), default_dir, "SRT Files (*.srt)")
                elif clicked_button == btn_folder:
                    # 選擇資料夾進行批次處理
                    folder_path = QFileDialog.getExistingDirectory(self, self.language_manager.get_text("select_srt_folder", "選擇包含SRT檔案的資料夾"), default_dir)
                    if folder_path:
                        self.scan_and_prepare_batch(folder_path)
                    return
                else:
                    # 取消
                    return
            else:
                # 非全自動模式,只能選擇單一檔案
                file_name, _ = QFileDialog.getOpenFileName(self, self.language_manager.get_text("file_dialog_title", "選擇來源 SRT 檔案"), default_dir, "SRT Files (*.srt)")

        if not file_name: return

        if self.mode_capcut.isChecked() and Path(file_name).name != 'draft_content.json':
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "警告"), self.language_manager.get_text("select_draft_content_warning", "請選擇名稱為 draft_content.json 的檔案"))
            return

        if self.one_click_auto_mode:
            # 全自動模式：自動產生檔名
            file_path_obj = Path(file_name)
            if self.mode_capcut.isChecked():
                # CapCut: 使用父目錄名稱
                self.output_filename = file_path_obj.parent.name
            else:
                 # SRT: 使用檔名 (不含副檔名)
                self.output_filename = file_path_obj.stem
            
            self.log_message(self.language_manager.get_text("auto_mode_filename_set", "全自動模式: 已自動設定輸出檔名為 {filename}").format(filename=self.output_filename))
        else:
            # 手動模式：跳出對話框，並帶入預設值
            file_path_obj = Path(file_name)
            if self.mode_capcut.isChecked():
                # CapCut: 使用父目錄名稱作為預設
                default_name = file_path_obj.parent.name
            else:
                # SRT: 使用檔名_ai 作為預設
                default_name = f"{file_path_obj.stem}_ai"
            dialog = FilenameDialog(self, default_name=default_name)
            if dialog.exec():
                self.output_filename = dialog.get_filename()
            else:
                return # 使用者取消
            
        if self.output_filename: # 確保有檔名 (自動模式必有，手動模式如上判斷)
            if not self.output_filename:
                QMessageBox.warning(self, self.language_manager.get_text("warning_title", "警告"), self.language_manager.get_text("empty_filename_warning", "輸出檔名不可為空"))
                return


            try:
                copy_needed = True
                assigned_input_path = None
                if self.mode_capcut.isChecked():
                    dest_dir = Path(os.getcwd()) / self.settings["paths"]["json_capcut"]
                    dest_path = dest_dir / f"{self.output_filename}.json"
                else:
                    dest_dir = Path(os.getcwd()) / self.settings["paths"]["srt_input"]
                    dest_path = dest_dir / f"{self.output_filename}.srt"
                    
                    source_path = Path(file_name)
                    try:
                        resolved_source = source_path.resolve()
                        resolved_dest = dest_path.resolve()
                    except Exception:
                        resolved_source = source_path
                        resolved_dest = dest_path
                    if resolved_source == resolved_dest:
                        copy_needed = False
                        assigned_input_path = str(resolved_source)
                        self.log_message(f"[資訊] SRT 來源已位於輸入資料夾，略過複製: {resolved_source}")
                    else:
                        self.log_message(f"[偵錯] 1A 將來源檔案複製到輸出路徑: {resolved_source} -> {resolved_dest}")
                
                dest_dir.mkdir(parents=True, exist_ok=True)
                if copy_needed:
                    shutil.copy2(file_name, dest_path)
                    assigned_input_path = str(dest_path)
                    self.log_message(f"檔案已複製到: {dest_path}")
                else:
                    self.log_message(f"[資訊] 使用既有檔案：{assigned_input_path}")

                if assigned_input_path is None:
                    assigned_input_path = str(dest_path)
                
                self.file_label.setText(self.language_manager.get_text("file_label_selected", "來源檔案: {path}").format(path=dest_path))
                self.output_label.setText(self.language_manager.get_text("output_label_set", "輸出檔名: {filename}").format(filename=self.output_filename))
                self.worker.input_file = assigned_input_path
                self.worker.output_filename = self.output_filename
                
                self.log_message(self.language_manager.get_text("file_selected_log", "已選擇檔案: {file}").format(file=file_name))
            except Exception as e:
                self.show_error(f"準備檔案時發生錯誤:{e}")
    
    def scan_and_prepare_batch(self, folder_path):
        """掃描資料夾中的所有SRT檔案並準備批次處理"""
        try:
            self.log_message(f"正在掃描資料夾: {folder_path}")
            
            # 根據設定選擇掃描方式
            srt_files = []
            if self.include_subfolders:
                # 遞迴掃描所有子資料夾
                self.log_message(f"掃描模式: 包含子資料夾")
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if file.lower().endswith('.srt'):
                            full_path = Path(root) / file
                            srt_files.append(full_path)
            else:
                # 只掃描目前資料夾
                self.log_message(f"掃描模式: 僅目前資料夾")
                folder_path_obj = Path(folder_path)
                for file in folder_path_obj.iterdir():
                    if file.is_file() and file.name.lower().endswith('.srt'):
                        srt_files.append(file)
            
            if not srt_files:
                QMessageBox.warning(self, self.language_manager.get_text("warning_title", "警告"), self.language_manager.get_text("no_srt_files_found", "在資料夾 {path} 中未找到任何SRT檔案").format(path=folder_path))
                return
            
            # 按修改時間排序
            srt_files.sort(key=lambda x: x.stat().st_mtime)
            
            # 顯示確認對話框
            file_list_text = "\n".join([f"{i+1}. {f.name} ({f.parent})" for i, f in enumerate(srt_files[:10])])
            if len(srt_files) > 10:
                file_list_text += f"\n... 以及其他 {len(srt_files) - 10} 個檔案"
            
            confirm_msg = f"找到 {len(srt_files)} 個SRT檔案:\n\n{file_list_text}\n\n是否開始批次處理?"
            reply = QMessageBox.question(self, self.language_manager.get_text("confirm_batch_title", "確認批次處理"), confirm_msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.batch_mode = True
                self.batch_files = srt_files
                self.current_batch_index = 0
                self.batch_errors = []
                
                # 更新UI顯示
                self.file_label.setText(self.language_manager.get_text("batch_mode_label", "批次模式: {count} 個檔案待處理").format(count=len(srt_files)))
                self.output_label.setText(self.language_manager.get_text("batch_processing_label", "批次處理模式"))
                
                self.log_message(self.language_manager.get_text("batch_processing_ready", "批次處理已準備完成,共 {count} 個檔案").format(count=len(srt_files)))
            else:
                self.log_message("使用者取消批次處理")
                
        except Exception as e:
            self.show_error(f"掃描資料夾時發生錯誤: {e}")

    def start_processing(self):
        # 檢查批次模式
        if self.batch_mode:
            if not self.batch_files:
                QMessageBox.warning(self, self.language_manager.get_text("warning_title", "警告"), self.language_manager.get_text("no_batch_files_warning", "批次處理模式下沒有待處理的檔案"))
                return
            
            # 重置批次處理狀態
            self.current_batch_index = 0
            self.batch_errors = []
            
            self.run_btn.setEnabled(False)
            self.file_btn.setEnabled(False)
            self.flow_combo.setEnabled(False)
            self.log_text.clear()
            self.progress_bar.setValue(0)
            
            self.log_message(self.language_manager.get_text("batch_start", "開始批次處理,共 {count} 個檔案").format(count=len(self.batch_files)))
            self.process_next_batch_file()
            return
        
        # 單檔處理模式
        if not self.worker.input_file or not self.output_filename:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "警告"), self.language_manager.get_text("no_source_selected_warning", "請先透過按鈕選擇來源檔案並設定輸出檔名"))
            return
        
        
        source_mode = "capcut" if self.mode_capcut.isChecked() else "srt"
        flow_mode = self.flow_combo.currentData()
        self.worker.set_task(self.worker.input_file, self.output_filename, source_mode, flow_mode, auto_mode=self.one_click_auto_mode)

        self.run_btn.setEnabled(False)
        self.file_btn.setEnabled(False)
        self.flow_combo.setEnabled(False)
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.worker.start()
    
    def process_next_batch_file(self):
        """處理批次列表中的下一個檔案"""
        if self.current_batch_index >= len(self.batch_files):
            # 所有檔案處理完成
            self.show_batch_report()
            return
        
        # 取得當前要處理的檔案
        current_file = self.batch_files[self.current_batch_index]
        self.output_filename = current_file.stem  # 使用檔名(不含副檔名)作為輸出檔名
        
        self.log_message(f"\n{'='*60}")
        self.log_message(f"批次處理 ({self.current_batch_index + 1}/{len(self.batch_files)}): {current_file.name}")
        self.log_message(f"{'='*60}")
        
        try:
            # 準備檔案
            dest_dir = Path(os.getcwd()) / self.settings["paths"]["srt_input"]
            dest_path = dest_dir / f"{self.output_filename}.srt"
            
            # 檢查是否需要複製
            copy_needed = True
            try:
                resolved_source = current_file.resolve()
                resolved_dest = dest_path.resolve()
                if resolved_source == resolved_dest:
                    copy_needed = False
                    assigned_input_path = str(resolved_source)
                    self.log_message(f"[資訊] SRT 來源已位於輸入資料夾,略過複製")
                else:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(current_file, dest_path)
                    assigned_input_path = str(dest_path)
                    self.log_message(f"檔案已複製到: {dest_path}")
            except Exception as e:
                self.log_message(f"警告: 檔案複製時發生問題: {e},使用原始路徑")
                assigned_input_path = str(current_file)
            
            # 設定worker並開始處理
            source_mode = "srt"
            flow_mode = self.flow_combo.currentData()
            self.worker.set_task(assigned_input_path, self.output_filename, source_mode, flow_mode, auto_mode=self.one_click_auto_mode)
            self.worker.start()
            
        except Exception as e:
            # 記錄錯誤並繼續下一個
            error_msg = f"準備檔案 {current_file.name} 時發生錯誤: {e}"
            self.log_message(f"錯誤: {error_msg}")
            self.batch_errors.append({
                'file': current_file.name,
                'error': str(e),
                'stage': '檔案準備'
            })
            # 繼續處理下一個檔案
            self.current_batch_index += 1
            self.process_next_batch_file()

    def run_manual_1B_filter(self):
        self.log_message("手動執行 1B 過濾文字管理...")
        self.manual_worker = Manual1BFilterWorker(self)
        self.manual_worker.finished.connect(lambda: self.log_message("1B 過濾文字管理程序執行完成。"))
        self.manual_worker.error.connect(lambda msg: self.show_error(f"1B 過濾文字管理錯誤: {msg}"))
        self.manual_worker.start()

    def run_manual_2A(self):
        self.log_message("手動執行 2A Prompt 管理器...")
        self.manual_worker = Manual2AWorker(self)
        self.manual_worker.finished.connect(lambda: self.log_message("2A Prompt 管理器執行完成。"))
        self.manual_worker.error.connect(lambda msg: self.show_error(f"2A 錯誤: {msg}"))
        self.manual_worker.start()

    def run_manual_2B(self):
        self.log_message("手動執行 2B 標記資料庫管理...")
        self.manual_worker = Manual2BWorker(self)
        self.manual_worker.finished.connect(lambda: self.log_message("2B 標記資料庫管理執行完成。"))
        self.manual_worker.error.connect(lambda msg: self.show_error(f"2B 錯誤: {msg}"))
        self.manual_worker.start()

    def open_ai_settings_dialog(self):
        ai_config = self.settings.get("ai_translation", {}).copy()
        dialog = AITranslationEditorDialog(
            source_file=None,
            target_file=None,
            ai_config=ai_config,
            parent=self,
            mode="settings",
            settings_paths=self.settings.get("paths", {})
        )
        result = dialog.exec()
        # 無論使用者是否在對話框中儲存設定，結束後重新載入設定以確保最新資料
        if result:
            self.log_message("AI 翻譯設定視窗已關閉並套用變更。")
        else:
            self.log_message("AI 翻譯設定視窗已關閉。")
        self.settings = load_settings()

    def process_completed(self):
        # 檢查是否為批次模式
        if self.batch_mode:
            self.log_message(f"檔案 {self.batch_files[self.current_batch_index].name} 處理完成")
            # 移動到下一個檔案
            self.current_batch_index += 1
            
            # 更新整體進度
            overall_progress = int((self.current_batch_index / len(self.batch_files)) * 100)
            self.progress_bar.setValue(overall_progress)
            
            # 繼續處理下一個檔案
            self.process_next_batch_file()
        else:
            # 單檔處理模式
            # 在全自動模式下，開啟 SRT 輸出資料夾
            if self.one_click_auto_mode:
                srt_output_folder = Path(os.getcwd()) / self.settings["paths"]["srt_output"]
                if srt_output_folder.exists():
                    try:
                        if os.name == 'nt':
                            os.startfile(str(srt_output_folder))
                        else:
                            subprocess.call(['xdg-open', str(srt_output_folder)])
                        self.log_message(f"已開啟 SRT 輸出資料夾: {srt_output_folder}")
                    except Exception as e:
                        self.log_message(f"無法開啟 SRT 輸出資料夾: {e}")
            
            self.run_btn.setEnabled(True)
            self.file_btn.setEnabled(True)
            self.flow_combo.setEnabled(True)
            self.log_message(self.language_manager.get_text("batch_all_complete", "所有處理已完成！"))
            QMessageBox.information(self, self.language_manager.get_text("completion_title", "完成"), self.language_manager.get_text("process_completed", "選擇的流程已成功執行完畢！"))

    def show_error(self, error_message):
        # 檢查是否為批次模式
        if self.batch_mode:
            # 記錄錯誤
            current_file = self.batch_files[self.current_batch_index]
            self.batch_errors.append({
                'file': current_file.name,
                'error': error_message,
                'stage': '處理過程'
            })
            self.log_message(f"錯誤: {error_message}")
            self.log_message(f"跳過檔案 {current_file.name},繼續處理下一個...")
            
            # 繼續處理下一個檔案
            self.current_batch_index += 1
            self.process_next_batch_file()
        else:
            # 單檔處理模式
            self.run_btn.setEnabled(True)
            self.file_btn.setEnabled(True)
            self.flow_combo.setEnabled(True)
            self.log_message(f"錯誤: {error_message}")
            self.status_label.setText("發生錯誤！")
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "錯誤"), str(error_message))
        
    def show_translation_editor(self, source_file, target_file):
        self.log_message("流程暫停，等待使用者輸入翻譯結果...")

        # 檢查是否啟用AI翻譯（優先使用流程預覽中的切換按鈕狀態）
        ai_config = self.settings.get("ai_translation", {})
        use_ai_translation = self.ai_auto_translate_enabled

        if use_ai_translation:
            # 使用新的AI翻譯編輯器對話框（帶獨立進度窗口）
            dialog = AITranslationEditorDialog(
                source_file=source_file,
                target_file=target_file,
                ai_config=ai_config,
                parent=self,
                mode="translation",
                settings_paths=self.settings.get("paths", {})
            )
            if dialog.exec():
                self.log_message("2C: 翻譯結果輸入完成，流程將繼續執行。")
                self.worker.resume_process()
            else:
                self.worker.error_occurred.emit("使用者取消了翻譯輸入，流程已中止。")
        else:
            # 使用原有的手動翻譯編輯器
            dialog = TranslationEditorDialog(source_file, target_file, self)
            if dialog.exec():
                self.log_message("2C: 翻譯結果輸入完成，流程將繼續執行。")
                self.worker.resume_process()
            else:
                self.worker.error_occurred.emit("使用者取消了翻譯輸入，流程已中止。")
    
    def show_batch_report(self):
        """顯示批次處理完成報告"""
        self.run_btn.setEnabled(True)
        self.file_btn.setEnabled(True)
        self.flow_combo.setEnabled(True)
        self.progress_bar.setValue(100)
        
        # 在全自動模式下，開啟 SRT 輸出資料夾
        if self.one_click_auto_mode:
            srt_output_folder = Path(os.getcwd()) / self.settings["paths"]["srt_output"]
            if srt_output_folder.exists():
                try:
                    if os.name == 'nt':
                        os.startfile(str(srt_output_folder))
                    else:
                        subprocess.call(['xdg-open', str(srt_output_folder)])
                    self.log_message(f"批次處理完成，已開啟 SRT 輸出資料夾: {srt_output_folder}")
                except Exception as e:
                    self.log_message(f"無法開啟 SRT 輸出資料夾: {e}")
        
        total_files = len(self.batch_files)
        success_count = total_files - len(self.batch_errors)
        error_count = len(self.batch_errors)
        
        # 建立報告訊息
        report_msg = f"批次處理完成!\n\n"
        report_msg += f"總檔案數: {total_files}\n"
        report_msg += f"成功: {success_count}\n"
        report_msg += f"失敗: {error_count}\n"
        
        if self.batch_errors:
            report_msg += f"\n失敗檔案清單:\n"
            for i, error_info in enumerate(self.batch_errors, 1):
                report_msg += f"{i}. {error_info['file']}\n"
                report_msg += f"   階段: {error_info['stage']}\n"
                report_msg += f"   錯誤: {error_info['error']}\n\n"
        
        self.log_message("\n" + "="*60)
        self.log_message("批次處理報告")
        self.log_message("="*60)
        self.log_message(report_msg)
        
        # 顯示對話框
        if error_count > 0:
            QMessageBox.warning(self, self.language_manager.get_text("batch_complete_with_errors", "批次處理完成(有錯誤)"), report_msg)
        else:
            QMessageBox.information(self, self.language_manager.get_text("batch_complete", "批次處理完成"), report_msg)
        
        # 重置批次模式
        self.batch_mode = False
        self.batch_files = []
        self.current_batch_index = 0
        self.batch_errors = []

    def update_progress(self, value, message):
        if value >= 0:
            self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self.log_message(message)

    def retranslate_ui(self):
        """重新翻譯界面元素"""
        self.setWindowTitle(self.language_manager.get_text("app_title", "字幕AI翻譯系統 v0.89.05"))
        self.settings_btn.setText(self.language_manager.get_text("settings_button", "系統設定"))

        # 更新各個群組標題
        self.findChild(QGroupBox, "source_group").setTitle(self.language_manager.get_text("source_group_title", "步驟 1: 選擇來源"))
        self.findChild(QGroupBox, "flow_group").setTitle(self.language_manager.get_text("flow_group_title", "步驟 2: 選擇執行流程"))
        self.findChild(QGroupBox, "manual_tools_group").setTitle(self.language_manager.get_text("manual_tools_group_title", "手動工具"))
        self.findChild(QGroupBox, "run_group").setTitle(self.language_manager.get_text("run_group_title", "步驟 3: 執行與狀態"))

        # 更新來源模式元件
        # 找到來源模式區域的標籤並更新
        for child in self.findChild(QGroupBox, "source_group").findChildren(QLabel):
            if child.text().startswith("來源模式") or child.text().startswith("Source mode"):
                child.setText(self.language_manager.get_text("source_mode_label", "來源模式:"))
                break

        # 更新單選按鈕
        self.mode_capcut.setText(self.language_manager.get_text("capcut_subtitle_parsing", "CapCut字幕解析"))
        self.mode_srt.setText(self.language_manager.get_text("srt_file_parsing", "SRT檔案拆解"))
        self.auto_mode_checkbox.setText(self.language_manager.get_text("one_click_auto_mode", "一鍵全自動模式 (One-Click Auto)"))
        self.include_subfolders_checkbox.setText(self.language_manager.get_text("include_subfolders", "包含子資料夾"))

        # 更新工具按鈕文本
        self.file_btn.setText(self.language_manager.get_text("select_file_button", "選擇來源檔案並設定輸出檔名"))
        self.findChild(QPushButton, "btn_1b").setText(self.language_manager.get_text("btn_1b_text", "1B 過濾文字管理"))
        self.findChild(QPushButton, "btn_2a").setText(self.language_manager.get_text("btn_2a_text", "2A prompt管理"))
        self.findChild(QPushButton, "btn_2b").setText(self.language_manager.get_text("btn_2b_text", "2B 標記資料庫管理"))
        self.ai_settings_dialog_btn.setText(self.language_manager.get_text("btn_ai_settings_text", "AI 翻譯設定 / Prompt"))
        self.run_btn.setText(self.language_manager.get_text("start_button", "開始執行"))

        # 更新狀態文本
        self.status_label.setText(self.language_manager.get_text("status_ready", "就緒"))
        
        # 更新來源檔案和輸出檔名標籤
        self.file_label.setText(self.language_manager.get_text("file_label", "來源檔案: 尚未選擇"))
        self.output_label.setText(self.language_manager.get_text("output_label", "輸出檔名: 尚未設定"))
        
        # 更新流程預覽標題
        self.workflow_preview_box.setTitle(self.language_manager.get_text("workflow_preview_box_title", "流程預覽"))

        # 更新流程選單
        self.flow_combo.clear()
        flow_map = {
            "full_flow": "flow_full",
            "parse_only": "flow_parse",
            "translate_raw": "flow_translate_raw",
            "filter_only": "flow_filter",
            "filter_translate": "flow_filter_translate",
            "mark_translate": "flow_mark_translate"
        }
        for flow_id, flow_data in FLOWS.items():
            self.flow_combo.addItem(self.language_manager.get_text(flow_map.get(flow_id, flow_id), flow_data["name"]), flow_id)

        # 更新流程預覽
        self.update_flow_description()

    def log_message(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    if getattr(sys, 'frozen', False):
        os.chdir(sys._MEIPASS)
    main()
