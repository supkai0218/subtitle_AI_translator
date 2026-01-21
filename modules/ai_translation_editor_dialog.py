#v0.89.02 新增介面語言包切換功能(繁中/英文，介面切換進度80%)
#v0.88.02 一鍵全自動翻譯驗證功能bug fix
#V0.88.01 支援一鍵全自動翻譯
#V0.87.06 支援Prompt_manager模板資料庫路徑設定
#V0.87.04 AI翻譯編輯器於主介面可編輯設定

import sys
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QSplitter, QGroupBox, QProgressBar, QMessageBox,
    QComboBox, QLineEdit, QFormLayout, QTabWidget, QWidget, QCheckBox,
    QSpinBox, QScrollArea, QInputDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from pathlib import Path
from typing import Dict, List, Optional
import json

from .ai_translator import AITranslator
from .ai_validator import TranslationValidator
from .prompt_manager import PromptManager
from .settings_path import resolve_settings_file, resolve_settings_asset
import time

def get_ai_prompt_path():
    return resolve_settings_asset("AI_prompt.json")

class AITranslationWorker(QThread):
    """AI翻譯工作執行緒 - 使用v1b翻譯器 + v0驗證器"""
    progress_updated = pyqtSignal(str)
    translation_completed = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ai_config: Dict, text_lines: List[str], context_info: Dict):
        super().__init__()
        self.ai_config = ai_config
        self.text_lines = text_lines
        self.context_info = context_info
        self.translator = None
        self.validator = None
    
    def run(self):
        try:
            # 初始化翻譯器和驗證器
            self.progress_updated.emit("初始化AI翻譯器...")
            self.translator = AITranslator(self.ai_config)
            self.validator = TranslationValidator(self.ai_config)
            
            # 驗證API連線
            self.progress_updated.emit("驗證API連線...")
            success, msg = self.translator.validate_api_connection()
            if not success:
                self.error_occurred.emit(f"API連線失敗: {msg}")
                return
            self.progress_updated.emit(f"✓ {msg}")
            
            # 執行翻譯（帶重試機制）
            max_retries = self.ai_config.get("max_retries", 3)
            retry_delay = self.ai_config.get("retry_delay", 2)
            
            for attempt in range(max_retries):
                self.progress_updated.emit(f"\n翻譯嘗試 {attempt + 1}/{max_retries}...")
                
                # 調用翻譯器（返回原始響應）
                success, raw_response, error_msg = self.translator.translate_batch(self.text_lines)
                
                if not success:
                    self.progress_updated.emit(f"✗ 翻譯失敗: {error_msg}")
                    if attempt < max_retries - 1:
                        self.progress_updated.emit(f"等待 {retry_delay} 秒後重試...")
                        time.sleep(retry_delay)
                    continue
                
                self.progress_updated.emit("✓ 翻譯完成，驗證結果...")
                
                # 驗證響應
                is_valid, parsed_translations, validation_msg = self.validator.validate_response(
                    raw_response, 
                    len(self.text_lines)
                )
                
                if is_valid:
                    self.progress_updated.emit(f"✓ 驗證通過: {validation_msg}")
                    self.translation_completed.emit(parsed_translations)
                    return
                else:
                    self.progress_updated.emit(f"✗ 驗證失敗: {validation_msg}")
                    if attempt < max_retries - 1:
                        self.progress_updated.emit(f"等待 {retry_delay} 秒後重試...")
                        time.sleep(retry_delay)
            
            # 所有重試都失敗
            self.error_occurred.emit(
                f"AI翻譯失敗: 經過 {max_retries} 次嘗試後仍無法獲得有效的翻譯結果"
            )
                
        except Exception as e:
            import traceback
            error_msg = f"翻譯過程發生錯誤: {str(e)}\n{traceback.format_exc()}"
            self.error_occurred.emit(error_msg)

