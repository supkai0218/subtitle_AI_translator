#v0.88.03 新增SRT批次處理功能 (資料夾模式)
#v0.88.02 一鍵全自動翻譯驗證功能bug fix
#v0.88.01 新增一鍵全自動翻譯


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
from modules.text_filter_v01 import TextFilter
from modules.text_marker import SensitiveWordReplacer
from modules.translation_editor_dialog_v0 import TranslationEditorDialog
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
from modules.ai_validator import TranslationValidator
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

STEP_DESCRIPTIONS = {
    "1A": "1A: CapCut字幕解析或SRT檔案拆解",
    "1B": "1B: 文字過濾 (同步處理時間軸)",
    "1C": "1C: 特殊詞標記",
    "1D": "1D: 準備AI翻譯檔案",
    "2C": "2C: AI自動翻譯或手動翻譯",
    "3A": "3A: 標記文字還原",
    "3B": "3B: 生成SRT檔案 (翻譯+原文)"
}

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
        "max_concurrent_requests": 5,
        "enable_validation": True,
        "prompts": {
            "system_prompt": "",
            "user_prompt_template": ""
        }
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

            return settings
        except Exception:
            pass
    default_settings = copy.deepcopy(DEFAULT_SETTINGS)
    default_settings.setdefault("paths", {})
    default_settings["paths"]["settings_file"] = make_portable_path(settings_file)
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
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系統設定")
        self.resize(700, 650)
        self.current_settings = current_settings.copy()
        self.inputs = {}
        self.ai_inputs = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 使用分頁式界面
        tab_widget = QTabWidget()
        
        # 路徑設定分頁
        paths_tab = QWidget()
        self.setup_paths_tab(paths_tab)
        tab_widget.addTab(paths_tab, "路徑設定")
        
        # AI翻譯設定分頁
        ai_tab = QWidget()
        self.setup_ai_tab(ai_tab)
        tab_widget.addTab(ai_tab, "AI翻譯設定")
        
        layout.addWidget(tab_widget)
        
        # 按鈕區域
        btn_layout = QHBoxLayout()
        restore_btn = QPushButton("恢復預設值")
        restore_btn.clicked.connect(self.restore_defaults)
        save_btn = QPushButton("儲存")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
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
            "capcut_drafts_dir": "CapCut專案預設開啟目錄:",
            "txt_1A": "1A 字幕/時間軸資料夾:", "txt_1B": "1B 過濾後文字資料夾:",
            "txt_1C": "1C 標記後文字資料夾:", "txt_2B": "2C 翻譯結果資料夾:",
            "txt_3A": "3A 標記還原資料夾:", "ai": "AI 交換資料夾:",
            "json_capcut": "CapCut JSON 儲存資料夾:", "json_bak_markers": "標記備份資料夾:",
            "srt_input": "SRT 來源資料夾:", "srt_output": "SRT 輸出資料夾:",
            "markers_db": "標記資料庫檔案:", "script_2A": "2A prompt管理腳本:",
            "script_2B": "2B 標記管理腳本:", "script_1B_filter": "1B 過濾管理腳本:",
            "filter_patterns_db": "1B 過濾文字資料庫檔案:",
            "prompt_templates_db": "Prompt 模板資料庫檔案:",
            "settings_file": "系統設定檔案位置:"
        }

        for key in dir_keys:
            le = QLineEdit(self.current_settings["paths"].get(key, ""))
            btn = QPushButton("瀏覽")
            btn.clicked.connect(lambda checked, le=le: self.browse_directory(le))
            hlayout = QHBoxLayout()
            hlayout.addWidget(le)
            hlayout.addWidget(btn)
            form_layout.addRow(key_descriptions.get(key, f"{key}:"), hlayout)
            self.inputs[key] = le

        for key in file_keys:
            le = QLineEdit(self.current_settings["paths"].get(key, ""))
            btn = QPushButton("瀏覽")
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
        api_group = QGroupBox("API設定")
        api_layout = QFormLayout(api_group)
        
        # API供應商
        self.ai_inputs["api_provider"] = QComboBox()
        providers = ["openrouter", "openai", "anthropic", "custom"]
        self.ai_inputs["api_provider"].addItems(providers)
        current_provider = ai_config.get("api_provider", "openrouter")
        if current_provider in providers:
            self.ai_inputs["api_provider"].setCurrentText(current_provider)
        api_layout.addRow("API供應商:", self.ai_inputs["api_provider"])
        
        # API URL
        self.ai_inputs["api_url"] = QLineEdit(ai_config.get("api_url", "https://openrouter.ai/api/v1/chat/completions"))
        api_layout.addRow("API網址:", self.ai_inputs["api_url"])
        
        # API Key
        self.ai_inputs["api_key"] = QLineEdit(ai_config.get("api_key", ""))
        self.ai_inputs["api_key"].setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API金鑰:", self.ai_inputs["api_key"])
        
        # 模型
        self.ai_inputs["model"] = QLineEdit(ai_config.get("model", "anthropic/claude-3-sonnet"))
        api_layout.addRow("模型名稱:", self.ai_inputs["model"])
        
        form_layout.addRow("", api_group)
        
        # 翻譯設定
        translate_group = QGroupBox("翻譯設定")
        translate_layout = QFormLayout(translate_group)
        
        # 來源語言
        self.ai_inputs["source_language"] = QComboBox()
        languages = ["ja", "en", "ko", "zh-CN", "zh-TW"]
        self.ai_inputs["source_language"].addItems(languages)
        current_source = ai_config.get("source_language", "ja")
        if current_source in languages:
            self.ai_inputs["source_language"].setCurrentText(current_source)
        translate_layout.addRow("來源語言:", self.ai_inputs["source_language"])
        
        # 目標語言
        self.ai_inputs["target_language"] = QComboBox()
        self.ai_inputs["target_language"].addItems(languages)
        current_target = ai_config.get("target_language", "zh-TW")
        if current_target in languages:
            self.ai_inputs["target_language"].setCurrentText(current_target)
        translate_layout.addRow("目標語言:", self.ai_inputs["target_language"])
        
        # 批次大小（移除上限限制）
        self.ai_inputs["batch_size"] = QSpinBox()
        self.ai_inputs["batch_size"].setRange(1, 9999)
        self.ai_inputs["batch_size"].setValue(ai_config.get("batch_size", 10))
        translate_layout.addRow("批次大小:", self.ai_inputs["batch_size"])
        
        # 並行請求數
        self.ai_inputs["max_concurrent_requests"] = QSpinBox()
        self.ai_inputs["max_concurrent_requests"].setRange(1, 20)
        self.ai_inputs["max_concurrent_requests"].setValue(ai_config.get("max_concurrent_requests", 5))
        translate_layout.addRow("最大並行請求數:", self.ai_inputs["max_concurrent_requests"])
        
        # 翻譯驗證
        self.ai_inputs["enable_validation"] = QCheckBox("啟用翻譯結果驗證")
        self.ai_inputs["enable_validation"].setChecked(ai_config.get("enable_validation", True))
        translate_layout.addRow("", self.ai_inputs["enable_validation"])
        
        # 重試設定
        self.ai_inputs["max_retries"] = QSpinBox()
        self.ai_inputs["max_retries"].setRange(1, 10)
        self.ai_inputs["max_retries"].setValue(ai_config.get("max_retries", 3))
        translate_layout.addRow("最大重試次數:", self.ai_inputs["max_retries"])
        
        self.ai_inputs["retry_delay"] = QSpinBox()
        self.ai_inputs["retry_delay"].setRange(1, 30)
        self.ai_inputs["retry_delay"].setValue(ai_config.get("retry_delay", 2))
        translate_layout.addRow("重試延遲(秒):", self.ai_inputs["retry_delay"])
        
        form_layout.addRow("", translate_group)
        
        # Prompt設定
        prompt_group = QGroupBox("Prompt設定")
        prompt_layout = QFormLayout(prompt_group)

        prompts_config = ai_config.get("prompts", {})

        # System Prompt
        self.ai_inputs["system_prompt"] = QTextEdit()
        self.ai_inputs["system_prompt"].setMaximumHeight(80)
        self.ai_inputs["system_prompt"].setPlainText(prompts_config.get("system_prompt", ""))
        prompt_layout.addRow("系統提示詞:", self.ai_inputs["system_prompt"])

        # User Prompt Template
        self.ai_inputs["user_prompt_template"] = QTextEdit()
        self.ai_inputs["user_prompt_template"].setMaximumHeight(80)
        self.ai_inputs["user_prompt_template"].setPlainText(prompts_config.get("user_prompt_template", ""))
        prompt_layout.addRow("用戶提示詞模板:", self.ai_inputs["user_prompt_template"])

        form_layout.addRow("", prompt_group)
        
        layout.addLayout(form_layout)

    def browse_directory(self, line_edit):
        directory = QFileDialog.getExistingDirectory(self, "選擇目錄", line_edit.text())
        if directory:
            line_edit.setText(directory)

    def browse_file(self, line_edit):
        filename, _ = QFileDialog.getOpenFileName(self, "選擇檔案", line_edit.text())
        if filename:
            line_edit.setText(filename)

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

        # 恢復Prompt設定預設值
        prompt_defaults = ai_defaults["prompts"]
        self.ai_inputs["system_prompt"].setPlainText(prompt_defaults["system_prompt"])
        self.ai_inputs["user_prompt_template"].setPlainText(prompt_defaults["user_prompt_template"])

    def get_settings(self):
        new_settings = {
            "paths": {},
            "ai_translation": {
                "prompts": {}
            }
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

        # 保存Prompt設定
        new_settings["ai_translation"]["prompts"]["system_prompt"] = self.ai_inputs["system_prompt"].toPlainText().strip()
        new_settings["ai_translation"]["prompts"]["user_prompt_template"] = self.ai_inputs["user_prompt_template"].toPlainText().strip()

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
            
            self.progress_updated.emit(10, "執行 1A: 字幕/時間軸拆解...")
            self.run_1A_parse()

            if self.flow_mode == "full_flow":
                self.run_1B_filter()
                self.run_1C_mark(from_stage='1B')
                self.run_1D_copy_for_ai(from_stage='1C')
                self.run_2C_get_translation()
                self.run_3A_replace_markers()
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
        
        # 假設 TextFilter 內部會處理時間軸
        self.log("重要提示：請確保您的 TextFilter 模組能同步處理時間軸，生成 1B-time 檔案。")
        text_filter = TextFilter(settings_paths=self.settings)
        success, msg = text_filter.process_file(str(txt_in_file), self.output_filename)
        if not success: raise Exception(f"1B 階段失敗: {msg}")
        self.log(f"1B: 過濾完成。")

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
        if self.auto_mode:
            self.run_2C_auto_translation()
            return

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
            
        # --- 新增：驗證與清理結果 ---
        self.log("正在驗證並清理翻譯結果...")
        validator = TranslationValidator(ai_config)
        is_valid, repaired_result, validation_msg = validator.validate_response(response, len(lines))
        
        if not is_valid:
            self.log(f"警告: 翻譯驗證未完全通過: {validation_msg}")
        
        # 將 repaired_result (List[str]) 轉換回文字內容
        # 這裡需要移除 validate_response 返回的 "序號:內容" 中的序號，只保留翻譯文字
        cleaned_translations = []
        for line in repaired_result:
            if ':' in line:
                _, content = line.split(':', 1)
                cleaned_translations.append(content.strip())
            else:
                cleaned_translations.append(line.strip())
        
        combined_cleaned_response = "\n".join(cleaned_translations)
            
        # 儲存結果
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(combined_cleaned_response)
            
        self.log(f"2C: AI 自動翻譯完成 (與驗證)，已寫入 {target_file.name}")
        
    def run_3A_replace_markers(self):
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

        # 條件式生成 raw 版字幕
        raw_text_file = self.base_path / self.settings['txt_1B'] / f"1B-txt_{self.output_filename}.txt"
        raw_time_file = self.base_path / self.settings['txt_1B'] / f"1B-time_{self.output_filename}.txt"
        if raw_text_file.exists() and raw_time_file.exists():
            srt_raw_out_file = output_dir / f"{self.output_filename}_raw.srt"
            success, msg = merger.merge_files(self.output_filename, str(raw_text_file), str(raw_time_file), str(srt_raw_out_file))
            if not success: 
                self.log(f"警告: 合併原文raw字幕失敗: {msg}")
            else:
                shutil.copy2(srt_raw_out_file, ai_folder / srt_raw_out_file.name) # 複製到 AI 資料夾
        else:
            self.log("資訊: 找不到1B階段檔案，跳過生成原文raw字幕。")
        
        # 檢查並開啟 AI 資料夾
        if not self.ai_folder_opened:
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定輸出檔案名稱")
        self.setModal(True)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel("請輸入輸出檔名 (不含副檔名):"))
        self.name_input = QLineEdit()
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
        self.setWindowTitle("字幕AI翻譯系統 v0.88.03")
        self.resize(700, 750)
        self.output_filename = None
        self.settings = load_settings()
        self.ai_auto_translate_enabled = False  # 新增:追蹤AI自動翻譯啟用狀態
        self.one_click_auto_mode = False # 新增:一鍵全自動模式狀態
        # 批次處理相關屬性
        self.batch_mode = False  # 是否為批次處理模式
        self.batch_files = []  # 待處理的檔案列表
        self.current_batch_index = 0  # 當前處理的檔案索引
        self.batch_errors = []  # 記錄批次處理中的錯誤
        self.setup_ui()
        self.worker = ProcessWorker(self)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.process_complete.connect(self.process_completed)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.show_translation_editor.connect(self.show_translation_editor)
        self.manual_worker = None

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
        source_layout = QVBoxLayout(source_group)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("來源模式:"))
        self.mode_capcut = QRadioButton("CapCut字幕解析")
        self.mode_srt = QRadioButton("SRT檔案拆解")
        self.mode_capcut.setChecked(True)
        mode_layout.addWidget(self.mode_capcut)
        mode_layout.addWidget(self.mode_srt)
        
        # 新增：一鍵全自動模式勾選框
        self.auto_mode_checkbox = QCheckBox("一鍵全自動模式 (One-Click Auto)")
        self.auto_mode_checkbox.setChecked(False)
        self.auto_mode_checkbox.stateChanged.connect(self.on_auto_mode_changed)
        mode_layout.addWidget(self.auto_mode_checkbox)
        
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
        flow_layout = QVBoxLayout(flow_group)
        self.flow_combo = QComboBox()
        for flow_id, flow_data in FLOWS.items():
            self.flow_combo.addItem(flow_data["name"], flow_id)
        self.flow_combo.currentIndexChanged.connect(self.update_flow_description)
        flow_layout.addWidget(self.flow_combo)

        self.workflow_preview_box = QGroupBox("流程預覽")
        self.workflow_preview_layout = QVBoxLayout(self.workflow_preview_box)
        flow_layout.addWidget(self.workflow_preview_box)
        layout.addWidget(flow_group)
        self.update_flow_description()

        manual_tools_group = QGroupBox("手動工具")
        manual_tools_layout = QHBoxLayout(manual_tools_group)
        btn_1b = QPushButton("1B 過濾文字管理")
        btn_2a = QPushButton("2A prompt管理")
        btn_2b = QPushButton("2B 標記資料庫管理")
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
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.get_settings()
            save_settings(self.settings)
            self.log_message("系統設定已儲存。")
            
    def on_auto_mode_changed(self, state):
        self.one_click_auto_mode = bool(state)
        self.update_flow_description() # 更新流程描述以反映自動模式狀態
        mode_text = "啟用" if self.one_click_auto_mode else "停用"
        self.log_message(f"一鍵全自動模式已{mode_text}")

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
            for step_id in steps:
                # 處理 '3B_raw' 這種特殊標記
                clean_step_id = step_id.split('_')[0]
                desc = STEP_DESCRIPTIONS.get(step_id, STEP_DESCRIPTIONS.get(clean_step_id, f"{step_id}: 未知步驟"))

                if step_id == "2C":
                    # 為 2C 步驟添加切換按鈕
                    hlayout = QHBoxLayout()
                    label = QLabel(desc)
                    self.ai_toggle_btn = QCheckBox("啟用AI自動翻譯")
                    
                    if self.one_click_auto_mode:
                        self.ai_toggle_btn.setChecked(True)
                        self.ai_toggle_btn.setEnabled(False)
                        self.ai_toggle_btn.setText("AI自動翻譯 (全自動模式強制啟用)")
                    else:
                        self.ai_toggle_btn.setChecked(self.ai_auto_translate_enabled)
                        self.ai_toggle_btn.setEnabled(True)
                        
                    self.ai_toggle_btn.stateChanged.connect(self.on_ai_toggle_changed)
                    hlayout.addWidget(label)
                    hlayout.addStretch()
                    hlayout.addWidget(self.ai_toggle_btn)
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

    def on_ai_toggle_changed(self, state):
        self.ai_auto_translate_enabled = bool(state)
        self.log_message(f"AI自動翻譯已{'啟用' if self.ai_auto_translate_enabled else '停用'}")

    def select_file(self):
        # 重置批次模式狀態
        self.batch_mode = False
        self.batch_files = []
        self.current_batch_index = 0
        self.batch_errors = []
        
        if self.mode_capcut.isChecked():
            default_dir = self.settings["paths"].get("capcut_drafts_dir", os.path.expanduser("~"))
            if not Path(default_dir).is_dir(): default_dir = os.path.expanduser("~")
            file_name, _ = QFileDialog.getOpenFileName(self, "選擇 CapCut 的 draft_content.json", default_dir, "JSON Files (draft_content.json)")
        else:
            # SRT模式
            default_dir = self.settings["paths"].get("srt_input", os.path.expanduser("~"))
            if not Path(default_dir).is_dir(): default_dir = os.path.expanduser("~")
            
            # 如果是SRT模式且啟用全自動模式,提供選擇檔案或資料夾的選項
            if self.one_click_auto_mode:
                # 建立選擇對話框
                choice_dialog = QMessageBox(self)
                choice_dialog.setWindowTitle("選擇來源類型")
                choice_dialog.setText("請選擇要處理的來源類型:")
                choice_dialog.setIcon(QMessageBox.Icon.Question)
                
                btn_file = choice_dialog.addButton("單一SRT檔案", QMessageBox.ButtonRole.AcceptRole)
                btn_folder = choice_dialog.addButton("資料夾(批次處理)", QMessageBox.ButtonRole.AcceptRole)
                choice_dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                
                choice_dialog.exec()
                clicked_button = choice_dialog.clickedButton()
                
                if clicked_button == btn_file:
                    # 選擇單一檔案
                    file_name, _ = QFileDialog.getOpenFileName(self, "選擇來源 SRT 檔案", default_dir, "SRT Files (*.srt)")
                elif clicked_button == btn_folder:
                    # 選擇資料夾進行批次處理
                    folder_path = QFileDialog.getExistingDirectory(self, "選擇包含SRT檔案的資料夾", default_dir)
                    if folder_path:
                        self.scan_and_prepare_batch(folder_path)
                    return
                else:
                    # 取消
                    return
            else:
                # 非全自動模式,只能選擇單一檔案
                file_name, _ = QFileDialog.getOpenFileName(self, "選擇來源 SRT 檔案", default_dir, "SRT Files (*.srt)")

        if not file_name: return

        if self.mode_capcut.isChecked() and Path(file_name).name != 'draft_content.json':
            QMessageBox.warning(self, "警告", "請選擇名稱為 draft_content.json 的檔案")
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
            
            self.log_message(f"全自動模式: 已自動設定輸出檔名為 {self.output_filename}")
        else:
            # 手動模式：跳出對話框
            dialog = FilenameDialog(self)
            if dialog.exec():
                self.output_filename = dialog.get_filename()
            else:
                return # 使用者取消
            
        if self.output_filename: # 確保有檔名 (自動模式必有，手動模式如上判斷)
            if not self.output_filename:
                QMessageBox.warning(self, "警告", "輸出檔名不可為空")
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
                
                self.file_label.setText(f"來源檔案: {dest_path}")
                self.output_label.setText(f"輸出檔名: {self.output_filename}")
                self.worker.input_file = assigned_input_path
                self.worker.output_filename = self.output_filename
                
                self.log_message(f"已選擇檔案: {file_name}")
            except Exception as e:
                self.show_error(f"準備檔案時發生錯誤:{e}")
    
    def scan_and_prepare_batch(self, folder_path):
        """掃描資料夾中的所有SRT檔案並準備批次處理"""
        try:
            self.log_message(f"正在掃描資料夾: {folder_path}")
            
            # 遞迴掃描所有.srt檔案
            srt_files = []
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.srt'):
                        full_path = Path(root) / file
                        srt_files.append(full_path)
            
            if not srt_files:
                QMessageBox.warning(self, "警告", f"在資料夾 {folder_path} 中未找到任何SRT檔案")
                return
            
            # 按修改時間排序
            srt_files.sort(key=lambda x: x.stat().st_mtime)
            
            # 顯示確認對話框
            file_list_text = "\n".join([f"{i+1}. {f.name} ({f.parent})" for i, f in enumerate(srt_files[:10])])
            if len(srt_files) > 10:
                file_list_text += f"\n... 以及其他 {len(srt_files) - 10} 個檔案"
            
            confirm_msg = f"找到 {len(srt_files)} 個SRT檔案:\n\n{file_list_text}\n\n是否開始批次處理?"
            reply = QMessageBox.question(self, "確認批次處理", confirm_msg, 
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.batch_mode = True
                self.batch_files = srt_files
                self.current_batch_index = 0
                self.batch_errors = []
                
                # 更新UI顯示
                self.file_label.setText(f"批次模式: {len(srt_files)} 個檔案待處理")
                self.output_label.setText(f"批次處理模式")
                
                self.log_message(f"批次處理已準備完成,共 {len(srt_files)} 個檔案")
            else:
                self.log_message("使用者取消批次處理")
                
        except Exception as e:
            self.show_error(f"掃描資料夾時發生錯誤: {e}")

    def start_processing(self):
        # 檢查批次模式
        if self.batch_mode:
            if not self.batch_files:
                QMessageBox.warning(self, "警告", "批次處理模式下沒有待處理的檔案")
                return
            
            # 重置批次處理狀態
            self.current_batch_index = 0
            self.batch_errors = []
            
            self.run_btn.setEnabled(False)
            self.file_btn.setEnabled(False)
            self.flow_combo.setEnabled(False)
            self.log_text.clear()
            self.progress_bar.setValue(0)
            
            self.log_message(f"開始批次處理,共 {len(self.batch_files)} 個檔案")
            self.process_next_batch_file()
            return
        
        # 單檔處理模式
        if not self.worker.input_file or not self.output_filename:
            QMessageBox.warning(self, "警告", "請先透過按鈕選擇來源檔案並設定輸出檔名")
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
            self.run_btn.setEnabled(True)
            self.file_btn.setEnabled(True)
            self.flow_combo.setEnabled(True)
            self.log_message("所有處理已完成！")
            QMessageBox.information(self, "完成", "選擇的流程已成功執行完畢！")

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
            QMessageBox.critical(self, "錯誤", str(error_message))
        
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
            QMessageBox.warning(self, "批次處理完成(有錯誤)", report_msg)
        else:
            QMessageBox.information(self, "批次處理完成", report_msg)
        
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
