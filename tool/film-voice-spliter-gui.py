#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影片音頻分離工具 - GUI 版本
提供圖形使用者介面，方便操作

作者: Auto-generated
版本: 1.1.0
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import importlib.util
from datetime import datetime

# 嘗試載入拖曳支援
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# ============================================================================
# 載入核心功能模組
# ============================================================================

def load_core_module():
    """動態載入核心功能模組"""
    core_path = os.path.join(os.path.dirname(__file__), "film-voice-spliter.py")
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
        self.root.title("影片音頻提取工具 - Video Audio Extractor v1.1")
        self.root.geometry("850x850")
        self.root.minsize(750, 700)
        
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
        self.sample_rate_var = tk.StringVar(value="44100")
        self.bitrate_var = tk.StringVar(value="192")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label_var = tk.StringVar(value="0% (0/0)")
        self.is_processing = False
        
        # 設定配色與樣式
        self.style = ttk.Style()
        self.setup_theme()
        
        # 創建 UI 元件
        self.create_widgets()
        
        # 檢查 ffmpeg
        self.check_ffmpeg()

    def setup_theme(self):
        """設定深色配色樣式"""
        # 深色背景色定義
        bg_color = "#2b2b2b"      # 主背景
        fg_color = "#e0e0e0"      # 主文字
        frame_bg = "#3c3f41"      # 區域背景
        entry_bg = "#45494a"      # 輸入框背景
        btn_bg = "#4e5254"        # 按鈕背景
        btn_active = "#5c6062"    # 按鈕按下
        accent_color = "#3592c4"  # 強調色
        
        # 設定 root 背景
        self.root.configure(bg=bg_color)
        
        # Ttk 樣式設定
        self.style.theme_use('clam')
        
        # 通用樣式
        self.style.configure(".", background=bg_color, foreground=fg_color, font=("Microsoft JhengHei", 10))
        
        # 各種元件細節
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, foreground=fg_color, relief="groove")
        self.style.configure("TLabelframe.Label", background=bg_color, foreground=accent_color, font=("Microsoft JhengHei", 11, "bold"))
        
        self.style.configure("TLabel", background=bg_color, foreground=fg_color)
        self.style.configure("TButton", background=btn_bg, foreground=fg_color, borderwidth=1, focuscolor=accent_color)
        self.style.map("TButton", background=[('active', btn_active), ('disabled', "#333333")])
        
        self.style.configure("TRadiobutton", background=bg_color, foreground=fg_color, focuscolor=bg_color)
        self.style.map("TRadiobutton", foreground=[('selected', accent_color)])
        
        self.style.configure("TCombobox", fieldbackground=entry_bg, background=btn_bg, foreground=fg_color)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=fg_color, insertcolor=fg_color)
        
        self.style.configure("TProgressbar", thickness=15, troughcolor="#1e1e1e", background=accent_color)
        
        # 專門給下方大按鈕用的樣式
        self.style.configure("Large.TButton", font=("Microsoft JhengHei", 12, "bold"), padding=10)
        self.style.configure("Action.Large.TButton", font=("Microsoft JhengHei", 14, "bold"), padding=15, background=accent_color)

    def create_widgets(self):
        """創建所有 UI 元件，使用 Canvas 與 Scrollbar 確保內容可滾動"""
        # 1. 建立固定的底部按鈕區
        self.bottom_frame = ttk.Frame(self.root, padding=(20, 10, 20, 20))
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.create_control_buttons(self.bottom_frame)

        # 2. 建立固定的頂部標題區
        self.top_frame = ttk.Frame(self.root, padding=(20, 20, 20, 0))
        self.top_frame.pack(side=tk.TOP, fill=tk.X)
        
        title_label = ttk.Label(self.top_frame, text="影片音頻提取工具", font=("Microsoft JhengHei", 24, "bold"), foreground="#FFFFFF")
        title_label.pack()
        subtitle_label = ttk.Label(self.top_frame, text="Video Audio Extractor - 專業批次音頻提取方案", font=("Microsoft JhengHei", 10))
        subtitle_label.pack()

        # 3. 中間可滾動區域
        self.canvas = tk.Canvas(self.root, bg="#2b2b2b", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, padding=20)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 綁定滑鼠滾輪
        self.root.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # 4. 在可滾動區域中放置元件
        self.create_file_selection_area(self.scrollable_frame)
        self.create_output_settings_area(self.scrollable_frame)
        
        lower_frame = ttk.Frame(self.scrollable_frame)
        lower_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.create_progress_area(lower_frame)
        self.create_log_area(lower_frame)

        # 確保滾動區域寬度跟隨視窗
        def _on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas.find_withtag("all")[0], width=event.width)
        self.canvas.bind('<Configure>', _on_canvas_configure)

    def create_file_selection_area(self, parent):
        """創建檔案選擇區域"""
        frame = ttk.LabelFrame(parent, text=" 檔案清單 ", padding=15)
        frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 工具列
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text=" ➕ 新增檔案 ", command=self.select_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text=" 🗑️ 清除清單 ", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        
        hint_text = "支援: MP4, TS, AVI" + (" (支援檔案拖曳)" if HAS_DND else "")
        ttk.Label(toolbar, text=hint_text, foreground="gray").pack(side=tk.RIGHT, padx=5)
        
        # 清單框
        list_container = ttk.Frame(frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(
            list_container,
            bg="#1e1e1e",
            fg="#cccccc",
            selectbackground=self.style.lookup("TProgressbar", "background"),
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=1,
            highlightcolor="#444444"
        )
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 拖曳綁定
        if HAS_DND:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind('<<Drop>>', self.handle_drop)
        
        # 右鍵選單
        self.create_context_menu()

    def create_output_settings_area(self, parent):
        """創建輸出設定區域"""
        frame = ttk.LabelFrame(parent, text=" 輸出設定 ", padding=15)
        frame.pack(fill=tk.X, pady=5)
        
        # 輸出路徑
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="輸出目錄:", width=10).pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.output_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="瀏覽...", command=self.select_output_dir).pack(side=tk.LEFT)
        
        # 格式與頻率
        options_frame = ttk.Frame(frame)
        options_frame.pack(fill=tk.X, pady=10)
        
        # 左邊格式
        format_group = ttk.Frame(options_frame)
        format_group.pack(side=tk.LEFT)
        ttk.Label(format_group, text="輸出格式:", width=10).pack(side=tk.LEFT)
        for text, val in [("WAV", "wav"), ("MP3", "mp3"), ("AAC", "aac")]:
            ttk.Radiobutton(format_group, text=text, variable=self.format_var, value=val).pack(side=tk.LEFT, padx=10)
            
        # 右邊頻率
        rate_group = ttk.Frame(options_frame)
        rate_group.pack(side=tk.RIGHT)
        ttk.Label(rate_group, text="取樣頻率 (Hz):").pack(side=tk.LEFT, padx=5)
        self.rate_combo = ttk.Combobox(rate_group, textvariable=self.sample_rate_var, values=["22050", "44100", "48000", "96000"], state="readonly", width=10)
        self.rate_combo.pack(side=tk.LEFT)
        
        # 位元率設定
        bitrate_frame = ttk.Frame(frame)
        bitrate_frame.pack(fill=tk.X, pady=5)
        ttk.Label(bitrate_frame, text="位元率 (kb/秒):", width=15).pack(side=tk.LEFT)
        self.bitrate_combo = ttk.Combobox(bitrate_frame, textvariable=self.bitrate_var, values=["96", "128", "192", "256"], state="readonly", width=10)
        self.bitrate_combo.pack(side=tk.LEFT, padx=5)

    def create_progress_area(self, parent):
        """創建進度顯示區域"""
        frame = ttk.LabelFrame(parent, text=" 處理進度 ", padding=15)
        frame.pack(fill=tk.X, pady=5)
        
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(header, textvariable=self.progress_label_var, font=("Microsoft JhengHei", 9, "bold")).pack(side=tk.LEFT)
        
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X)

    def create_log_area(self, parent):
        """創建日誌區域"""
        frame = ttk.LabelFrame(parent, text=" 狀態日誌 ", padding=15)
        frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = tk.Text(frame, height=8, bg="#1e1e1e", fg="#a9b7c6", font=("Consolas", 9), borderwidth=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(state='disabled')

    def create_control_buttons(self, parent):
        """創建大按鈕"""
        btn_container = ttk.Frame(parent, padding=(0, 20, 0, 0))
        btn_container.pack(fill=tk.X, side=tk.BOTTOM)
        
        # 開始按鈕
        self.start_btn = ttk.Button(btn_container, text=" ⚡ 開始提取音頻 ", style="Action.Large.TButton", command=self.start_processing)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 工具按鈕
        ttk.Button(btn_container, text=" ❌ 關閉 ", style="Large.TButton", command=self.root.quit).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_container, text=" ℹ️ 關於 ", style="Large.TButton", command=self.show_about).pack(side=tk.LEFT, padx=5)

    # --- 功能實作 ---

    def handle_drop(self, event):
        files = self.root.splitlist(event.data)
        added = 0
        for f in files:
            is_valid, _ = self.core.validate_video_file(f)
            if is_valid and f not in self.file_list:
                self.file_list.append(f)
                self.file_listbox.insert(tk.END, os.path.basename(f))
                added += 1
        if added: self.log_message(f"拖曳加入 {added} 個檔案", 'info')

    def select_files(self):
        files = filedialog.askopenfilenames(filetypes=[("影片檔案", "*.mp4 *.ts *.avi"), ("所有檔案", "*.*")])
        if files:
            added = 0
            for f in files:
                if f not in self.file_list:
                    self.file_list.append(f)
                    self.file_listbox.insert(tk.END, os.path.basename(f))
                    added += 1
            self.log_message(f"手動加入 {added} 個檔案", 'info')

    def select_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if d: self.output_dir_var.set(d)

    def clear_list(self):
        self.file_list.clear()
        self.file_listbox.delete(0, tk.END)
        self.log_message("清單已清除", 'info')

    def log_message(self, message, level='info'):
        ts = datetime.now().strftime('%H:%M:%S')
        prefix = {'success': '[OK]', 'error': '[ERR]', 'warning': '[WRN]'}.get(level, '[INF]')
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{ts}] {prefix} {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update_idletasks()

    def update_progress(self, current, total):
        if total > 0:
            p = (current / total) * 100
            self.progress_var.set(p)
            self.progress_label_var.set(f"處理中: {p:.0f}% ({current}/{total})")
        self.root.update_idletasks()

    def check_ffmpeg(self):
        if self.core.check_ffmpeg_installed():
            self.log_message("ffmpeg 環境檢測正常", 'success')
        else:
            self.log_message("警告: 系統未偵測到 ffmpeg", 'warning')

    def start_processing(self):
        if not self.file_list:
            messagebox.showwarning("提示", "請先新增影片檔案")
            return
        if self.is_processing: return

        self.is_processing = True
        self.start_btn.config(state='disabled', text=" ⏳ 處理中... ")
        threading.Thread(target=self.process_task, daemon=True).start()

    def process_task(self):
        try:
            out_dir = self.output_dir_var.get()
            fmt = self.format_var.get()
            sr = self.sample_rate_var.get()
            br = self.bitrate_var.get()
            
            self.log_message("-" * 40)
            self.log_message(f"開始任務: 格式={fmt.upper()}, 頻率={sr}Hz, 位元率={br}k", 'info')
            
            extractor = self.core.VideoAudioExtractor(output_dir=out_dir, audio_format=fmt, sample_rate=sr, bitrate=f"{br}k")
            self.core.ensure_output_directory(out_dir)
            
            total = len(self.file_list)
            for i, f in enumerate(self.file_list, 1):
                self.root.after(0, self.update_progress, i, total)
                name = os.path.basename(f)
                out_f = os.path.join(out_dir, f"{os.path.splitext(name)[0]}.{fmt}")
                
                success, err = extractor.extract_audio(f, out_f)
                if success:
                    self.log_message(f"完成: {name}", 'success')
                else:
                    self.log_message(f"失敗: {name} ({err})", 'error')
            
            self.log_message("任務完成", 'success')
            self.root.after(0, lambda: messagebox.showinfo("完成", "批次處理已結束"))
        except Exception as e:
            self.log_message(f"發生錯誤: {e}", 'error')
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.start_btn.config(state='normal', text=" ⚡ 開始提取音頻 "))
            self.root.after(0, self.update_progress, 0, 0)

    def show_about(self):
        messagebox.showinfo("關於", "影片音頻提取工具 v1.1\n\n- 支援深色模式\n- 提供取樣頻率設定\n- 支援檔案拖拉")

    def create_context_menu(self):
        self.menu = tk.Menu(self.file_listbox, tearoff=0, bg="#333333", fg="#ffffff")
        self.menu.add_command(label="移除選取", command=self.remove_item)
        self.file_listbox.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

    def remove_item(self):
        idx = self.file_listbox.curselection()
        for i in reversed(idx):
            self.file_listbox.delete(i)
            del self.file_list[i]

# ============================================================================
# 主程式
# ============================================================================

def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = AudioExtractorGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