class TranslationProgressWindow(QDialog):
    """獨立的翻譯進度窗口 - 實時顯示翻譯和驗證進度"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 初始化語言管理器
        from modules.language_manager import LanguageManager
        self.language_manager = LanguageManager()

        # 從父視窗獲取語言管理器（如果存在），否則使用預設
        if parent and hasattr(parent, 'language_manager'):
            self.language_manager = parent.language_manager

        self.setWindowTitle(self.language_manager.get_text("progress_window_title", "AI Translation Progress"))
        self.resize(600, 500)
        self.setModal(True)

        # 設置窗口始終在最前面
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.init_ui()
        self.message_count = 0

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 標題
        title_label = QLabel(self.language_manager.get_text("real_time_monitoring", "Translation Progress Real-time Monitoring"))
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 進度消息顯示區域
        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.progress_text)

        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不確定進度
        layout.addWidget(self.progress_bar)

        # 統計信息
        self.stats_label = QLabel(self.language_manager.get_text("messages_received", "Messages Received: 0").format(count=0))
        layout.addWidget(self.stats_label)

        # 按鈕區域
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton(self.language_manager.get_text("cancel_translation", "Cancel Translation"))
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def add_progress_message(self, message: str):
        """添加進度消息"""
        self.message_count += 1

        # 獲取當前文本
        current_text = self.progress_text.toPlainText()

        # 添加新消息
        if current_text:
            new_text = current_text + "\n" + message
        else:
            new_text = message

        self.progress_text.setPlainText(new_text)

        # 自動滾動到最底部
        cursor = self.progress_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.progress_text.setTextCursor(cursor)

        # 更新統計
        self.stats_label.setText(self.language_manager.get_text("messages_received", "Messages Received: {count}").format(count=self.message_count))

    def on_cancel_clicked(self):
        """取消按鈕被點擊"""
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(self.language_manager.get_text("cancelling_translation", "Cancelling..."))
        self.reject()

    def closeEvent(self, event):
        """窗口關閉事件"""
        event.accept()

class AITranslationEditorDialog(QDialog):
    """AI翻譯編輯器對話框 v2.0 - 可編輯設定版本"""
    
    def __init__(
        self,
        source_file: Optional[str],
        target_file: Optional[str],
        ai_config: Dict,
        parent=None,
        mode: str = "translation",
        settings_paths: Optional[Dict] = None
    ):
        super().__init__(parent)
        self.mode = mode if mode in {"translation", "settings"} else "translation"
        self.source_file = source_file
        self.target_file = target_file
        self.ai_config = ai_config.copy()  # 使用傳入的設定，不修改原始設定
        self.settings_paths = dict(settings_paths) if settings_paths else {}
        if self.settings_paths:
            self.ai_config["paths"] = self.settings_paths
        # 強制設定AI翻譯為啟用狀態，因為此流程預設執行AI翻譯
        self.ai_config["enabled"] = True
        self.original_lines = []
        self.translated_lines = []
        self.ai_translator = None
        self.prompt_manager = PromptManager(settings_paths=self.ai_config.get("paths", {}))
        
        # 初始化語言管理器
        from modules.language_manager import LanguageManager
        self.language_manager = LanguageManager()
        
        # 從父視窗獲取語言管理器（如果存在），否則使用預設
        if parent and hasattr(parent, 'language_manager'):
            self.language_manager = parent.language_manager

        # 臨時prompt設定（僅用於本次翻譯）
        self.temp_prompts = {
            "system_prompt": ai_config.get("prompts", {}).get("system_prompt", ""),
            "user_prompt_template": ai_config.get("prompts", {}).get("user_prompt_template", ""),
            "translation_style": ai_config.get("prompts", {}).get("translation_style", "自然對話風格"),
            "video_type": ai_config.get("prompts", {}).get("video_type", "一般影片"),
            "character_info": ai_config.get("prompts", {}).get("character_info", "無特殊設定")
        }

        self.setWindowTitle(self.language_manager.get_text("ai_translation_editor_title", "AI翻譯編輯器 v2.0"))
        self.resize(600, 800)
        self.setModal(True)

        self.init_ui()
        self.load_source_content()
        self.configure_mode_ui()

        # 初始化AI翻譯器（此流程預設啟用）
        try:
            self.ai_translator = AITranslator(self.ai_config)
        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("ai_translator_init_error", "AI translator initialization failed: {error}").format(error=str(e)))

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 建立分頁
        self.tab_widget = QTabWidget()
        
        # 翻譯分頁
        translation_tab = QWidget()
        self.setup_translation_tab(translation_tab)
        self.tab_widget.addTab(translation_tab, self.language_manager.get_text("ai_translation_editor_translation_tab", "翻譯編輯"))
        
        # 設定資訊分頁（可編輯）
        settings_info_tab = QWidget()
        self.setup_settings_info_tab(settings_info_tab)
        self.tab_widget.addTab(settings_info_tab, self.language_manager.get_text("ai_translation_editor_settings_tab", "設定資訊"))
        
        # Prompt設定分頁（臨時調整）
        prompt_tab = QWidget()
        self.setup_prompt_tab(prompt_tab)
        self.tab_widget.addTab(prompt_tab, self.language_manager.get_text("ai_translation_editor_prompt_tab", "Prompt調整"))
        
        layout.addWidget(self.tab_widget)
        
        # 底部按鈕
        button_layout = QHBoxLayout()
        
        self.test_api_btn = QPushButton(self.language_manager.get_text("ai_translation_editor_test_api", "測試API連線"))
        self.test_api_btn.clicked.connect(self.test_api_connection)
        
        self.auto_translate_btn = QPushButton(self.language_manager.get_text("ai_translation_editor_auto_translate", "AI自動翻譯"))
        self.auto_translate_btn.clicked.connect(self.start_auto_translation)

        self.save_btn = QPushButton(self.language_manager.get_text("ai_translation_editor_save", "儲存翻譯"))
        self.save_btn.clicked.connect(self.handle_save_action)
        
        self.cancel_btn = QPushButton(self.language_manager.get_text("cancel_button", "取消"))
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.test_api_btn)
        button_layout.addWidget(self.auto_translate_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 狀態標籤
        self.status_label = QLabel(self.language_manager.get_text("status_ready", "Ready"))
        layout.addWidget(self.status_label)

    def setup_translation_tab(self, tab):
        layout = QVBoxLayout(tab)

        # 檔案資訊
        info_layout = QHBoxLayout()
        source_text = f"{self.language_manager.get_text('ai_translation_editor_source_file', '來源檔案:')} {Path(self.source_file).name}" if self.source_file else f"{self.language_manager.get_text('ai_translation_editor_source_file', '來源檔案:')} {self.language_manager.get_text('ai_translation_editor_not_specified', '尚未指定')}"
        target_text = f"{self.language_manager.get_text('ai_translation_editor_target_file', '目標檔案:')} {Path(self.target_file).name}" if self.target_file else f"{self.language_manager.get_text('ai_translation_editor_target_file', '目標檔案:')} {self.language_manager.get_text('ai_translation_editor_not_specified', '尚未指定')}"
        self.source_info_label = QLabel(source_text)
        self.target_info_label = QLabel(target_text)
        info_layout.addWidget(self.source_info_label)
        info_layout.addWidget(self.target_info_label)
        layout.addLayout(info_layout)

        # 分割視窗
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 原文區域
        original_group = QGroupBox(self.language_manager.get_text('ai_translation_editor_original_text', '原文'))
        original_layout = QVBoxLayout(original_group)
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        font = QFont("Consolas", 10)
        self.original_text.setFont(font)
        original_layout.addWidget(self.original_text)
        splitter.addWidget(original_group)

        # 翻譯區域
        translation_group = QGroupBox(self.language_manager.get_text('ai_translation_editor_translation_result', '翻譯結果'))
        translation_layout = QVBoxLayout(translation_group)

        # 翻譯控制按鈕
        trans_control_layout = QHBoxLayout()
        self.clear_translation_btn = QPushButton(self.language_manager.get_text('ai_translation_editor_clear_translation', '清空翻譯'))
        self.clear_translation_btn.clicked.connect(self.clear_translation)
        self.reload_btn = QPushButton(self.language_manager.get_text('ai_translation_editor_reload', '重新載入'))
        self.reload_btn.clicked.connect(self.load_source_content)
        trans_control_layout.addWidget(self.clear_translation_btn)
        trans_control_layout.addWidget(self.reload_btn)
        trans_control_layout.addStretch()
        translation_layout.addLayout(trans_control_layout)

        self.translation_text = QTextEdit()
        self.translation_text.setFont(font)
        translation_layout.addWidget(self.translation_text)
        splitter.addWidget(translation_group)

        layout.addWidget(splitter)

        # 翻譯統計
        stats_layout = QHBoxLayout()
        self.line_count_label = QLabel(self.language_manager.get_text("line_count", "Lines: {count}").format(count=0))
        self.char_count_label = QLabel(self.language_manager.get_text("char_count", "Characters: {count}").format(count=0))
        stats_layout.addWidget(self.line_count_label)
        stats_layout.addWidget(self.char_count_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

    def configure_mode_ui(self):
        """依照模式切換 UI 狀態"""
        source_exists = bool(self.source_file and Path(self.source_file).exists())
        target_exists = bool(self.target_file)
        translation_enabled = self.mode == "translation" and source_exists and target_exists

        if self.source_info_label:
            if self.source_file:
                suffix = "" if source_exists else " (未找到檔案)"
                self.source_info_label.setText(f"來源檔案: {Path(self.source_file).name}{suffix}")
            else:
                self.source_info_label.setText("來源檔案: 尚未指定")

        if self.target_info_label:
            if self.target_file:
                self.target_info_label.setText(f"目標檔案: {Path(self.target_file).name}")
            else:
                self.target_info_label.setText("目標檔案: 尚未指定")

        for widget in [self.clear_translation_btn, self.reload_btn, self.auto_translate_btn]:
            widget.setEnabled(translation_enabled)

        self.translation_text.setReadOnly(not translation_enabled)
        if hasattr(self.translation_text, "setPlaceholderText"):
            placeholder = "" if translation_enabled else self.language_manager.get_text("settings_mode_placeholder", "Settings mode: No subtitle content loaded currently.")
            self.translation_text.setPlaceholderText(placeholder)

        if translation_enabled:
            self.save_btn.setText("儲存翻譯")
            if self.status_label.text().startswith(self.language_manager.get_text("settings_mode", "Settings mode")):
                self.status_label.setText(self.language_manager.get_text("status_ready", "Ready"))
        else:
            self.save_btn.setText("完成")
            self.status_label.setText(self.language_manager.get_text("settings_mode_title", "Settings mode: Can directly adjust AI settings and Prompt"))

    def setup_settings_info_tab(self, tab):
        """設定資訊分頁 - 多組AI設定管理"""
        layout = QVBoxLayout(tab)

        # 說明標籤
        info_label = QLabel(self.language_manager.get_text("ai_settings_management_info", "Manage multiple AI translation settings. Each setting group contains API information and model information, which can be freely combined."))
        info_label.setStyleSheet("color: #666; font-style: italic; margin: 10px;")
        layout.addWidget(info_label)

        # 設定選擇區域
        settings_selection_layout = QHBoxLayout()

        # API設定選擇
        api_group = QGroupBox(self.language_manager.get_text("ai_settings_group_title", "API Settings"))
        api_layout = QVBoxLayout(api_group)

        api_select_layout = QHBoxLayout()
        api_select_layout.addWidget(QLabel(self.language_manager.get_text("select_api_setting", "Select API Setting:")))
        self.api_settings_combo = QComboBox()
        self.api_settings_combo.currentTextChanged.connect(self.on_api_setting_changed)
        api_select_layout.addWidget(self.api_settings_combo)

        self.new_api_btn = QPushButton(self.language_manager.get_text("new_api_setting", "New API"))
        self.new_api_btn.clicked.connect(self.new_api_setting)
        api_select_layout.addWidget(self.new_api_btn)

        self.delete_api_btn = QPushButton(self.language_manager.get_text("delete_api_setting", "Delete"))
        self.delete_api_btn.clicked.connect(self.delete_api_setting)
        api_select_layout.addWidget(self.delete_api_btn)

        api_layout.addLayout(api_select_layout)

        # API設定欄位
        self.api_provider_edit = QLineEdit()
        self.api_provider_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel(self.language_manager.get_text("api_provider_field", "API Provider:")))
        api_layout.addWidget(self.api_provider_edit)

        self.api_url_edit = QLineEdit()
        self.api_url_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel(self.language_manager.get_text("api_url_field", "API URL:")))
        api_layout.addWidget(self.api_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel(self.language_manager.get_text("api_key_field", "API Key:")))
        api_layout.addWidget(self.api_key_edit)

        settings_selection_layout.addWidget(api_group)

        # 模型設定選擇
        model_group = QGroupBox(self.language_manager.get_text("model_settings_group_title", "Model Settings"))
        model_layout = QVBoxLayout(model_group)

        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel(self.language_manager.get_text("select_model_setting", "Select Model Setting:")))
        self.model_settings_combo = QComboBox()
        self.model_settings_combo.currentTextChanged.connect(self.on_model_setting_changed)
        model_select_layout.addWidget(self.model_settings_combo)

        self.new_model_btn = QPushButton(self.language_manager.get_text("new_model_setting", "New Model"))
        self.new_model_btn.clicked.connect(self.new_model_setting)
        model_select_layout.addWidget(self.new_model_btn)

        self.delete_model_btn = QPushButton(self.language_manager.get_text("delete_model_setting", "Delete"))
        self.delete_model_btn.clicked.connect(self.delete_model_setting)
        model_select_layout.addWidget(self.delete_model_btn)

        model_layout.addLayout(model_select_layout)

        # 模型設定欄位
        self.model_edit = QLineEdit()
        self.model_edit.setFixedWidth(int(self.width() * 0.8))
        model_layout.addWidget(QLabel(self.language_manager.get_text("model_field", "Model:")))
        model_layout.addWidget(self.model_edit)

        settings_selection_layout.addWidget(model_group)

        layout.addLayout(settings_selection_layout)

        # 翻譯參數設定
        params_group = QGroupBox(self.language_manager.get_text("translation_params_group_title", "Translation Parameters"))
        params_layout = QFormLayout(params_group)

        # 語言設定
        self.source_language_edit = QLineEdit(self.ai_config.get("source_language", ""))
        self.source_language_edit.setFixedWidth(int(self.width() * 0.8))
        params_layout.addRow(self.language_manager.get_text("source_language_field", "Source Language:"), self.source_language_edit)

        self.target_language_edit = QLineEdit(self.ai_config.get("target_language", ""))
        self.target_language_edit.setFixedWidth(int(self.width() * 0.8))
        params_layout.addRow(self.language_manager.get_text("target_language_field", "Target Language:"), self.target_language_edit)

        # 翻譯參數
        self.batch_size_spinbox = QSpinBox()
        self.batch_size_spinbox.setRange(1, 100)
        self.batch_size_spinbox.setValue(self.ai_config.get("batch_size", 10))
        params_layout.addRow(self.language_manager.get_text("batch_size_field", "Batch Size:"), self.batch_size_spinbox)

        self.max_concurrent_requests_spinbox = QSpinBox()
        self.max_concurrent_requests_spinbox.setRange(1, 10)
        self.max_concurrent_requests_spinbox.setValue(self.ai_config.get("max_concurrent_requests", 3))
        params_layout.addRow(self.language_manager.get_text("max_concurrent_requests_field", "Max Concurrent Requests:"), self.max_concurrent_requests_spinbox)

        self.enable_validation_checkbox = QCheckBox(self.language_manager.get_text("enable_validation_field", "Enable Translation Validation"))
        self.enable_validation_checkbox.setChecked(self.ai_config.get("enable_validation", False))
        params_layout.addRow(self.language_manager.get_text("translation_validation", "Translation Validation:"), self.enable_validation_checkbox)

        self.max_retries_spinbox = QSpinBox()
        self.max_retries_spinbox.setRange(0, 5)
        self.max_retries_spinbox.setValue(self.ai_config.get("max_retries", 3))
        params_layout.addRow(self.language_manager.get_text("max_retries_field", "Max Retries:"), self.max_retries_spinbox)

        self.retry_delay_spinbox = QSpinBox()
        self.retry_delay_spinbox.setRange(1, 10)
        self.retry_delay_spinbox.setValue(self.ai_config.get("retry_delay", 2))
        params_layout.addRow(self.language_manager.get_text("retry_delay_field", "Retry Delay (seconds):"), self.retry_delay_spinbox)

        layout.addWidget(params_group)

        # 控制按鈕
        button_layout = QHBoxLayout()
        save_settings_btn = QPushButton(self.language_manager.get_text("save_settings", "Save Settings"))
        save_settings_btn.clicked.connect(self.save_ai_settings)

        reset_settings_btn = QPushButton(self.language_manager.get_text("reset_settings", "Reset"))
        reset_settings_btn.clicked.connect(self.reset_ai_settings)

        button_layout.addWidget(save_settings_btn)
        button_layout.addWidget(reset_settings_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 初始化設定
        self.load_ai_settings()

    def setup_prompt_tab(self, tab):
        """Prompt設定分頁 - 自定義模板管理"""
        layout = QVBoxLayout(tab)

        # 說明標籤
        info_label = QLabel(self.language_manager.get_text("prompt_template_management_info", "Custom Prompt template management. Select a template to edit, or add/delete templates."))
        info_label.setStyleSheet("color: #666; font-style: italic; margin: 10px;")
        layout.addWidget(info_label)

        # 模板管理控制
        template_control_layout = QHBoxLayout()
        template_control_layout.addWidget(QLabel(self.language_manager.get_text("select_template", "Template Selection:")))

        self.template_combo = QComboBox()
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        template_control_layout.addWidget(self.template_combo)

        self.new_template_btn = QPushButton(self.language_manager.get_text("new_template", "New"))
        self.new_template_btn.clicked.connect(self.new_template)
        template_control_layout.addWidget(self.new_template_btn)

        self.delete_template_btn = QPushButton(self.language_manager.get_text("delete_template", "Delete"))
        self.delete_template_btn.clicked.connect(self.delete_template)
        template_control_layout.addWidget(self.delete_template_btn)

        self.save_template_btn = QPushButton(self.language_manager.get_text("save_template", "Save"))
        self.save_template_btn.clicked.connect(self.save_template)
        template_control_layout.addWidget(self.save_template_btn)

        template_control_layout.addStretch()
        layout.addLayout(template_control_layout)

        # 主編輯區域 - 垂直分割
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # System Prompt區域 (2/5)
        system_group = QGroupBox(self.language_manager.get_text("system_prompt_group", "System Prompt"))
        system_layout = QVBoxLayout(system_group)
        self.system_prompt_editor = QTextEdit()
        self.system_prompt_editor.setFont(QFont("Consolas", 10))
        system_layout.addWidget(self.system_prompt_editor)
        main_splitter.addWidget(system_group)

        # User Prompt區域 (2/5)
        user_group = QGroupBox(self.language_manager.get_text("user_prompt_group", "User Prompt"))
        user_layout = QVBoxLayout(user_group)
        self.user_prompt_editor = QTextEdit()
        self.user_prompt_editor.setFont(QFont("Consolas", 10))
        user_layout.addWidget(self.user_prompt_editor)
        main_splitter.addWidget(user_group)

        # 變數參考區域 (1/5)
        variables_group = QGroupBox(self.language_manager.get_text("variables_reference", "Variables Reference"))
        variables_layout = QVBoxLayout(variables_group)

        variables_text = QTextEdit()
        variables_text.setReadOnly(True)
        variables_text.setFont(QFont("Consolas", 9))

        variables_info = self.prompt_manager.get_available_variables()
        variables_content = "\n".join([f"{{{key}}}: {desc}" for key, desc in variables_info.items()])
        variables_text.setPlainText(variables_content)

        variables_layout.addWidget(variables_text)
        main_splitter.addWidget(variables_group)

        # 設置分割器比例 (2:2:1)
        main_splitter.setSizes([200, 200, 100])
        layout.addWidget(main_splitter)

        # Prompt控制按鈕
        prompt_control_layout = QHBoxLayout()

        self.apply_prompt_btn = QPushButton(self.language_manager.get_text("apply_adjustment", "Apply Adjustment"))
        self.apply_prompt_btn.clicked.connect(self.apply_prompt_changes)

        self.reset_prompt_btn = QPushButton(self.language_manager.get_text("reset_prompt", "Reset"))
        self.reset_prompt_btn.clicked.connect(self.reset_prompts)

        prompt_control_layout.addWidget(self.apply_prompt_btn)
        prompt_control_layout.addWidget(self.reset_prompt_btn)
        prompt_control_layout.addStretch()

        layout.addLayout(prompt_control_layout)

        # 初始化
        self.load_ai_prompt_templates()
        self.on_template_changed()
    
    def save_settings(self):
        """儲存設定"""
        try:
            # 更新AI配置
            self.ai_config.update({
                "enabled": self.enabled_checkbox.isChecked(),
                "api_provider": self.api_provider_edit.text().strip(),
                "api_url": self.api_url_edit.text().strip(),
                "model": self.model_edit.text().strip(),
                "source_language": self.source_language_edit.text().strip(),
                "target_language": self.target_language_edit.text().strip(),
                "batch_size": self.batch_size_spinbox.value(),
                "max_concurrent_requests": self.max_concurrent_requests_spinbox.value(),
                "enable_validation": self.enable_validation_checkbox.isChecked(),
                "max_retries": self.max_retries_spinbox.value(),
                "retry_delay": self.retry_delay_spinbox.value(),
            })
            
            # 更新API金鑰（如果不是遮蔽的）
            api_key_text = self.api_key_edit.text().strip()
            if not api_key_text.startswith('*'):
                self.ai_config["api_key"] = api_key_text
            
            # 更新Prompt設定
            self.ai_config["prompts"] = {
                "translation_style": self.translation_style_edit.text().strip(),
                "video_type": self.video_type_edit.text().strip(),
                "character_info": self.character_info_edit.text().strip()
            }
            
            # 重新初始化翻譯器
            if self.ai_config.get("enabled", False):
                self.ai_translator = AITranslator(self.ai_config)
            
            QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("settings_saved_success", "AI settings saved"))
            
        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))
    
    def reset_settings(self):
        """重置設定為預設值"""
        try:
            # 重置為初始配置
            self.enabled_checkbox.setChecked(False)
            self.api_provider_edit.clear()
            self.api_url_edit.clear()
            self.api_key_edit.clear()
            self.model_edit.clear()
            self.source_language_edit.clear()
            self.target_language_edit.clear()
            self.batch_size_spinbox.setValue(10)
            self.max_concurrent_requests_spinbox.setValue(3)
            self.enable_validation_checkbox.setChecked(False)
            self.max_retries_spinbox.setValue(3)
            self.retry_delay_spinbox.setValue(2)
            
            # 重置Prompt設定
            self.translation_style_edit.clear()
            self.video_type_edit.clear()
            self.character_info_edit.clear()
            
            QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("settings_reset_success", "AI settings reset"))
            
        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("reset_ai_settings_error", "Failed to reset AI settings: {error}").format(error=str(e)))

    def load_source_content(self):
        """載入來源檔案內容"""
        if not self.source_file or not Path(self.source_file).exists():
            placeholder = self.language_manager.get_text("settings_mode_placeholder", "Settings mode: No subtitle content loaded currently.") if self.mode == "settings" else self.language_manager.get_text("source_file_not_found", "Source file not found, please confirm 2C process input.")
            self.original_text.setPlainText(placeholder)
            self.original_lines = []
            self.line_count_label.setText("行數: 0")
            self.char_count_label.setText("字元數: 0")
            if self.mode == "settings":
                self.status_label.setText(self.language_manager.get_text("settings_mode_title", "Settings mode: Can directly adjust AI settings and Prompt"))
            else:
                self.status_label.setText(self.language_manager.get_text("source_file_not_found", "Source file not found, please confirm 2C process input."))
            self.configure_mode_ui()
            return

        try:
            with open(self.source_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.original_text.setPlainText(content)
            self.original_lines = content.strip().split("\n")

            # 更新統計
            self.line_count_label.setText(f"行數: {len(self.original_lines)}")
            self.char_count_label.setText(f"字元數: {len(content)}")

            self.status_label.setText(self.language_manager.get_text("load_source_error", "Failed to load source file: {error}").format(error=""))

        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("load_source_error", "Failed to load source file: {error}").format(error=str(e)))
        finally:
            self.configure_mode_ui()

    def apply_prompt_changes(self):
        """套用Prompt調整到臨時設定"""
        try:
            # 從編輯器獲取當前的prompt內容
            system_prompt = self.system_prompt_editor.toPlainText()
            user_prompt = self.user_prompt_editor.toPlainText()

            # 更新臨時prompt設定
            self.temp_prompts["system_prompt"] = system_prompt
            self.temp_prompts["user_prompt_template"] = user_prompt

            # 更新AI配置中的prompts
            self.ai_config["prompts"] = self.temp_prompts.copy()

            # 重新初始化翻譯器
            if self.ai_config.get("enabled", False):
                self.ai_translator = AITranslator(self.ai_config)
                self.status_label.setText(self.language_manager.get_text("prompt_applied", "Prompt adjustment applied"))
            else:
                self.status_label.setText(self.language_manager.get_text("ai_translation_disabled", "AI translation not enabled"))

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("apply_prompt_error", "Failed to apply prompt adjustment: {error}").format(error=str(e)))

    def reset_prompts(self):
        """重置Prompt為原始設定"""
        try:
            # 重新載入settings.json的原始設定
            settings_file_path = resolve_settings_file()
            with open(settings_file_path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)

            original_prompts = settings_data.get("ai_translation", {}).get("prompts", {})

            # 重置臨時prompt設定
            self.temp_prompts = {
                "system_prompt": original_prompts.get("system_prompt", ""),
                "user_prompt_template": original_prompts.get("user_prompt_template", ""),
                "translation_style": original_prompts.get("translation_style", "自然對話風格"),
                "video_type": original_prompts.get("video_type", "一般影片"),
                "character_info": original_prompts.get("character_info", "無特殊設定")
            }

            # 更新編輯器內容為原始設定
            self.system_prompt_editor.setPlainText(self.temp_prompts["system_prompt"])
            self.user_prompt_editor.setPlainText(self.temp_prompts["user_prompt_template"])

            # 重新載入並選擇default模板
            self.load_ai_prompt_templates()
            index = self.template_combo.findText("default")
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
                self.on_template_changed()

            self.status_label.setText(self.language_manager.get_text("prompt_reset", "Prompt reset to original settings"))

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("reset_prompt_error", "Failed to reset prompt: {error}").format(error=str(e)))

    def test_api_connection(self):
        """測試API連線"""
        if not self.ai_translator:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("ai_translation_disabled", "AI translation not enabled"))
            return

        self.status_label.setText(self.language_manager.get_text("api_connection_test_disabled", "Testing API connection..."))
        self.test_api_btn.setEnabled(False)

        try:
            success, message = self.ai_translator.validate_api_connection()
            if success:
                QMessageBox.information(self, self.language_manager.get_text("success_title", "成功"), message)
                self.status_label.setText(self.language_manager.get_text("api_connection_test_success", "API connection test successful: {message}").format(message=""))
            else:
                QMessageBox.warning(self, self.language_manager.get_text("failure_title", "失敗"), message)
                self.status_label.setText(self.language_manager.get_text("api_connection_test_failure", "API connection test failed: {message}").format(message=""))
        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "錯誤"), self.language_manager.get_text("api_connection_test_error_detail", "API連線測試錯誤: {error}").format(error=str(e)))
            self.status_label.setText(self.language_manager.get_text("api_connection_test_error", "API connection test error: {error}").format(error=""))
        finally:
            self.test_api_btn.setEnabled(True)

    def start_auto_translation(self):
        """開始自動翻譯"""
        if self.mode != "translation":
            QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("settings_mode", "Settings mode: Can directly adjust AI settings and Prompt"))
            return

        if not self.ai_config.get("enabled", False):
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("ai_translation_disabled", "AI translation not enabled"))
            return

        if not self.original_lines:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("no_content_to_translate", "No content to translate"))
            return

        # 準備上下文資訊
        context_info = {
            "video_type": self.temp_prompts.get("video_type", "一般影片"),
            "character_info": self.temp_prompts.get("character_info", "無特殊設定")
        }

        # 開始翻譯
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不確定進度
        self.auto_translate_btn.setEnabled(False)
        self.status_label.setText(self.language_manager.get_text("translation_in_progress", "AI translation in progress..."))

        # 建立獨立的進度窗口
        self.progress_window = TranslationProgressWindow(self)
        self.progress_window.show()

        # 建立並啟動翻譯工作執行緒
        self.translation_worker = AITranslationWorker(
            self.ai_config, self.original_lines, context_info
        )
        self.translation_worker.progress_updated.connect(self.on_translation_progress)
        self.translation_worker.progress_updated.connect(self.progress_window.add_progress_message)
        self.translation_worker.translation_completed.connect(self.on_translation_completed)
        self.translation_worker.error_occurred.connect(self.on_translation_error)
        self.translation_worker.start()

    def on_translation_progress(self, message: str):
        """翻譯進度更新"""
        self.status_label.setText(message)

    def on_translation_completed(self, translated_lines: List[str]):
        """翻譯完成"""
        self.translated_lines = translated_lines
        self.translation_text.setPlainText("\n".join(translated_lines))

        self.progress_bar.setVisible(False)
        self.auto_translate_btn.setEnabled(True)
        self.status_label.setText(self.language_manager.get_text("translation_completed", "AI translation completed, please check the results"))

        # 關閉進度窗口
        if hasattr(self, 'progress_window') and self.progress_window:
            self.progress_window.close()

        QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("translation_completed", "AI translation completed, please check the results"))

    def on_translation_error(self, error_message: str):
        """翻譯錯誤"""
        self.progress_bar.setVisible(False)
        self.auto_translate_btn.setEnabled(True)
        self.status_label.setText(self.language_manager.get_text("translation_error", "Translation error: {error}").format(error=""))

        # 關閉進度窗口
        if hasattr(self, 'progress_window') and self.progress_window:
            self.progress_window.close()

        QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), error_message)

    def clear_translation(self):
        """清空翻譯"""
        self.translation_text.clear()
        self.translated_lines = []
        if self.mode == "translation":
            self.status_label.setText(self.language_manager.get_text("clear_translation_done", "Translation cleared"))
        else:
            self.status_label.setText(self.language_manager.get_text("settings_mode_clear", "Settings mode: Translation area content cleared"))

    def handle_save_action(self):
        if self.mode == "translation":
            self.save_translation()
        else:
            self.accept()

    def save_translation(self):
        """儲存翻譯結果"""
        if self.mode != "translation":
            self.accept()
            return

        if not self.target_file:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("no_translation_to_save", "No translation content to save"))
            return

        try:
            # 取得翻譯內容
            translation_content = self.translation_text.toPlainText()

            if not translation_content.strip():
                QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("no_translation_to_save", "No translation content to save"))
                return

            # 確保目標目錄存在
            target_path = Path(self.target_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 儲存翻譯結果
            with open(self.target_file, "w", encoding="utf-8") as f:
                f.write(translation_content)

            self.status_label.setText(self.language_manager.get_text("translation_saved_to", "Translation saved to: {path}").format(path=""))
            QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("translation_saved_to", "Translation saved to: {path}").format(path=self.target_file))
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_translation_error", "Failed to save translation: {error}").format(error=str(e)))

    def update_template_list(self):
        """更新模板列表"""
        current_type = self.prompt_type_combo.currentText()
        self.template_combo.clear()

        if current_type == "System Prompt":
            templates = self.prompt_manager.get_template_list("system")
        else:
            templates = self.prompt_manager.get_template_list("user")

        self.template_combo.addItems(templates)

    def on_prompt_type_changed(self):
        """Prompt類型改變"""
        self.update_template_list()

        # 顯示當前的prompt內容
        current_type = self.prompt_type_combo.currentText()
        if current_type == "System Prompt":
            content = self.temp_prompts.get("system_prompt", "")
        else:
            content = self.temp_prompts.get("user_prompt_template", "")

        self.prompt_editor.setPlainText(content)

    def on_template_changed(self):
        """模板改變"""
        template_name = self.template_combo.currentText()

        if not template_name:
            return

        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            if template_name in ai_prompt_data:
                template_data = ai_prompt_data[template_name]
                system_prompt = template_data.get("prompt_templates", {}).get("system_prompt", "")
                user_prompt = template_data.get("prompt_templates", {}).get("user_prompt_template", "")

                self.system_prompt_editor.setPlainText(system_prompt)
                self.user_prompt_editor.setPlainText(user_prompt)
        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_prompt_error", "Failed to load Prompt templates: {error}").format(error=str(e)))

    def load_ai_settings(self):
        """載入AI設定"""
        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            # 載入API設定
            self.api_settings_combo.clear()
            for setting_name in ai_prompt_data.get("default", {}).get("api_settings", {}):
                self.api_settings_combo.addItem(setting_name)

            # 載入模型設定
            self.model_settings_combo.clear()
            for setting_name in ai_prompt_data.get("default", {}).get("model_settings", {}):
                self.model_settings_combo.addItem(setting_name)

            # 預設選擇第一個
            if self.api_settings_combo.count() > 0:
                self.api_settings_combo.setCurrentIndex(0)
                self.on_api_setting_changed()

            if self.model_settings_combo.count() > 0:
                self.model_settings_combo.setCurrentIndex(0)
                self.on_model_setting_changed()

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_settings_error", "Failed to load AI settings: {error}").format(error=str(e)))

    def _sync_config_from_ui(self):
        """從UI同步設定到ai_config"""
        try:
            current_api = self.api_settings_combo.currentText()
            current_model = self.model_settings_combo.currentText()

            # 同步API設定
            if current_api:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)
                api_data = ai_prompt_data.get("default", {}).get("api_settings", {}).get(current_api, {})
                self.ai_config.update({
                    "api_provider": api_data.get("provider", ""),
                    "api_url": api_data.get("url", ""),
                    "api_key": api_data.get("key", "")
                })

            # 同步模型設定
            if current_model:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)
                model_data = ai_prompt_data.get("default", {}).get("model_settings", {}).get(current_model, {})
                self.ai_config["model"] = model_data.get("model", "")

            # 同步翻譯參數
            self.ai_config.update({
                "source_language": self.source_language_edit.text().strip(),
                "target_language": self.target_language_edit.text().strip(),
                "batch_size": self.batch_size_spinbox.value(),
                "max_concurrent_requests": self.max_concurrent_requests_spinbox.value(),
                "enable_validation": self.enable_validation_checkbox.isChecked(),
                "max_retries": self.max_retries_spinbox.value(),
                "retry_delay": self.retry_delay_spinbox.value()
            })

            # 重新初始化翻譯器
            if self.ai_config.get("enabled", False):
                self.ai_translator = AITranslator(self.ai_config)

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_settings_error", "Failed to load AI settings: {error}").format(error=str(e)))

    def save_ai_settings(self):
        """儲存AI設定"""
        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            current_api = self.api_settings_combo.currentText()
            current_model = self.model_settings_combo.currentText()

            if current_api and current_api in ai_prompt_data.get("default", {}).get("api_settings", {}):
                ai_prompt_data["default"]["api_settings"][current_api].update({
                    "provider": self.api_provider_edit.text().strip(),
                    "url": self.api_url_edit.text().strip(),
                    "key": self.api_key_edit.text().strip()
                })

            if current_model and current_model in ai_prompt_data.get("default", {}).get("model_settings", {}):
                ai_prompt_data["default"]["model_settings"][current_model]["model"] = self.model_edit.text().strip()

            # 更新翻譯參數
            ai_prompt_data["default"]["translation_config"].update({
                "source_language": self.source_language_edit.text().strip(),
                "target_language": self.target_language_edit.text().strip(),
                "batch_size": self.batch_size_spinbox.value(),
                "max_concurrent_requests": self.max_concurrent_requests_spinbox.value(),
                "enable_validation": self.enable_validation_checkbox.isChecked(),
                "max_retries": self.max_retries_spinbox.value(),
                "retry_delay": self.retry_delay_spinbox.value()
            })

            with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

            QMessageBox.information(self, self.language_manager.get_text("success_title", "成功"), self.language_manager.get_text("ai_settings_saved", "AI設定已儲存"))

        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def reset_ai_settings(self):
        """重置AI設定"""
        try:
            # 重新載入設定
            self.load_ai_settings()
            QMessageBox.information(self, self.language_manager.get_text("success_title", "成功"), self.language_manager.get_text("ai_settings_reset", "AI設定已重置"))
        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("reset_ai_settings_error", "Failed to reset AI settings: {error}").format(error=str(e)))

    def on_api_setting_changed(self):
        """API設定改變"""
        current_api = self.api_settings_combo.currentText()

        if not current_api:
            return

        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            api_data = ai_prompt_data.get("default", {}).get("api_settings", {}).get(current_api, {})
            self.api_provider_edit.setText(api_data.get("provider", ""))
            self.api_url_edit.setText(api_data.get("url", ""))
            self.api_key_edit.setText(api_data.get("key", ""))

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_settings_error", "Failed to load AI settings: {error}").format(error=str(e)))

    def on_model_setting_changed(self):
        """模型設定改變"""
        current_model = self.model_settings_combo.currentText()

        if not current_model:
            return

        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            model_data = ai_prompt_data.get("default", {}).get("model_settings", {}).get(current_model, {})
            self.model_edit.setText(model_data.get("model", ""))

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_settings_error", "Failed to load AI settings: {error}").format(error=str(e)))

    def new_api_setting(self):
        """新增API設定"""
        name, ok = QInputDialog.getText(self, self.language_manager.get_text("new_api_setting_name", "Enter API setting name:"), self.language_manager.get_text("new_api_setting_name", "Enter API setting name:"))
        if ok and name.strip():
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if "default" not in ai_prompt_data:
                    ai_prompt_data["default"] = {"api_settings": {}, "model_settings": {}, "prompt_templates": {}, "translation_config": {}}

                if "api_settings" not in ai_prompt_data["default"]:
                    ai_prompt_data["default"]["api_settings"] = {}

                ai_prompt_data["default"]["api_settings"][name.strip()] = {
                    "provider": "",
                    "url": "",
                    "key": ""
                }

                with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_settings()
                # 選擇新建立的設定
                index = self.api_settings_combo.findText(name.strip())
                if index >= 0:
                    self.api_settings_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def delete_api_setting(self):
        """刪除API設定"""
        current_api = self.api_settings_combo.currentText()

        if not current_api:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("select_api_setting", "Select API Setting:"))
            return

        reply = QMessageBox.question(self, self.language_manager.get_text("confirm_delete_api", "Are you sure you want to delete API setting '{name}'?").format(name=current_api), self.language_manager.get_text("confirm_delete_api", "Are you sure you want to delete API setting '{name}'?").format(name=current_api),
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_api in ai_prompt_data.get("default", {}).get("api_settings", {}):
                    del ai_prompt_data["default"]["api_settings"][current_api]

                    with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_settings()

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def new_model_setting(self):
        """新增模型設定"""
        name, ok = QInputDialog.getText(self, self.language_manager.get_text("new_model_setting_name", "Enter model setting name:"), self.language_manager.get_text("new_model_setting_name", "Enter model setting name:"))
        if ok and name.strip():
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if "default" not in ai_prompt_data:
                    ai_prompt_data["default"] = {"api_settings": {}, "model_settings": {}, "prompt_templates": {}, "translation_config": {}}

                if "model_settings" not in ai_prompt_data["default"]:
                    ai_prompt_data["default"]["model_settings"] = {}

                ai_prompt_data["default"]["model_settings"][name.strip()] = {
                    "model": ""
                }

                with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_settings()
                # 選擇新建立的設定
                index = self.model_settings_combo.findText(name.strip())
                if index >= 0:
                    self.model_settings_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def delete_model_setting(self):
        """刪除模型設定"""
        current_model = self.model_settings_combo.currentText()

        if not current_model:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("select_model_setting", "Select Model Setting:"))
            return

        reply = QMessageBox.question(self, self.language_manager.get_text("confirm_delete_model", "Are you sure you want to delete model setting '{name}'?").format(name=current_model), self.language_manager.get_text("confirm_delete_model", "Are you sure you want to delete model setting '{name}'?").format(name=current_model),
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_model in ai_prompt_data.get("default", {}).get("model_settings", {}):
                    del ai_prompt_data["default"]["model_settings"][current_model]

                    with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_settings()

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def load_ai_prompt_templates(self):
        """載入AI Prompt模板"""
        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            self.template_combo.clear()

            # 始終添加default模板
            self.template_combo.addItem("default")

            # 添加自定義模板
            for template_name in ai_prompt_data:
                if template_name != "default":  # default是設定，不是模板
                    self.template_combo.addItem(template_name)

            # 預設選擇default模板
            index = self.template_combo.findText("default")
            if index >= 0:
                self.template_combo.setCurrentIndex(index)

        except Exception as e:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("load_api_prompt_error", "Failed to load Prompt templates: {error}").format(error=str(e)))

    def new_template(self):
        """新增模板"""
        name, ok = QInputDialog.getText(self, self.language_manager.get_text("new_template_name", "Enter template name:"), self.language_manager.get_text("new_template_name", "Enter template name:"))
        if ok and name.strip():
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                # 複製default設定作為新模板
                ai_prompt_data[name.strip()] = ai_prompt_data.get("default", {
                    "api_settings": {},
                    "model_settings": {},
                    "prompt_templates": {
                        "system_prompt": "",
                        "user_prompt_template": ""
                    },
                    "translation_config": {}
                }).copy()

                with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_prompt_templates()
                # 選擇新建立的模板
                index = self.template_combo.findText(name.strip())
                if index >= 0:
                    self.template_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def delete_template(self):
        """刪除模板"""
        current_template = self.template_combo.currentText()

        if not current_template or current_template == "default":
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("cannot_delete_default_template", "Cannot delete default template"))
            return

        reply = QMessageBox.question(self, self.language_manager.get_text("confirm_delete_template", "Are you sure you want to delete template '{name}'?").format(name=current_template), self.language_manager.get_text("confirm_delete_template", "Are you sure you want to delete template '{name}'?").format(name=current_template),
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_template in ai_prompt_data:
                    del ai_prompt_data[current_template]

                    with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_prompt_templates()

            except Exception as e:
                QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))

    def save_template(self):
        """儲存模板"""
        current_template = self.template_combo.currentText()

        if not current_template:
            QMessageBox.warning(self, self.language_manager.get_text("warning_title", "Warning"), self.language_manager.get_text("select_template", "Template Selection:"))
            return

        try:
            with open(get_ai_prompt_path(), "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            if current_template not in ai_prompt_data:
                ai_prompt_data[current_template] = {
                    "api_settings": {},
                    "model_settings": {},
                    "prompt_templates": {},
                    "translation_config": {}
                }

            ai_prompt_data[current_template]["prompt_templates"] = {
                "system_prompt": self.system_prompt_editor.toPlainText(),
                "user_prompt_template": self.user_prompt_editor.toPlainText()
            }

            with open(get_ai_prompt_path(), "w", encoding="utf-8") as f:
                json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

            QMessageBox.information(self, self.language_manager.get_text("confirm_button", "Confirm"), self.language_manager.get_text("template_saved", "Template '{name}' saved").format(name=current_template))

        except Exception as e:
            QMessageBox.critical(self, self.language_manager.get_text("error_title", "Error"), self.language_manager.get_text("save_ai_settings_error", "Failed to save AI settings: {error}").format(error=str(e)))
