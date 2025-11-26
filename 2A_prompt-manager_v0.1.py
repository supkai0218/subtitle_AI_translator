import sys
import json
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QTextEdit, QPushButton, QTableWidget, QTableWidgetItem, 
    QMessageBox, QDialog, QComboBox, QDialogButtonBox, QLineEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard

class PromptVersionDialog(QDialog):
    """Prompt 版本列表對話框"""
    def __init__(self, prompts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 版本列表")
        self.setModal(True)
        self.resize(800, 400)
        self.selected_prompt = None
        
        layout = QVBoxLayout(self)
        
        # 版本列表
        self.version_table = QTableWidget()
        self.version_table.setColumnCount(5)
        self.version_table.setHorizontalHeaderLabels([
            '註記', '最後修改時間', 'Prompt內容預覽', 'AI名稱', 'LLM版本'
        ])
        
        # 設置欄位寬度
        self.version_table.setColumnWidth(0, 200)   # 註記
        self.version_table.setColumnWidth(1, 150)   # 修改時間
        self.version_table.setColumnWidth(2, 250)   # Prompt預覽
        self.version_table.setColumnWidth(3, 100)   # AI名稱
        self.version_table.setColumnWidth(4, 100)   # LLM版本
        
        # 雙擊事件
        self.version_table.itemDoubleClicked.connect(self.select_version)
        
        # 填充資料
        self.version_table.setRowCount(len(prompts))
        for row, prompt in enumerate(prompts):
            # 註記預覽
            note_preview = prompt['note'][:50] + '...' if len(prompt['note']) > 50 else prompt['note']
            self.version_table.setItem(row, 0, QTableWidgetItem(note_preview))
            # 修改時間
            self.version_table.setItem(row, 1, QTableWidgetItem(prompt['last_modified']))
            # Prompt預覽
            preview = prompt['content'][:50] + '...' if len(prompt['content']) > 50 else prompt['content']
            self.version_table.setItem(row, 2, QTableWidgetItem(preview))
            # AI名稱
            self.version_table.setItem(row, 3, QTableWidgetItem(prompt['ai_name']))
            # LLM版本
            self.version_table.setItem(row, 4, QTableWidgetItem(prompt['llm_version']))
        
        layout.addWidget(self.version_table)
        
        # 按鈕
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def select_version(self, item):
        row = item.row()
        self.selected_prompt = {
            'row': row,
            'ai_name': self.version_table.item(row, 3).text(),
            'llm_version': self.version_table.item(row, 4).text()
        }
        self.accept()

class PromptManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db_file = '../settings/prompt.json'
        self.has_unsaved_changes = False
        self.current_prompt = None
        self.editing_mode = False
        
        self.init_ui()
        self.load_db()
        
        # 設置預設視窗大小
        self.resize(800, 600)
        
    def init_ui(self):
        self.setWindowTitle('Prompt 管理工具 v0.1')
        
        # 主要區域
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # AI模型資訊區域
        info_layout = QHBoxLayout()
        
        # AI名稱
        ai_layout = QHBoxLayout()
        ai_layout.addWidget(QLabel("AI 名稱:"))
        self.ai_combo = QComboBox()
        self.ai_combo.addItems(["Claude", "ChatGPT", "其他"])
        self.ai_combo.setEnabled(False)
        ai_layout.addWidget(self.ai_combo)
        info_layout.addLayout(ai_layout)
        
        # LLM版本
        version_layout = QHBoxLayout()
        version_layout.addWidget(QLabel("LLM 版本:"))
        self.version_combo = QComboBox()
        self.version_combo.addItems([
            "Claude-3.5 Sonnet",
            "Claude-3 Opus",
            "Claude-3 Haiku",
            "GPT-4",
            "GPT-3.5",
            "其他"
        ])
        self.version_combo.setEnabled(False)
        version_layout.addWidget(self.version_combo)
        info_layout.addLayout(version_layout)
        
        # 最後修改時間
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("最後修改:"))
        self.time_edit = QLineEdit()
        self.time_edit.setReadOnly(True)  # 預設為唯讀
        self.time_edit.setMaximumWidth(150)  # 限制寬度
        time_layout.addWidget(self.time_edit)
        info_layout.addLayout(time_layout)
        
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # Prompt 內容
        layout.addWidget(QLabel("Prompt 內容:"))
        self.content_edit = QTextEdit()
        self.content_edit.setReadOnly(True)
        layout.addWidget(self.content_edit)
        
        # 註記
        layout.addWidget(QLabel("註記:"))
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(100)
        self.note_edit.setReadOnly(True)
        layout.addWidget(self.note_edit)
        
        # 按鈕區域
        button_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton('複製 Prompt')
        self.edit_btn = QPushButton('編輯')
        self.delete_btn = QPushButton('刪除')
        self.save_btn = QPushButton('儲存')
        self.new_btn = QPushButton('新增 Prompt')
        self.version_btn = QPushButton('其他版本')
        
        self.copy_btn.clicked.connect(self.copy_prompt)
        self.edit_btn.clicked.connect(self.toggle_edit_mode)
        self.delete_btn.clicked.connect(self.delete_prompt)
        self.save_btn.clicked.connect(self.save_prompt)
        self.new_btn.clicked.connect(self.new_prompt)
        self.version_btn.clicked.connect(self.show_versions)
        
        self.save_btn.setEnabled(False)
        
        button_layout.addWidget(self.copy_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.new_btn)
        button_layout.addWidget(self.version_btn)
        
        layout.addLayout(button_layout)
        
    def load_db(self):
        try:
            # 確保json目錄存在
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            
            # 嘗試讀取檔案
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.db = json.load(f)
            else:
                # 如果檔案不存在，創建預設資料
                self.db = {'prompts': []}
                self.save_db()
            
            # 載入最新的 prompt
            if self.db['prompts']:
                latest_prompt = max(self.db['prompts'], 
                                  key=lambda x: x['last_modified'])
                self.load_prompt(latest_prompt)
            
        except Exception as e:
            QMessageBox.warning(self, '錯誤', f'載入資料庫時發生錯誤：{str(e)}')
    
    def load_prompt(self, prompt_data):
        """載入指定的 prompt 到介面"""
        self.current_prompt = prompt_data
        self.ai_combo.setCurrentText(prompt_data['ai_name'])
        self.version_combo.setCurrentText(prompt_data['llm_version'])
        self.content_edit.setText(prompt_data['content'])
        self.note_edit.setText(prompt_data['note'])
        self.time_edit.setText(prompt_data['last_modified'])
        
    def save_db(self):
        """儲存整個資料庫"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
            self.has_unsaved_changes = False
            return True
        except Exception as e:
            QMessageBox.warning(self, '錯誤', f'儲存資料庫時發生錯誤：{str(e)}')
            return False
            
    def toggle_edit_mode(self):
        """切換編輯模式"""
        self.editing_mode = not self.editing_mode
        
        # 更新界面狀態
        self.ai_combo.setEnabled(self.editing_mode)
        self.version_combo.setEnabled(self.editing_mode)
        self.content_edit.setReadOnly(not self.editing_mode)
        self.note_edit.setReadOnly(not self.editing_mode)
        self.time_edit.setReadOnly(not self.editing_mode)
        
        # 更新按鈕狀態
        self.edit_btn.setText('完成編輯' if self.editing_mode else '編輯')
        self.save_btn.setEnabled(self.editing_mode)
        
        # 如果退出編輯模式且有未儲存的更改
        if not self.editing_mode and self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                '未儲存的更改',
                '您有未儲存的更改，是否要儲存？',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_prompt()
            else:
                # 恢復原始資料
                if self.current_prompt:
                    self.load_prompt(self.current_prompt)
                self.has_unsaved_changes = False
    
    def save_prompt(self):
        """儲存當前 prompt"""
        if not self.editing_mode:
            return
            
        prompt_data = {
            'ai_name': self.ai_combo.currentText(),
            'llm_version': self.version_combo.currentText(),
            'content': self.content_edit.toPlainText(),
            'note': self.note_edit.toPlainText(),
            'last_modified': self.time_edit.text()
        }
        
        # 如果是新增，直接加入列表
        if self.current_prompt is None:
            self.db['prompts'].append(prompt_data)
        else:
            # 更新現有的 prompt
            for i, prompt in enumerate(self.db['prompts']):
                if (prompt['ai_name'] == self.current_prompt['ai_name'] and
                    prompt['last_modified'] == self.current_prompt['last_modified']):
                    self.db['prompts'][i] = prompt_data
                    break
        
        if self.save_db():
            self.current_prompt = prompt_data
            self.has_unsaved_changes = False
            self.toggle_edit_mode()  # 退出編輯模式
            QMessageBox.information(self, '成功', '儲存成功！')
    
    def copy_prompt(self):
        """複製 prompt 內容到剪貼板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.content_edit.toPlainText())
        self.statusBar().showMessage('已複製 Prompt 到剪貼板', 3000)
    
    def delete_prompt(self):
        """刪除當前 prompt"""
        if not self.current_prompt:
            return
            
        reply = QMessageBox.question(
            self,
            '確認刪除',
            '確定要刪除此 Prompt 嗎？此操作無法撤銷。',
            QMessageBox.StandardButton.Yes | 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 從資料庫中刪除
            self.db['prompts'] = [p for p in self.db['prompts'] 
                                if not (p['ai_name'] == self.current_prompt['ai_name'] and
                                       p['last_modified'] == self.current_prompt['last_modified'])]
            
            if self.save_db():
                # 清空界面或載入其他 prompt
                if self.db['prompts']:
                    self.load_prompt(self.db['prompts'][-1])
                else:
                    self.new_prompt()
                QMessageBox.information(self, '成功', '刪除成功！')
    
    def new_prompt(self):
        """建立新的 prompt"""
        self.current_prompt = None
        self.ai_combo.setCurrentText("Claude")
        self.version_combo.setCurrentText("Claude-3.5 Sonnet")
        self.content_edit.clear()
        self.note_edit.clear()
        self.time_edit.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 進入編輯模式
        if not self.editing_mode:
            self.toggle_edit_mode()
    
    def show_versions(self):
        """顯示版本列表對話框"""
        dialog = PromptVersionDialog(self.db['prompts'], self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_prompt:
            # 找到選中的 prompt
            selected_prompt = self.db['prompts'][dialog.selected_prompt['row']]
            self.load_prompt(selected_prompt)
    
    def closeEvent(self, event):
        """關閉視窗前檢查是否有未儲存的更改"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                '未儲存的更改',
                '您有未儲存的更改，是否要在關閉前儲存？',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if not self.save_prompt():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
                
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = PromptManager()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
