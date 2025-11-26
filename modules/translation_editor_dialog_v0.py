from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QTextEdit, QPushButton, QMessageBox)
from pathlib import Path

class TranslationEditorDialog(QDialog):
    def __init__(self, source_file, target_file, parent=None):
        super().__init__(parent)
        self.source_file = source_file
        self.target_file = target_file
        self.source_line_count = 0
        self.setup_ui()
        self.load_source_file()

    def setup_ui(self):
        self.setWindowTitle("AI翻譯內容確認")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # 說明文字
        info_label = QLabel("請將AI翻譯完成的內容貼上：")
        layout.addWidget(info_label)
        
        # 文字編輯區域
        self.editor = QTextEdit()
        layout.addWidget(self.editor)
        
        # 行數信息區域
        count_layout = QHBoxLayout()
        self.source_count_label = QLabel("來源檔案行數：0")
        self.current_count_label = QLabel("當前內容行數：0")
        count_layout.addWidget(self.source_count_label)
        count_layout.addWidget(self.current_count_label)
        layout.addLayout(count_layout)
        
        # 按鈕區域
        button_layout = QHBoxLayout()
        confirm_button = QPushButton("確認")
        cancel_button = QPushButton("取消")
        confirm_button.clicked.connect(self.confirm)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(confirm_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # 連接文字變更信號
        self.editor.textChanged.connect(self.update_line_count)

    def load_source_file(self):
        try:
            with open(self.source_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                self.source_line_count = len(lines)
                self.source_count_label.setText(f"來源檔案行數：{self.source_line_count}")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"讀取來源檔案失敗：{str(e)}")

    def update_line_count(self):
        content = self.editor.toPlainText()
        current_count = len(content.splitlines())
        self.current_count_label.setText(f"當前內容行數：{current_count}")

    def confirm(self):
        content = self.editor.toPlainText()
        current_count = len(content.splitlines())
        
        if current_count != self.source_line_count:
            reply = QMessageBox.warning(
                self,
                "行數不符",
                f"當前內容行數（{current_count}）與來源檔案行數（{self.source_line_count}）不符。\n"
                "是否要繼續修改？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                return
        
        try:
            # 確保目標目錄存在
            Path(self.target_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 儲存內容
            with open(self.target_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存檔案失敗：{str(e)}")
