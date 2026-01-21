#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影片音頻分離工具 - GUI 版本
提供圖形使用者介面，方便操作

作者: Auto-generated
版本: 1.0.0
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog,messagebox
import threading
import importlib.util
from datetime import datetime

# ============================================================================
# 載入核心功能模組
# ============================================================================

def load_core_module():
    """動態載入核心功能模組"""
    core_path =os.path.join(os.path.dirname(__file__), "film-voice-spliter.py")
    spec = importlib.util.spec_from_file_location("film_voice_spliter", core_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ============================================================================
# GUI 主類別
# ============================================================================

class AudioExtractorGUI:
    """影片音頻提取器 GUI 類別"""
    
    def __init__(self, root):
        """初始化 GUI"""
        self.root = root
        self.root.title("影片音頻提取工具 - Video Audio Extractor v1.0")
        self.root.geometry("850x750")
        self.root.minsize(700, 600)
        
        # 載入核心模組
        try:
            self.core = load_core_module()
        except Exception as e:
            messagebox.showerror("錯誤", f"無法載入核心模組: {e}")
            sys.exit(1)
        
        # 初始化變數
        self.file_list = []
        self.output_dir_var = tk.StringVar(value="./output")
        self.format_var = tk.StringVar(value="mp3")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label_var = tk.StringVar(value="0% (0/0)")
        self.is_processing = False
        
        # 創建 UI 元件
        self.create_widgets()
        
        # 檢查 ffmpeg
        self.check_ffmpeg()
    
    def create_widgets(self):
        """創建所有 UI 元件"""
        # 標題框架
        title_frame = ttk.Frame(self.root, padding=10)
        title_frame.pack(fill=tk.X)
        
        title_label = ttk.Label(
            title_frame,
            text="影片音頻提取工具",
            font=("Arial", 16, "bold")
        )
        title_label.pack()
        
        subtitle_label = ttk.Label(
            title_frame,
            text="Video Audio Extractor - 批次提取影片音頻",
            font=("Arial", 9)
        )
        subtitle_label.pack()
        
        # 分隔線
        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=10, pady=5)
        
        # 檔案選擇區
        self.create_file_selection_area()
        
        # 輸出設定區
        self.create_output_settings_area()
        
        # 進度區
        self.create_progress_area()
        
        # 日誌區
        self.create_log_area()
        
        # 控制按鈕區
        self.create_control_buttons()
    
    def create_file_selection_area(self):
        """創建檔案選擇區域"""
        frame = ttk.LabelFrame(self.root, text="選擇影片檔案", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 按鈕列
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        
        select_btn = ttk.Button(
            btn_frame,
            text="選擇檔案...",
            command=self.select_files
        )
        select_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        clear_btn = ttk.Button(
            btn_frame,
            text="清除列表",
            command=self.clear_list
        )
        clear_btn.pack(side=tk.LEFT)
        
        info_label = ttk.Label(
            btn_frame,
            text="支援格式: MP4, TS, AVI",
            font=("Arial", 8),
            foreground="gray"
        )
        info_label.pack(side=tk.RIGHT)
        
        # 檔案列表
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED,
            height=8
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        
        # 右鍵選單
        self.create_context_menu()
    
    def create_output_settings_area(self):
        """創建輸出設定區域"""
        frame = ttk.LabelFrame(self.root, text="輸出設定", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 輸出資料夾
        dir_frame = ttk.Frame(frame)
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(dir_frame, text="輸出資料夾:").pack(side=tk.LEFT, padx=(0, 5))
        
        dir_entry = ttk.Entry(
            dir_frame,
            textvariable=self.output_dir_var,
            width=50
        )
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_btn = ttk.Button(
            dir_frame,
            text="瀏覽...",
            command=self.select_output_dir,
            width=10
        )
        browse_btn.pack(side=tk.LEFT)
        
        # 輸出格式
        format_frame = ttk.Frame(frame)
        format_frame.pack(fill=tk.X)
        
        ttk.Label(format_frame, text="輸出格式:").pack(side=tk.LEFT, padx=(0, 10))
        
        formats = [
            ("WAV (無損高品質)", "wav"),
            ("MP3 (通用格式)", "mp3"),
            ("AAC (小檔案)", "aac")
        ]
        
        for text, value in formats:
            ttk.Radiobutton(
                format_frame,
                text=text,
                variable=self.format_var,
                value=value
            ).pack(side=tk.LEFT, padx=(0, 15))
    
    def create_progress_area(self):
        """創建進度顯示區域"""
        frame = ttk.LabelFrame(self.root, text="處理進度", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 進度標籤
        progress_label = ttk.Label(
            frame,
            textvariable=self.progress_label_var,
            font=("Arial", 9)
        )
        progress_label.pack(anchor=tk.W, pady=(0, 5))
        
        # 進度條
        self.progress_bar = ttk.Progressbar(
            frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)
    
    def create_log_area(self):
        """創建日誌顯示區域"""
        frame = ttk.LabelFrame(self.root, text="狀態日誌", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 創建文字框和滾動條
        log_frame = ttk.Frame(frame)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            state='disabled',
            font=("Consolas", 9)
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # 清除日誌按鈕
        clear_log_btn = ttk.Button(
            frame,
            text="清除日誌",
            command=self.clear_log
        )
        clear_log_btn.pack(anchor=tk.E, pady=(5, 0))
    
    def create_control_buttons(self):
        """創建控制按鈕區域"""
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # 開始按鈕
        self.start_btn = ttk.Button(
            frame,
            text="開始處理",
            command=self.start_processing,
            width=15
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 取消按鈕
        cancel_btn = ttk.Button(
            frame,
            text="關閉",
            command=self.root.quit,
            width=15
        )
        cancel_btn.pack(side=tk.LEFT)
        
        # 關於按鈕
        about_btn = ttk.Button(
            frame,
            text="關於",
            command=self.show_about,
            width=10
        )
        about_btn.pack(side=tk.RIGHT)
    
    def create_context_menu(self):
        """創建右鍵選單"""
        self.context_menu = tk.Menu(self.file_listbox, tearoff=0)
        self.context_menu.add_command(label="移除選中", command=self.remove_selected)
        self.context_menu.add_command(label="移除全部", command=self.clear_list)
        
        self.file_listbox.bind("<Button-3>", self.show_context_menu)
    
    def show_context_menu(self, event):
        """顯示右鍵選單"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def select_files(self):
        """開啟檔案選擇對話框"""
        filetypes = [
            ('影片檔案', '*.mp4 *.ts *.avi'),
            ('MP4 檔案', '*.mp4'),
            ('TS 檔案', '*.ts'),
            ('AVI 檔案', '*.avi'),
            ('所有檔案', '*.*')
        ]
        
        files = filedialog.askopenfilenames(
            title='選擇影片檔案',
            filetypes=filetypes
        )
        
        if files:
            added_count = 0
            for file in files:
                if file not in self.file_list:
                    # 驗證檔案
                    is_valid, error_msg = self.core.validate_video_file(file)
                    if is_valid:
                        self.file_list.append(file)
                        self.file_listbox.insert(tk.END, os.path.basename(file))
                        added_count += 1
                    else:
                        self.log_message(f"[WARNING] {error_msg}", 'warning')
            
            if added_count > 0:
                self.log_message(f"成功添加 {added_count} 個檔案", 'info')
    
    def select_output_dir(self):
        """開啟資料夾選擇對話框"""
        directory = filedialog.askdirectory(
            title='選擇輸出資料夾',
            initialdir=self.output_dir_var.get()
        )
        
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"輸出資料夾設定為: {directory}", 'info')
    
    def clear_list(self):
        """清除檔案列表"""
        self.file_list.clear()
        self.file_listbox.delete(0, tk.END)
        self.log_message("檔案列表已清除", 'info')
    
    def remove_selected(self):
        """移除選中的檔案"""
        selection = self.file_listbox.curselection()
        if selection:
            for index in reversed(selection):
                self.file_listbox.delete(index)
                del self.file_list[index]
            self.log_message(f"已移除 {len(selection)} 個檔案", 'info')
    
    def clear_log(self):
        """清除日誌"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
    
    def log_message(self, message, level='info'):
        """添加日誌訊息"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # 根據等級設定顏色標記
        level_prefix = {
            'info': '[INFO]',
            'success': '[OK]',
            'warning': '[WARNING]',
            'error': '[ERROR]'
        }.get(level, '[INFO]')
        
        formatted_msg = f"[{timestamp}] {level_prefix} {message}\n"
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, formatted_msg)
        self.log_text.see(tk.END)  # 自動滾動到最新
        self.log_text.config(state='disabled')
        
        # 更新 GUI
        self.root.update_idletasks()
    
    def update_progress(self, current, total):
        """更新進度條"""
        if total > 0:
            percentage = (current / total) * 100
            self.progress_var.set(percentage)
            self.progress_label_var.set(f"{percentage:.0f}% ({current}/{total})")
        else:
            self.progress_var.set(0)
            self.progress_label_var.set("0% (0/0)")
        
        self.root.update_idletasks()
    
    def check_ffmpeg(self):
        """檢查 ffmpeg 是否已安裝"""
        if self.core.check_ffmpeg_installed():
            self.log_message("ffmpeg 已安裝", 'success')
        else:
            self.log_message("警告: 未檢測到 ffmpeg", 'warning')
            messagebox.showwarning(
                "ffmpeg 未安裝",
                "未檢測到 ffmpeg。\n\n"
                "請先安裝 ffmpeg:\n"
                "- Windows: choco install ffmpeg\n"
                "- macOS: brew install ffmpeg\n"
                "- Linux: sudo apt install ffmpeg"
            )
    
    def start_processing(self):
        """開始處理"""
        # 驗證
        if not self.file_list:
            messagebox.showwarning("提示", "請先選擇要處理的影片檔案")
            return
        
        if self.is_processing:
            messagebox.showinfo("提示", "正在處理中，請稍候...")
            return
        
        # 確認處理
        response = messagebox.askyesno(
            "確認處理",
            f"即將處理 {len(self.file_list)} 個檔案\n"
            f"輸出格式: {self.format_var.get().upper()}\n"
            f"輸出資料夾: {self.output_dir_var.get()}\n\n"
            "是否繼續?"
        )
        
        if not response:
            return
        
        # 在新執行緒中處理
        self.is_processing = True
        self.start_btn.config(state='disabled', text="處理中...")
        
        thread = threading.Thread(target=self.process_in_thread, daemon=True)
        thread.start()
    
    def process_in_thread(self):
        """在子執行緒中執行處理"""
        try:
            self.log_message("="*60, 'info')
            self.log_message(f"開始批次處理 {len(self.file_list)} 個檔案", 'info')
            self.log_message(f"輸出格式: {self.format_var.get().upper()}", 'info')
            self.log_message(f"輸出資料夾: {self.output_dir_var.get()}", 'info')
            self.log_message("="*60, 'info')
            
            # 創建提取器
            extractor = self.core.VideoAudioExtractor(
                output_dir=self.output_dir_var.get(),
                audio_format=self.format_var.get()
            )
            
            # 確保輸出目錄存在
            success, error_msg = self.core.ensure_output_directory(self.output_dir_var.get())
            if not success:
                self.root.after(0, self.log_message, f"錯誤: {error_msg}", 'error')
                return
            
            # 處理每個檔案
            total = len(self.file_list)
            success_count = 0
            failed_count = 0
            
            for i, video_file in enumerate(self.file_list, 1):
                # 更新進度
                self.root.after(0, self.update_progress, i, total)
                
                # 生成輸出檔案路徑
                base_name = os.path.splitext(os.path.basename(video_file))[0]
                output_file = os.path.join(
                    self.output_dir_var.get(),
                    f"{base_name}.{self.format_var.get()}"
                )
                
                # 記錄開始處理
                self.root.after(0, self.log_message, f"處理中 [{i}/{total}]: {os.path.basename(video_file)}", 'info')
                
                # 執行提取
                success, err_msg = extractor.extract_audio(video_file, output_file, verbose=False)
                
                # 記錄結果
                if success:
                    output_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
                    msg = f"成功: {os.path.basename(output_file)} ({output_size:.2f} MB)"
                    self.root.after(0, self.log_message, msg, 'success')
                    success_count += 1
                else:
                    msg = f"失敗: {os.path.basename(video_file)} - {err_msg}"
                    self.root.after(0, self.log_message, msg, 'error')
                    failed_count += 1
            
            # 顯示摘要
            self.root.after(0, self.log_message, "="*60, 'info')
            self.root.after(0, self.log_message, "處理完成！", 'success')
            self.root.after(0, self.log_message, f"總計: {total} 個檔案", 'info')
            self.root.after(0, self.log_message, f"成功: {success_count} 個", 'success')
            self.root.after(0, self.log_message, f"失敗: {failed_count} 個", 'error' if failed_count > 0 else 'info')
            self.root.after(0, self.log_message, "="*60, 'info')
            
            # 顯示完成對話框
            if failed_count == 0:
                self.root.after(0, messagebox.showinfo, "完成", f"所有 {total} 個檔案處理成功！")
            else:
                self.root.after(0, messagebox.showwarning, "完成", 
                               f"處理完成\n成功: {success_count} 個\n失敗: {failed_count} 個")
        
        except Exception as e:
            self.root.after(0, self.log_message, f"嚴重錯誤: {str(e)}", 'error')
            self.root.after(0, messagebox.showerror, "錯誤", f"處理過程中出現錯誤:\n{str(e)}")
        
        finally:
            # 恢復按鈕狀態
            self.is_processing = False
            self.root.after(0, lambda: self.start_btn.config(state='normal', text="開始處理"))
    
    def show_about(self):
        """顯示關於對話框"""
        about_text = """
影片音頻提取工具
Video Audio Extractor

版本: 1.0.0

功能:
• 批次處理多個影片檔案
• 支援 MP4、TS、AVI 格式
• 輸出 WAV、MP3、AAC 格式
• 友善的圖形介面
• 即時進度顯示

需求:
• Python 3.6+
• ffmpeg

© 2026 Auto-generated
        """
        messagebox.showinfo("關於", about_text)


# ============================================================================
# 主程式入口
# ============================================================================

def main():
    """主程式入口"""
    root = tk.Tk()
    
    # 設定應用程式圖示（如果有的話）
    # try:
    #     root.iconbitmap('icon.ico')
    # except:
    #     pass
    
    # 創建 GUI 應用
    app = AudioExtractorGUI(root)
    
    # 添加歡迎訊息
    app.log_message("歡迎使用影片音頻提取工具！", 'success')
    app.log_message("請選擇要處理的影片檔案", 'info')
    
    # 運行主迴圈
    root.mainloop()


if __name__ == '__main__':
    main()
