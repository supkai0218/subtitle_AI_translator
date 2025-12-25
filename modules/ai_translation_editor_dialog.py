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

from .ai_translator_v1b import AITranslator
from .ai_validator_v1 import TranslationValidator
from .prompt_manager import PromptManager
import time

def get_settings_filepath():
    """獲取settings.json檔案路徑"""
    from pathlib import Path
    import os
    base_path = Path(os.getcwd())
    settings_dir = base_path / "../settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "settings.json"

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
        self.setWindowTitle("AI翻譯進度")
        self.resize(600, 500)
        self.setModal(True)

        # 設置窗口始終在最前面
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.init_ui()
        self.message_count = 0

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 標題
        title_label = QLabel("翻譯進度實時監控")
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
        self.stats_label = QLabel("已接收消息: 0")
        layout.addWidget(self.stats_label)

        # 按鈕區域
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("取消翻譯")
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
        self.stats_label.setText(f"已接收消息: {self.message_count}")

    def on_cancel_clicked(self):
        """取消按鈕被點擊"""
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("正在取消...")
        self.reject()

    def closeEvent(self, event):
        """窗口關閉事件"""
        event.accept()

class AITranslationEditorDialog(QDialog):
    """AI翻譯編輯器對話框 v2.0 - 可編輯設定版本"""
    
    def __init__(self, source_file: Optional[str], target_file: Optional[str], ai_config: Dict, parent=None, mode: str = "translation"):
        super().__init__(parent)
        self.mode = mode if mode in {"translation", "settings"} else "translation"
        self.source_file = source_file
        self.target_file = target_file
        self.ai_config = ai_config.copy()  # 使用傳入的設定，不修改原始設定
        # 強制設定AI翻譯為啟用狀態，因為此流程預設執行AI翻譯
        self.ai_config["enabled"] = True
        self.original_lines = []
        self.translated_lines = []
        self.ai_translator = None
        self.prompt_manager = PromptManager()

        # 臨時prompt設定（僅用於本次翻譯）
        self.temp_prompts = {
            "system_prompt": ai_config.get("prompts", {}).get("system_prompt", ""),
            "user_prompt_template": ai_config.get("prompts", {}).get("user_prompt_template", ""),
            "translation_style": ai_config.get("prompts", {}).get("translation_style", "自然對話風格"),
            "video_type": ai_config.get("prompts", {}).get("video_type", "一般影片"),
            "character_info": ai_config.get("prompts", {}).get("character_info", "無特殊設定")
        }

        self.setWindowTitle("AI翻譯編輯器 v2.0")
        self.resize(600, 800)
        self.setModal(True)

        self.init_ui()
        self.load_source_content()
        self.configure_mode_ui()

        # 初始化AI翻譯器（此流程預設啟用）
        try:
            self.ai_translator = AITranslator(self.ai_config)
        except Exception as e:
            QMessageBox.warning(self, "警告", f"AI翻譯器初始化失敗: {str(e)}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 建立分頁
        self.tab_widget = QTabWidget()
        
        # 翻譯分頁
        translation_tab = QWidget()
        self.setup_translation_tab(translation_tab)
        self.tab_widget.addTab(translation_tab, "翻譯編輯")
        
        # 設定資訊分頁（可編輯）
        settings_info_tab = QWidget()
        self.setup_settings_info_tab(settings_info_tab)
        self.tab_widget.addTab(settings_info_tab, "設定資訊")
        
        # Prompt設定分頁（臨時調整）
        prompt_tab = QWidget()
        self.setup_prompt_tab(prompt_tab)
        self.tab_widget.addTab(prompt_tab, "Prompt調整")
        
        layout.addWidget(self.tab_widget)
        
        # 底部按鈕
        button_layout = QHBoxLayout()
        
        self.test_api_btn = QPushButton("測試API連線")
        self.test_api_btn.clicked.connect(self.test_api_connection)
        
        self.auto_translate_btn = QPushButton("AI自動翻譯")
        self.auto_translate_btn.clicked.connect(self.start_auto_translation)

        self.save_btn = QPushButton("儲存翻譯")
        self.save_btn.clicked.connect(self.handle_save_action)
        
        self.cancel_btn = QPushButton("取消")
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
        self.status_label = QLabel("就緒")
        layout.addWidget(self.status_label)

    def setup_translation_tab(self, tab):
        layout = QVBoxLayout(tab)

        # 檔案資訊
        info_layout = QHBoxLayout()
        source_text = f"來源檔案: {Path(self.source_file).name}" if self.source_file else "來源檔案: 尚未指定"
        target_text = f"目標檔案: {Path(self.target_file).name}" if self.target_file else "目標檔案: 尚未指定"
        self.source_info_label = QLabel(source_text)
        self.target_info_label = QLabel(target_text)
        info_layout.addWidget(self.source_info_label)
        info_layout.addWidget(self.target_info_label)
        layout.addLayout(info_layout)

        # 分割視窗
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 原文區域
        original_group = QGroupBox("原文")
        original_layout = QVBoxLayout(original_group)
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        font = QFont("Consolas", 10)
        self.original_text.setFont(font)
        original_layout.addWidget(self.original_text)
        splitter.addWidget(original_group)

        # 翻譯區域
        translation_group = QGroupBox("翻譯結果")
        translation_layout = QVBoxLayout(translation_group)

        # 翻譯控制按鈕
        trans_control_layout = QHBoxLayout()
        self.clear_translation_btn = QPushButton("清空翻譯")
        self.clear_translation_btn.clicked.connect(self.clear_translation)
        self.reload_btn = QPushButton("重新載入")
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
        self.line_count_label = QLabel("行數: 0")
        self.char_count_label = QLabel("字元數: 0")
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
            placeholder = "" if translation_enabled else "設定模式：需在流程中載入字幕後才能進行翻譯。"
            self.translation_text.setPlaceholderText(placeholder)

        if translation_enabled:
            self.save_btn.setText("儲存翻譯")
            if self.status_label.text().startswith("設定模式"):
                self.status_label.setText("就緒")
        else:
            self.save_btn.setText("完成")
            self.status_label.setText("設定模式：可直接調整 AI 設定與 Prompt")

    def setup_settings_info_tab(self, tab):
        """設定資訊分頁 - 多組AI設定管理"""
        layout = QVBoxLayout(tab)

        # 說明標籤
        info_label = QLabel("管理多組AI翻譯設定。每組設定包含API資訊和模型資訊，可自由組合使用。")
        info_label.setStyleSheet("color: #666; font-style: italic; margin: 10px;")
        layout.addWidget(info_label)

        # 設定選擇區域
        settings_selection_layout = QHBoxLayout()

        # API設定選擇
        api_group = QGroupBox("API設定")
        api_layout = QVBoxLayout(api_group)

        api_select_layout = QHBoxLayout()
        api_select_layout.addWidget(QLabel("選擇API設定:"))
        self.api_settings_combo = QComboBox()
        self.api_settings_combo.currentTextChanged.connect(self.on_api_setting_changed)
        api_select_layout.addWidget(self.api_settings_combo)

        self.new_api_btn = QPushButton("新增API")
        self.new_api_btn.clicked.connect(self.new_api_setting)
        api_select_layout.addWidget(self.new_api_btn)

        self.delete_api_btn = QPushButton("刪除")
        self.delete_api_btn.clicked.connect(self.delete_api_setting)
        api_select_layout.addWidget(self.delete_api_btn)

        api_layout.addLayout(api_select_layout)

        # API設定欄位
        self.api_provider_edit = QLineEdit()
        self.api_provider_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel("API供應商:"))
        api_layout.addWidget(self.api_provider_edit)

        self.api_url_edit = QLineEdit()
        self.api_url_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel("API網址:"))
        api_layout.addWidget(self.api_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setFixedWidth(int(self.width() * 0.8))
        api_layout.addWidget(QLabel("API金鑰:"))
        api_layout.addWidget(self.api_key_edit)

        settings_selection_layout.addWidget(api_group)

        # 模型設定選擇
        model_group = QGroupBox("模型設定")
        model_layout = QVBoxLayout(model_group)

        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel("選擇模型設定:"))
        self.model_settings_combo = QComboBox()
        self.model_settings_combo.currentTextChanged.connect(self.on_model_setting_changed)
        model_select_layout.addWidget(self.model_settings_combo)

        self.new_model_btn = QPushButton("新增模型")
        self.new_model_btn.clicked.connect(self.new_model_setting)
        model_select_layout.addWidget(self.new_model_btn)

        self.delete_model_btn = QPushButton("刪除")
        self.delete_model_btn.clicked.connect(self.delete_model_setting)
        model_select_layout.addWidget(self.delete_model_btn)

        model_layout.addLayout(model_select_layout)

        # 模型設定欄位
        self.model_edit = QLineEdit()
        self.model_edit.setFixedWidth(int(self.width() * 0.8))
        model_layout.addWidget(QLabel("模型:"))
        model_layout.addWidget(self.model_edit)

        settings_selection_layout.addWidget(model_group)

        layout.addLayout(settings_selection_layout)

        # 翻譯參數設定
        params_group = QGroupBox("翻譯參數")
        params_layout = QFormLayout(params_group)

        # 語言設定
        self.source_language_edit = QLineEdit(self.ai_config.get("source_language", ""))
        self.source_language_edit.setFixedWidth(int(self.width() * 0.8))
        params_layout.addRow("來源語言:", self.source_language_edit)

        self.target_language_edit = QLineEdit(self.ai_config.get("target_language", ""))
        self.target_language_edit.setFixedWidth(int(self.width() * 0.8))
        params_layout.addRow("目標語言:", self.target_language_edit)

        # 翻譯參數
        self.batch_size_spinbox = QSpinBox()
        self.batch_size_spinbox.setRange(1, 100)
        self.batch_size_spinbox.setValue(self.ai_config.get("batch_size", 10))
        params_layout.addRow("批次大小:", self.batch_size_spinbox)

        self.max_concurrent_requests_spinbox = QSpinBox()
        self.max_concurrent_requests_spinbox.setRange(1, 10)
        self.max_concurrent_requests_spinbox.setValue(self.ai_config.get("max_concurrent_requests", 3))
        params_layout.addRow("最大並行請求數:", self.max_concurrent_requests_spinbox)

        self.enable_validation_checkbox = QCheckBox("啟用翻譯結果驗證")
        self.enable_validation_checkbox.setChecked(self.ai_config.get("enable_validation", False))
        params_layout.addRow("翻譯結果驗證:", self.enable_validation_checkbox)

        self.max_retries_spinbox = QSpinBox()
        self.max_retries_spinbox.setRange(0, 5)
        self.max_retries_spinbox.setValue(self.ai_config.get("max_retries", 3))
        params_layout.addRow("最大重試次數:", self.max_retries_spinbox)

        self.retry_delay_spinbox = QSpinBox()
        self.retry_delay_spinbox.setRange(1, 10)
        self.retry_delay_spinbox.setValue(self.ai_config.get("retry_delay", 2))
        params_layout.addRow("重試延遲(秒):", self.retry_delay_spinbox)

        layout.addWidget(params_group)

        # 控制按鈕
        button_layout = QHBoxLayout()
        save_settings_btn = QPushButton("儲存設定")
        save_settings_btn.clicked.connect(self.save_ai_settings)

        reset_settings_btn = QPushButton("重置")
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
        info_label = QLabel("自定義Prompt模板管理。選擇模板進行編輯，或新增/刪除模板。")
        info_label.setStyleSheet("color: #666; font-style: italic; margin: 10px;")
        layout.addWidget(info_label)

        # 模板管理控制
        template_control_layout = QHBoxLayout()
        template_control_layout.addWidget(QLabel("模板選擇:"))

        self.template_combo = QComboBox()
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        template_control_layout.addWidget(self.template_combo)

        self.new_template_btn = QPushButton("新增")
        self.new_template_btn.clicked.connect(self.new_template)
        template_control_layout.addWidget(self.new_template_btn)

        self.delete_template_btn = QPushButton("刪除")
        self.delete_template_btn.clicked.connect(self.delete_template)
        template_control_layout.addWidget(self.delete_template_btn)

        self.save_template_btn = QPushButton("儲存")
        self.save_template_btn.clicked.connect(self.save_template)
        template_control_layout.addWidget(self.save_template_btn)

        template_control_layout.addStretch()
        layout.addLayout(template_control_layout)

        # 主編輯區域 - 垂直分割
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # System Prompt區域 (2/5)
        system_group = QGroupBox("System Prompt")
        system_layout = QVBoxLayout(system_group)
        self.system_prompt_editor = QTextEdit()
        self.system_prompt_editor.setFont(QFont("Consolas", 10))
        system_layout.addWidget(self.system_prompt_editor)
        main_splitter.addWidget(system_group)

        # User Prompt區域 (2/5)
        user_group = QGroupBox("User Prompt")
        user_layout = QVBoxLayout(user_group)
        self.user_prompt_editor = QTextEdit()
        self.user_prompt_editor.setFont(QFont("Consolas", 10))
        user_layout.addWidget(self.user_prompt_editor)
        main_splitter.addWidget(user_group)

        # 變數參考區域 (1/5)
        variables_group = QGroupBox("變數參考")
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

        self.apply_prompt_btn = QPushButton("套用調整")
        self.apply_prompt_btn.clicked.connect(self.apply_prompt_changes)

        self.reset_prompt_btn = QPushButton("重置")
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
            
            QMessageBox.information(self, "成功", "AI翻譯設定已儲存")
            
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存設定失敗: {str(e)}")
    
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
            
            QMessageBox.information(self, "成功", "AI翻譯設定已重置")
            
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"重置設定失敗: {str(e)}")

    def load_source_content(self):
        """載入來源檔案內容"""
        if not self.source_file or not Path(self.source_file).exists():
            placeholder = "設定模式：目前沒有載入字幕內容。" if self.mode == "settings" else "找不到來源檔案，請確認 2C 流程輸入。"
            self.original_text.setPlainText(placeholder)
            self.original_lines = []
            self.line_count_label.setText("行數: 0")
            self.char_count_label.setText("字元數: 0")
            if self.mode == "settings":
                self.status_label.setText("設定模式：可直接調整 AI 設定與 Prompt")
            else:
                self.status_label.setText("警告：找不到來源檔案")
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

            self.status_label.setText("來源檔案載入完成")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"載入來源檔案失敗: {str(e)}")
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
                self.status_label.setText("Prompt調整已套用")
            else:
                self.status_label.setText("AI翻譯未啟用")

        except Exception as e:
            QMessageBox.warning(self, "警告", f"套用Prompt調整失敗: {str(e)}")

    def reset_prompts(self):
        """重置Prompt為原始設定"""
        try:
            # 重新載入settings.json的原始設定
            settings_file_path = get_settings_filepath()
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

            self.status_label.setText("Prompt已重置為原始設定")

        except Exception as e:
            QMessageBox.warning(self, "警告", f"重置Prompt失敗: {str(e)}")

    def test_api_connection(self):
        """測試API連線"""
        if not self.ai_translator:
            QMessageBox.warning(self, "警告", "AI翻譯未啟用或初始化失敗")
            return

        self.status_label.setText("測試API連線中...")
        self.test_api_btn.setEnabled(False)

        try:
            success, message = self.ai_translator.validate_api_connection()
            if success:
                QMessageBox.information(self, "成功", message)
                self.status_label.setText("API連線測試成功")
            else:
                QMessageBox.warning(self, "失敗", message)
                self.status_label.setText("API連線測試失敗")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"API連線測試錯誤: {str(e)}")
            self.status_label.setText("API連線測試錯誤")
        finally:
            self.test_api_btn.setEnabled(True)

    def start_auto_translation(self):
        """開始自動翻譯"""
        if self.mode != "translation":
            QMessageBox.information(self, "提示", "設定模式下無法執行自動翻譯。")
            return

        if not self.ai_config.get("enabled", False):
            QMessageBox.warning(self, "警告", "AI翻譯未啟用")
            return

        if not self.original_lines:
            QMessageBox.warning(self, "警告", "沒有可翻譯的內容")
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
        self.status_label.setText("AI翻譯進行中...")

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
        self.status_label.setText("AI翻譯完成")

        # 關閉進度窗口
        if hasattr(self, 'progress_window') and self.progress_window:
            self.progress_window.close()

        QMessageBox.information(self, "完成", "AI翻譯已完成，請檢查翻譯結果")

    def on_translation_error(self, error_message: str):
        """翻譯錯誤"""
        self.progress_bar.setVisible(False)
        self.auto_translate_btn.setEnabled(True)
        self.status_label.setText("翻譯失敗")

        # 關閉進度窗口
        if hasattr(self, 'progress_window') and self.progress_window:
            self.progress_window.close()

        QMessageBox.critical(self, "翻譯錯誤", error_message)

    def clear_translation(self):
        """清空翻譯"""
        self.translation_text.clear()
        self.translated_lines = []
        if self.mode == "translation":
            self.status_label.setText("翻譯已清空")
        else:
            self.status_label.setText("設定模式：翻譯區內容已清空")

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
            QMessageBox.warning(self, "警告", "目標檔案未設定，無法儲存翻譯")
            return

        try:
            # 取得翻譯內容
            translation_content = self.translation_text.toPlainText()

            if not translation_content.strip():
                QMessageBox.warning(self, "警告", "沒有翻譯內容可儲存")
                return

            # 確保目標目錄存在
            target_path = Path(self.target_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 儲存翻譯結果
            with open(self.target_file, "w", encoding="utf-8") as f:
                f.write(translation_content)

            self.status_label.setText("翻譯已儲存")
            QMessageBox.information(self, "成功", f"翻譯結果已儲存到: {self.target_file}")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存翻譯失敗: {str(e)}")

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
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            if template_name in ai_prompt_data:
                template_data = ai_prompt_data[template_name]
                system_prompt = template_data.get("prompt_templates", {}).get("system_prompt", "")
                user_prompt = template_data.get("prompt_templates", {}).get("user_prompt_template", "")

                self.system_prompt_editor.setPlainText(system_prompt)
                self.user_prompt_editor.setPlainText(user_prompt)
        except Exception as e:
            QMessageBox.warning(self, "警告", f"載入模板失敗: {str(e)}")

    def load_ai_settings(self):
        """載入AI設定"""
        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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
            QMessageBox.warning(self, "警告", f"載入AI設定失敗: {str(e)}")

    def _sync_config_from_ui(self):
        """從UI同步設定到ai_config"""
        try:
            current_api = self.api_settings_combo.currentText()
            current_model = self.model_settings_combo.currentText()

            # 同步API設定
            if current_api:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)
                api_data = ai_prompt_data.get("default", {}).get("api_settings", {}).get(current_api, {})
                self.ai_config.update({
                    "api_provider": api_data.get("provider", ""),
                    "api_url": api_data.get("url", ""),
                    "api_key": api_data.get("key", "")
                })

            # 同步模型設定
            if current_model:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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
            QMessageBox.warning(self, "警告", f"同步設定失敗: {str(e)}")

    def save_ai_settings(self):
        """儲存AI設定"""
        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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

            with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

            QMessageBox.information(self, "成功", "AI設定已儲存")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存AI設定失敗: {str(e)}")

    def reset_ai_settings(self):
        """重置AI設定"""
        try:
            # 重新載入設定
            self.load_ai_settings()
            QMessageBox.information(self, "成功", "AI設定已重置")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"重置AI設定失敗: {str(e)}")

    def on_api_setting_changed(self):
        """API設定改變"""
        current_api = self.api_settings_combo.currentText()

        if not current_api:
            return

        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            api_data = ai_prompt_data.get("default", {}).get("api_settings", {}).get(current_api, {})
            self.api_provider_edit.setText(api_data.get("provider", ""))
            self.api_url_edit.setText(api_data.get("url", ""))
            self.api_key_edit.setText(api_data.get("key", ""))

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

        except Exception as e:
            QMessageBox.warning(self, "警告", f"載入API設定失敗: {str(e)}")

    def on_model_setting_changed(self):
        """模型設定改變"""
        current_model = self.model_settings_combo.currentText()

        if not current_model:
            return

        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                ai_prompt_data = json.load(f)

            model_data = ai_prompt_data.get("default", {}).get("model_settings", {}).get(current_model, {})
            self.model_edit.setText(model_data.get("model", ""))

            # 同步設定到記憶體並重新初始化翻譯器
            self._sync_config_from_ui()

        except Exception as e:
            QMessageBox.warning(self, "警告", f"載入模型設定失敗: {str(e)}")

    def new_api_setting(self):
        """新增API設定"""
        name, ok = QInputDialog.getText(self, "新增API設定", "輸入API設定名稱:")
        if ok and name.strip():
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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

                with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_settings()
                # 選擇新建立的設定
                index = self.api_settings_combo.findText(name.strip())
                if index >= 0:
                    self.api_settings_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"新增API設定失敗: {str(e)}")

    def delete_api_setting(self):
        """刪除API設定"""
        current_api = self.api_settings_combo.currentText()

        if not current_api:
            QMessageBox.warning(self, "警告", "請先選擇要刪除的API設定")
            return

        reply = QMessageBox.question(self, "確認刪除", f"確定要刪除API設定 '{current_api}' 嗎？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_api in ai_prompt_data.get("default", {}).get("api_settings", {}):
                    del ai_prompt_data["default"]["api_settings"][current_api]

                    with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_settings()

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除API設定失敗: {str(e)}")

    def new_model_setting(self):
        """新增模型設定"""
        name, ok = QInputDialog.getText(self, "新增模型設定", "輸入模型設定名稱:")
        if ok and name.strip():
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if "default" not in ai_prompt_data:
                    ai_prompt_data["default"] = {"api_settings": {}, "model_settings": {}, "prompt_templates": {}, "translation_config": {}}

                if "model_settings" not in ai_prompt_data["default"]:
                    ai_prompt_data["default"]["model_settings"] = {}

                ai_prompt_data["default"]["model_settings"][name.strip()] = {
                    "model": ""
                }

                with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_settings()
                # 選擇新建立的設定
                index = self.model_settings_combo.findText(name.strip())
                if index >= 0:
                    self.model_settings_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"新增模型設定失敗: {str(e)}")

    def delete_model_setting(self):
        """刪除模型設定"""
        current_model = self.model_settings_combo.currentText()

        if not current_model:
            QMessageBox.warning(self, "警告", "請先選擇要刪除的模型設定")
            return

        reply = QMessageBox.question(self, "確認刪除", f"確定要刪除模型設定 '{current_model}' 嗎？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_model in ai_prompt_data.get("default", {}).get("model_settings", {}):
                    del ai_prompt_data["default"]["model_settings"][current_model]

                    with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_settings()

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除模型設定失敗: {str(e)}")

    def load_ai_prompt_templates(self):
        """載入AI Prompt模板"""
        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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
            QMessageBox.warning(self, "警告", f"載入Prompt模板失敗: {str(e)}")

    def new_template(self):
        """新增模板"""
        name, ok = QInputDialog.getText(self, "新增模板", "輸入模板名稱:")
        if ok and name.strip():
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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

                with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                    json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                self.load_ai_prompt_templates()
                # 選擇新建立的模板
                index = self.template_combo.findText(name.strip())
                if index >= 0:
                    self.template_combo.setCurrentIndex(index)

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"新增模板失敗: {str(e)}")

    def delete_template(self):
        """刪除模板"""
        current_template = self.template_combo.currentText()

        if not current_template or current_template == "default":
            QMessageBox.warning(self, "警告", "無法刪除預設模板")
            return

        reply = QMessageBox.question(self, "確認刪除", f"確定要刪除模板 '{current_template}' 嗎？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
                    ai_prompt_data = json.load(f)

                if current_template in ai_prompt_data:
                    del ai_prompt_data[current_template]

                    with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                        json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

                    self.load_ai_prompt_templates()

            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除模板失敗: {str(e)}")

    def save_template(self):
        """儲存模板"""
        current_template = self.template_combo.currentText()

        if not current_template:
            QMessageBox.warning(self, "警告", "請先選擇模板")
            return

        try:
            with open("../settings/AI_prompt.json", "r", encoding="utf-8") as f:
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

            with open("../settings/AI_prompt.json", "w", encoding="utf-8") as f:
                json.dump(ai_prompt_data, f, ensure_ascii=False, indent=4)

            QMessageBox.information(self, "成功", f"模板 '{current_template}' 已儲存")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存模板失敗: {str(e)}")
