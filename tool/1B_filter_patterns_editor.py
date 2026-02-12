#V0.89.00 修正路徑問題讓在任何地方執行都可以正常運作

import sys
from pathlib import Path

# 將專案根目錄加入sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from datetime import datetime
from typing import Dict, List

from modules.settings_path import resolve_settings_asset

class FilterPatternsEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("過濾規則編輯器 v1.0")
        self.root.geometry("800x600")
        
        # 初始化變數
        self.default_db_path = resolve_settings_asset('filter_patterns.json')
        self.backup_dir = resolve_settings_asset('bak_filters')
        self.patterns = self._load_patterns()
        self.has_unsaved_changes = False
        
        # 建立主要框架
        self.create_main_frames()
        self.create_pattern_management()
        self.create_pattern_display()
        
        # 綁定關閉視窗事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_main_frames(self):
        """建立主要框架"""
        # 中間框架 - 規則管理
        self.middle_frame = ttk.Frame(self.root, padding="5")
        self.middle_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def create_pattern_management(self):
        """建立規則管理區域"""
        # 左側 - 規則管理
        self.pattern_frame = ttk.LabelFrame(self.middle_frame, text="規則管理", padding="5")
        self.pattern_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 分類選擇區域
        category_frame = ttk.Frame(self.pattern_frame)
        category_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(category_frame, text="分類:").pack(side=tk.LEFT)
        
        # 分類下拉選單
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(category_frame, textvariable=self.category_var)
        self.category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # 分類管理按鈕
        btn_frame = ttk.Frame(category_frame)
        btn_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="新增分類", command=self.add_new_category).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="編輯分類", command=self.edit_category).pack(side=tk.LEFT, padx=2)
        
        # 更新分類下拉選單
        self.update_category_combo()
        
        # 規則輸入
        ttk.Label(self.pattern_frame, text="規則:").pack(anchor=tk.W)
        self.pattern_var = tk.StringVar()
        self.pattern_entry = ttk.Entry(self.pattern_frame, textvariable=self.pattern_var)
        self.pattern_entry.pack(fill=tk.X, pady=2)
        
        # 按鈕區
        btn_frame = ttk.Frame(self.pattern_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="新增規則", command=self.add_new_pattern).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="儲存變更", command=self.save_patterns).pack(side=tk.LEFT, padx=2)
        
        # 說明文字區域
        help_frame = ttk.LabelFrame(self.pattern_frame, text="正則表達式說明", padding="5")
        help_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        help_text = """正則表達式語法說明：

^ - 表示字串的開始：
  • 確保匹配從行的最開始開始
  • 防止匹配字串中間的部分

[あぁアァ] - 字元集合：
  • [] 表示這是一個字元集合，匹配其中任何一個字元
  • あ - 平假名的「a」音
  • ぁ - 平假名的小寫「a」音
  • ア - 片假名的「a」音
  • ァ - 片假名的小寫「a」音

+ - 表示一個或多個：
  • 匹配前面的字元集合一次或多次
  • 例如可以匹配：「あ」、「ああ」、「あぁあ」等

$ - 表示字串的結束：
  • 確保匹配到行的最後
  • 防止匹配後面還有其他字元
"""
        
        help_text_widget = tk.Text(help_frame, wrap=tk.WORD, height=15, width=40)
        help_text_widget.pack(fill=tk.BOTH, expand=True)
        help_text_widget.insert('1.0', help_text)
        help_text_widget.config(state='disabled')

    def create_pattern_display(self):
        """建立規則顯示區域"""
        # 右側 - 規則顯示
        self.display_frame = ttk.LabelFrame(self.middle_frame, text="現有規則", padding="5")
        self.display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 建立樹狀顯示
        self.tree = ttk.Treeview(self.display_frame, columns=('Pattern',), show='tree headings')
        self.tree.heading('Pattern', text='規則樣式')
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # 捲軸
        scrollbar = ttk.Scrollbar(self.display_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 綁定雙擊事件
        self.tree.bind('<Double-1>', self.edit_pattern)
        
        # 綁定刪除鍵
        self.tree.bind('<Delete>', lambda e: self.remove_selected_pattern())
        
        # 更新顯示
        self.update_pattern_display()

    def _load_patterns(self) -> Dict[str, List[str]]:
        """載入過濾規則"""
        try:
            # 嘗試從預設路徑載入
            if self.default_db_path.exists():
                with open(self.default_db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 如果預設路徑不存在，讓使用者選擇檔案
                file_path = filedialog.askopenfilename(
                    title="選擇過濾規則檔案",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
                
                if file_path:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    # 如果使用者取消選擇，建立預設規則
                    return {
                        "moan": [
                            r'^[あぁアァ]+$',
                            r'^[んンッ]+$',
                            r'^[いぃイィ]+$',
                            r'^[うぅウゥ]+$',
                            r'^[えぇエェ]+$',
                            r'^[おぉオォ]+$'
                        ]
                    }
        except Exception as e:
            messagebox.showerror("錯誤", f"載入規則檔案時發生錯誤：{str(e)}")
            return {"moan": []}

    def save_patterns(self):
        """儲存規則並建立備份"""
        try:
            # 確保目錄存在
            self.default_db_path.parent.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # 儲存當前規則
            with open(self.default_db_path, 'w', encoding='utf-8') as f:
                json.dump(self.patterns, f, ensure_ascii=False, indent=2)
            
            # 建立備份
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = self.backup_dir / f'filter_patterns_{timestamp}.json'
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(self.patterns, f, ensure_ascii=False, indent=2)
            
            self.has_unsaved_changes = False
            messagebox.showinfo("成功", "規則已儲存，並建立備份檔案")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存規則時發生錯誤：{str(e)}")

    def update_category_combo(self):
        """更新分類下拉選單"""
        categories = list(self.patterns.keys())
        self.category_combo['values'] = categories
        if categories:
            self.category_combo.set(categories[0])

    def update_pattern_display(self):
        """更新規則顯示"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for category, patterns in self.patterns.items():
            category_item = self.tree.insert('', 'end', text=category)
            for pattern in patterns:
                self.tree.insert(category_item, 'end', values=(pattern,))

    def add_new_category(self):
        """新增分類"""
        new_category = tk.simpledialog.askstring("新增分類", "請輸入新分類名稱：")
        if new_category:
            if new_category not in self.patterns:
                self.patterns[new_category] = []
                self.update_category_combo()
                self.update_pattern_display()
                self.has_unsaved_changes = True
            else:
                messagebox.showwarning("警告", "此分類已存在")

    def edit_category(self):
        """編輯分類名稱"""
        old_category = self.category_var.get()
        if not old_category:
            messagebox.showwarning("警告", "請先選擇要編輯的分類")
            return
            
        new_category = tk.simpledialog.askstring(
            "編輯分類",
            "請輸入新的分類名稱：",
            initialvalue=old_category
        )
        
        if new_category and new_category != old_category:
            if new_category not in self.patterns:
                self.patterns[new_category] = self.patterns.pop(old_category)
                self.update_category_combo()
                self.update_pattern_display()
                self.category_combo.set(new_category)
                self.has_unsaved_changes = True
            else:
                messagebox.showwarning("警告", "此分類名稱已存在")

    def add_new_pattern(self):
        """新增規則"""
        category = self.category_var.get()
        pattern = self.pattern_var.get().strip()
        
        if not category or not pattern:
            messagebox.showwarning("警告", "分類和規則都不能為空")
            return
        
        try:
            import re
            re.compile(pattern)
        except re.error:
            messagebox.showerror("錯誤", "無效的正則表達式")
            return
        
        if pattern not in self.patterns[category]:
            self.patterns[category].append(pattern)
            self.update_pattern_display()
            self.pattern_var.set("")
            self.has_unsaved_changes = True
        else:
            messagebox.showinfo("提示", "此規則已存在")

    def edit_pattern(self, event):
        """編輯規則"""
        item = self.tree.selection()[0]
        parent = self.tree.parent(item)
        
        # 只有規則可以編輯，分類不能在這裡編輯
        if parent:
            category = self.tree.item(parent)['text']
            old_pattern = self.tree.item(item)['values'][0]
            
            new_pattern = tk.simpledialog.askstring(
                "編輯規則",
                "請輸入新的規則：",
                initialvalue=old_pattern
            )
            
            if new_pattern and new_pattern != old_pattern:
                try:
                    import re
                    re.compile(new_pattern)
                    
                    # 更新規則
                    patterns = self.patterns[category]
                    idx = patterns.index(old_pattern)
                    patterns[idx] = new_pattern
                    
                    self.update_pattern_display()
                    self.has_unsaved_changes = True
                    
                except re.error:
                    messagebox.showerror("錯誤", "無效的正則表達式")
                except ValueError:
                    messagebox.showerror("錯誤", "找不到原規則")

    def remove_selected_pattern(self):
        """刪除選中的規則或分類"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇要刪除的項目")
            return
        
        item = selected[0]
        parent = self.tree.parent(item)
        
        try:
            if parent:  # 刪除規則
                category = self.tree.item(parent)['text']
                pattern = self.tree.item(item)['values'][0]
                
                if messagebox.askyesno("確認", f"確定要刪除規則「{pattern}」嗎？"):
                    if category in self.patterns and pattern in self.patterns[category]:
                        self.patterns[category].remove(pattern)
                        self.update_pattern_display()
                        self.has_unsaved_changes = True
                    else:
                        messagebox.showerror("錯誤", "找不到要刪除的規則")
                        
            else:  # 刪除分類
                category = self.tree.item(item)['text']
                
                if messagebox.askyesno("確認", f"確定要刪除分類「{category}」及其所有規則嗎？"):
                    if category in self.patterns:
                        del self.patterns[category]
                        self.update_category_combo()
                        self.update_pattern_display()
                        self.has_unsaved_changes = True
                    else:
                        messagebox.showerror("錯誤", "找不到要刪除的分類")
                        
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除過程發生錯誤: {str(e)}")

    def on_closing(self):
        """關閉視窗前檢查是否有未儲存的變更"""
        if self.has_unsaved_changes:
            response = messagebox.askyesnocancel(
                "未儲存的變更",
                "有未儲存的變更，是否要儲存？"
            )
            
            if response is None:  # 取消關閉
                return
            elif response:  # 儲存變更
                self.save_patterns()
            
        self.root.destroy()


def main():
    root = tk.Tk()
    app = FilterPatternsEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
