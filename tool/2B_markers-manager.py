#V0.89.00 修正路徑問題讓在任何地方執行都可以正常運作

import sys
from pathlib import Path

# 將專案根目錄加入sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import json
import os
from datetime import datetime
from shutil import copy2
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QTextEdit, QPushButton, 
    QTableWidget, QTableWidgetItem, QTabWidget, QMessageBox, QFileDialog, QSizePolicy)
from PyQt6.QtCore import Qt

from modules.settings_path import resolve_settings_asset

class MarkersDBManager(QMainWindow):
    def __init__(self):
        super().__init__()
        # 修改資料庫和備份路徑
        self.db_file = resolve_settings_asset('markers_db.json')
        self.backup_dir = project_root / 'backup' / 'bak_markers'
        self.has_unsaved_changes = False
        self.current_data = None
        
        # 確保目錄存在
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 檢查數據庫文件是否存在
        if not self.check_db_file():
            self.select_db_file()
            
        self.load_db()
        self.init_ui()
        
        # 設置預設視窗大小
        self.resize(800, 600)

    def check_db_file(self):
        return self.db_file.exists()

    def select_db_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "選擇標記數據庫文件",
            str(self.db_file.parent),  # 修改預設路徑
            "JSON Files (*.json);;All Files (*)"
        )
        if file_name:
            self.db_file = Path(file_name)
        else:
            # 如果用戶取消選擇，創建新的數據庫文件
            self.create_new_db()

    def create_new_db(self):
        self.db = {
            "A": {
                "description": "行為/狀態相關",
                "items": {}
            },
            "B": {
                "description": "身體相關",
                "items": {}
            }
        }
        self.save_db()

    def create_backup(self):
        # 生成備份文件名，格式為: markers_db_YYYYMMDD_HHMMSS.json
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = self.backup_dir / f'markers_db_{timestamp}.json'
        
        try:
            # 複製當前數據庫文件到備份目錄
            copy2(self.db_file, backup_file)
            self.statusBar().showMessage(f'備份創建成功: {backup_file}', 3000)
        except Exception as e:
            QMessageBox.warning(self, '備份錯誤', f'創建備份時發生錯誤：{str(e)}')

    def restore_backup(self):
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                '未儲存的更改',
                '還原前是否要保存當前的更改？',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.save_current_changes()

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "選擇要還原的備份文件",
            str(self.backup_dir),  # 修改預設路徑
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_name:
            try:
                # 讀取備份文件
                with open(file_name, 'r', encoding='utf-8') as f:
                    self.db = json.load(f)
                
                # 保存到當前數據庫文件
                self.save_db()
                self.update_markers_table()
                
                QMessageBox.information(self, '還原成功', '數據已成功還原！')
            except Exception as e:
                QMessageBox.warning(self, '還原錯誤', f'還原備份時發生錯誤：{str(e)}')

    def load_db(self):
        try:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                self.db = json.load(f)
        except FileNotFoundError:
            self.create_new_db()

    def save_db(self):
        """統一的數據庫保存方法"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.warning(self, '儲存錯誤', f'儲存數據庫時發生錯誤：{str(e)}')
            return False

    def init_ui(self):
        self.setWindowTitle('標記資料庫管理器 V4(241101')
        
        # 主要區域用TabWidget
        main_tabs = QTabWidget()
        
        # Tab1: 現有標記編輯
        edit_tab = QWidget()
        edit_layout = QVBoxLayout()
        
        # 上方按鈕列
        top_buttons = QHBoxLayout()
        restore_btn = QPushButton('還原備份')
        restore_btn.clicked.connect(self.restore_backup)
        top_buttons.addWidget(restore_btn)
        top_buttons.addStretch()
        
        # 類別選擇
        category_layout = QHBoxLayout()
        category_label = QLabel('類別:')
        self.category_combo = QComboBox()
        self.category_combo.addItems(['A', 'B'])
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo)
        
        # 標記表格
        self.markers_table = QTableWidget()
        self.markers_table.setColumnCount(5)
        self.markers_table.setHorizontalHeaderLabels([
            '標記ID', '日文原文', '原意譯文', '委婉譯文', '時間'
        ])
        
        # 設置各欄位的寬度
        self.markers_table.setColumnWidth(0, 80)   # 標記ID
        self.markers_table.setColumnWidth(1, 200)  # 日文原文
        self.markers_table.setColumnWidth(2, 150)  # 原意譯文
        self.markers_table.setColumnWidth(3, 150)  # 委婉譯文
        self.markers_table.setColumnWidth(4, 100)  # 時間
        
        # 設置表格變更事件
        self.markers_table.itemChanged.connect(self.on_table_changed)
        
        # 編輯按鈕
        edit_buttons = QHBoxLayout()
        add_btn = QPushButton('新增標記')
        save_btn = QPushButton('儲存')
        delete_btn = QPushButton('刪除選中')
        add_btn.clicked.connect(self.add_marker)
        save_btn.clicked.connect(self.save_current_changes)
        delete_btn.clicked.connect(self.delete_marker)
        edit_buttons.addWidget(add_btn)
        edit_buttons.addWidget(save_btn)
        edit_buttons.addWidget(delete_btn)
        
        edit_layout.addLayout(top_buttons)
        edit_layout.addLayout(category_layout)
        edit_layout.addWidget(self.markers_table)
        edit_layout.addLayout(edit_buttons)
        edit_tab.setLayout(edit_layout)
        
        # Category change event - 移到這裡，確保所有UI元素都已創建
        self.category_combo.currentTextChanged.connect(self.on_category_changed)
        
        # Tab2: 新標記匯入
        import_tab = QWidget()
        import_layout = QVBoxLayout()
        
        # 匯入區域
        self.import_text = QTextEdit()
        self.import_text.setPlaceholderText('請貼上新的AI翻譯標記...')
        
        # 按鈕區域使用水平布局
        button_layout = QHBoxLayout()
        
        import_btn = QPushButton('分析並匯入')
        clear_btn = QPushButton('清除內容')
        
        # 設定按鈕大小策略
        import_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        import_btn.clicked.connect(lambda: self.import_new_markers(self.import_text.toPlainText()))
        clear_btn.clicked.connect(lambda: self.import_text.clear())
        
        button_layout.addWidget(import_btn)
        button_layout.addWidget(clear_btn)
        
        import_layout.addWidget(QLabel('新標記匯入:'))
        import_layout.addWidget(self.import_text)
        import_layout.addLayout(button_layout)
        import_tab.setLayout(import_layout)
        
        # 加入Tabs
        main_tabs.addTab(edit_tab, "編輯現有標記")
        main_tabs.addTab(import_tab, "匯入新標記")
        
        self.setCentralWidget(main_tabs)
        
        # 最後再更新表格內容
        self.update_markers_table()
            
    def get_complete_id_list(self, category):
        # 找出該類別最大的 ID 號碼
        max_id = 0
        for marker_id in self.db[category]['items'].keys():
            num = int(marker_id.split('-')[1])
            max_id = max(max_id, num)
        # 生成完整的 ID 列表
        return [f"{category}-{i}" for i in range(1, max_id + 1)]

    def on_table_changed(self, item):
        self.has_unsaved_changes = True
        row = item.row()
        
        # 保存當前編輯的數據
        marker_id = self.markers_table.item(row, 0).text()
        category = self.category_combo.currentText()
        
        # 獲取日文原文文字並轉換為列表
        jp_text = self.markers_table.item(row, 1).text()
        jp_list = [x.strip() for x in jp_text.split(',')] if jp_text else []
        
        # 構建更新的數據
        updated_data = {
            'jp': jp_list,
            'input_zh': self.markers_table.item(row, 2).text(),
            'zh': self.markers_table.item(row, 3).text(),
            'time': self.markers_table.item(row, 4).text()
        }
        
        # 更新內存中的數據
        self.current_data = (category, marker_id, updated_data)

    def on_category_changed(self, new_category):
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                '未儲存的更改',
                '您有未儲存的更改，是否要儲存？',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.save_current_changes()
            elif reply == QMessageBox.StandardButton.Cancel:
                # 恢復之前的選擇
                self.category_combo.setCurrentText(self.current_data[0])
                return
                
        self.has_unsaved_changes = False
        self.current_data = None
        self.update_markers_table()

    def save_current_changes(self):
        if not self.has_unsaved_changes:
            QMessageBox.information(self, '提示', '沒有需要儲存的更改')
            return
            
        try:
            category = self.category_combo.currentText()
            items = {}
            
            # 從表格中獲取所有數據
            for row in range(self.markers_table.rowCount()):
                marker_id = self.markers_table.item(row, 0).text()
                # 檢查該行是否有數據
                if (self.markers_table.item(row, 1) and 
                    self.markers_table.item(row, 1).text().strip()):
                    items[marker_id] = {
                        'jp': [x.strip() for x in self.markers_table.item(row, 1).text().split(',')],
                        'input_zh': self.markers_table.item(row, 2).text(),
                        'zh': self.markers_table.item(row, 3).text(),
                        'time': self.markers_table.item(row, 4).text()
                    }
            
            # 更新數據庫
            self.db[category]['items'] = items
            self.save_db()
            self.has_unsaved_changes = False
            
            QMessageBox.information(self, '成功', '更改已成功儲存！')
            
        except Exception as e:
            QMessageBox.warning(self, '錯誤', f'儲存失敗：{str(e)}')

    def add_marker(self):
        category = self.category_combo.currentText()
        # 找出最大的ID號碼
        existing_ids = [int(id.split('-')[1]) for id in self.db[category]['items'].keys()]
        new_id = max(existing_ids + [0]) + 1
        new_marker_id = f"{category}-{new_id}"
        
        # 取得今天的日期
        current_date = datetime.now().strftime('%y/%m/%d')
        
        # 新增空白記錄
        self.db[category]['items'][new_marker_id] = {
            'jp': [''],
            'zh': '',
            'input_zh': '',
            'time': current_date
        }
        
        self.save_db()
        self.update_markers_table()
        
        # 選中新增的行
        for row in range(self.markers_table.rowCount()):
            if self.markers_table.item(row, 0).text() == new_marker_id:
                self.markers_table.selectRow(row)
                break

    def delete_marker(self):
        selected_items = self.markers_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '警告', '請先選擇要刪除的標記')
            return
            
        reply = QMessageBox.question(
            self,
            '確認刪除',
            '確定要刪除選中的標記嗎？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            row = selected_items[0].row()
            marker_id = self.markers_table.item(row, 0).text()
            category = self.category_combo.currentText()
            
            # 刪除數據
            if marker_id in self.db[category]['items']:
                del self.db[category]['items'][marker_id]
                self.save_db()
                self.update_markers_table()

    def update_markers_table(self):
        # 暫時斷開itemChanged信號連接
        self.markers_table.itemChanged.disconnect(self.on_table_changed)
        
        category = self.category_combo.currentText()
        complete_ids = self.get_complete_id_list(category)
        
        self.markers_table.setRowCount(len(complete_ids))
        for row, marker_id in enumerate(complete_ids):
            # 設置 ID
            id_item = QTableWidgetItem(marker_id)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # ID 不可編輯
            self.markers_table.setItem(row, 0, id_item)
            
            # 如果資料存在則填入，不存在則留空
            if marker_id in self.db[category]['items']:
                data = self.db[category]['items'][marker_id]
                self.markers_table.setItem(row, 1, QTableWidgetItem(','.join(data['jp'])))
                self.markers_table.setItem(row, 2, QTableWidgetItem(data['input_zh']))
                self.markers_table.setItem(row, 3, QTableWidgetItem(data['zh']))
                self.markers_table.setItem(row, 4, QTableWidgetItem(data['time']))
            else:
                # 設置空白項目，保留 ID 的位置
                for col in range(1, self.markers_table.columnCount()):
                    self.markers_table.setItem(row, col, QTableWidgetItem(""))
        
        # 重新連接itemChanged信號
        self.markers_table.itemChanged.connect(self.on_table_changed)

    def import_new_markers(self, text):
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                '未儲存的更改',
                '您有未儲存的更改，是否要在匯入前儲存？',
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.save_current_changes()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        try:
            # 移除注釋
            import re
            text = re.sub(r'//.*?\n', '\n', text)
            new_markers = json.loads(text)
            current_date = datetime.now().strftime('%y/%m/%d')
            imported_count = 0
            
            # 檢查是否為簡化格式（直接是標記ID的字典）
            if any(key.startswith(('A-', 'B-')) for key in new_markers.keys()):
                # 處理簡化格式
                for marker_id, data in new_markers.items():
                    category = marker_id[0]  # 取得類別（A 或 B）
                    
                    # 確保類別存在
                    if category not in self.db:
                        self.db[category] = {"description": "新增類別", "items": {}}
                    
                    if marker_id in self.db[category]['items']:
                        # 合併日文原文列表
                        existing_jp = set(self.db[category]['items'][marker_id]['jp'])
                        new_jp = set(data.get('jp', []))
                        combined_jp = list(existing_jp.union(new_jp))
                        
                        # 更新現有記錄
                        current_record = self.db[category]['items'][marker_id]
                        current_record['jp'] = combined_jp
                        
                        # 只在新數據有值時更新其他欄位
                        if data.get('zh'):
                            current_record['zh'] = data['zh']
                        if data.get('input_zh'):
                            current_record['input_zh'] = data['input_zh']
                        
                        # 更新時間
                        current_record['time'] = current_date
                    else:
                        # 新增記錄
                        self.db[category]['items'][marker_id] = {
                            'jp': data.get('jp', []),
                            'zh': data.get('zh', ''),
                            'input_zh': data.get('input_zh', ''),
                            'time': current_date
                        }
                    
                    imported_count += 1
            else:
                # 處理完整格式
                for category in ['A', 'B']:
                    if category in new_markers and 'items' in new_markers[category]:
                        for marker_id, data in new_markers[category]['items'].items():
                            if marker_id in self.db[category]['items']:
                                # 合併日文原文列表
                                existing_jp = set(self.db[category]['items'][marker_id]['jp'])
                                new_jp = set(data['jp'])
                                combined_jp = list(existing_jp.union(new_jp))
                                
                                # 更新現有記錄
                                current_record = self.db[category]['items'][marker_id]
                                current_record['jp'] = combined_jp
                                
                                # 只在新數據有值時更新其他欄位
                                if data.get('zh'):
                                    current_record['zh'] = data['zh']
                                if data.get('input_zh'):
                                    current_record['input_zh'] = data['input_zh']
                                
                                # 更新時間
                                current_record['time'] = current_date
                            else:
                                # 新增記錄
                                self.db[category]['items'][marker_id] = {
                                    'jp': data.get('jp', []),
                                    'zh': data.get('zh', ''),
                                    'input_zh': data.get('input_zh', ''),
                                    'time': current_date
                                }
                            
                            imported_count += 1
            
            # 保存更新並建立備份
            if self.save_db():  # 使用統一的save_db方法
                self.create_backup()
                self.update_markers_table()
                QMessageBox.information(self, '成功', f'已成功匯入 {imported_count} 個標記！')
            else:
                QMessageBox.warning(self, '錯誤', '保存失敗，請檢查文件是否可寫入。')
                return
            
        except json.JSONDecodeError:
            QMessageBox.warning(self, '錯誤', '無效的JSON格式！\n請確認是否有未移除的注釋或格式錯誤。')
        except Exception as e:
            QMessageBox.warning(self, '錯誤', f'匯入失敗：{str(e)}')

    def closeEvent(self, event):
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
                self.save_current_changes()
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
                
        event.accept()

if __name__ == '__main__':
    def main():
        app = QApplication(sys.argv)
        window = MarkersDBManager()
        window.show()
        sys.exit(app.exec())
    
    main()
