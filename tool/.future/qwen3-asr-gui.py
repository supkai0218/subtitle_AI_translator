#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3 ASR 語音轉文字工具 - GUI 版本
提供圖形使用者介面，方便操作

作者: Auto-generated
版本: 1.0.0
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import importlib.util
from datetime import datetime

# 延遲載入 torch (需要 conda 環境)
torch = None
torch_cuda_available = False
try:
    import torch
    torch_cuda_available = torch.cuda.is_available()
except ImportError:
    pass

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
    core_path = os.path.join(os.path.dirname(__file__), "qwen3-asr.py")
    spec = importlib.util.spec_from_file_location("qwen3_asr", core_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ============================================================================
# GUI 主類別
# ============================================================================

class Qwen3ASRGUI:
    """Qwen3 ASR GUI 類別"""

    def __init__(self, root):
        """初始化 GUI"""
        self.root = root
        self.root.title("Qwen3 ASR 語音轉文字工具 v1.0")
        self.root.geometry("900x900")
        self.root.minsize(800, 800)

        # 載入核心模組
        try:
            self.core = load_core_module()
        except Exception as e:
            messagebox.showerror("錯誤", f"無法載入核心模組: {e}")
            sys.exit(1)

        # 初始化變數
        self.file_list = []
        self.output_dir_var = tk.StringVar(value="./output")
        self.format_var = tk.StringVar(value="txt")
        self.language_var = tk.StringVar(value="auto")
        self.model_var = tk.StringVar(value="Qwen/Qwen3-ASR-0.6B")
        self.dtype_var = tk.StringVar(value="bf16")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label_var = tk.StringVar(value="0% (0/0)")
        self.is_processing = False
        self.model_loaded = False
        self.processor = None

        # 設定配色與樣式
        self.style = ttk.Style()
        self.setup_theme()

        # 創建 UI 元件
        self.create_widgets()

        # 檢查系統環境
        self.check_environment()

    def setup_theme(self):
        """設定深色配色樣式"""
        bg_color = "#2b2b2b"
        fg_color = "#e0e0e0"
        frame_bg = "#3c3f41"
        entry_bg = "#45494a"
        btn_bg = "#4e5254"
        btn_active = "#5c6062"
        accent_color = "#3592c4"

        self.root.configure(bg=bg_color)
        self.style.theme_use('clam')

        self.style.configure(".", background=bg_color, foreground=fg_color, font=("Microsoft JhengHei", 10))
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, foreground=fg_color, relief="groove")
        self.style.configure("TLabelframe.Label", background=bg_color, foreground=accent_color, font=("Microsoft JhengHei", 11, "bold"))
        self.style.configure("TLabel", background=bg_color, foreground=fg_color)
        self.style.configure("TButton", background=btn_bg, foreground=fg_color, borderwidth=1, focuscolor=accent_color)
        self.style.map("TButton", background=[('active', btn_active), ('disabled', "#333333")])
        self.style.configure("TRadiobutton", background=bg_color, foreground=fg_color, focuscolor=bg_color)
        self.style.configure("TCombobox", fieldbackground=entry_bg, background=btn_bg, foreground=fg_color)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=fg_color, insertcolor=fg_color)
        self.style.configure("TProgressbar", thickness=15, troughcolor="#1e1e1e", background=accent_color)
        self.style.configure("Large.TButton", font=("Microsoft JhengHei", 12, "bold"), padding=10)
        self.style.configure("Action.Large.TButton", font=("Microsoft JhengHei", 14, "bold"), padding=15, background=accent_color)

    def create_widgets(self):
        """創建所有 UI 元件"""
        # 底部按鈕區
        self.bottom_frame = ttk.Frame(self.root, padding=(20, 10, 20, 20))
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.create_control_buttons(self.bottom_frame)

        # 頂部標題區
        self.top_frame = ttk.Frame(self.root, padding=(20, 20, 20, 0))
        self.top_frame.pack(side=tk.TOP, fill=tk.X)

        title_label = ttk.Label(self.top_frame, text="Qwen3 ASR 語音轉文字工具", font=("Microsoft JhengHei", 24, "bold"), foreground="#FFFFFF")
        title_label.pack()
        subtitle_label = ttk.Label(self.top_frame, text="Qwen3-ASR-0.6B 語音識別 + 字幕生成", font=("Microsoft JhengHei", 10))
        subtitle_label.pack()

        # 中間可滾動區域
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

        self.root.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # 可滾動區域內容
        self.create_model_status_area(self.scrollable_frame)
        self.create_file_selection_area(self.scrollable_frame)
        self.create_settings_area(self.scrollable_frame)

        lower_frame = ttk.Frame(self.scrollable_frame)
        lower_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.create_progress_area(lower_frame)
        self.create_log_area(lower_frame)

    def create_model_status_area(self, parent):
        """創建模型狀態區域"""
        frame = ttk.LabelFrame(parent, text=" 模型狀態 ", padding=15)
        frame.pack(fill=tk.X, pady=5)

        status_frame = ttk.Frame(frame)
        status_frame.pack(fill=tk.X)

        self.model_status_label = ttk.Label(status_frame, text="模型未載入", foreground="gray")
        self.model_status_label.pack(side=tk.LEFT)

        self.load_model_btn = ttk.Button(status_frame, text=" 載入模型 ", command=self.load_model)
        self.load_model_btn.pack(side=tk.RIGHT)

    def create_file_selection_area(self, parent):
        """創建檔案選擇區域"""
        frame = ttk.LabelFrame(parent, text=" 音頻檔案清單 ", padding=15)
        frame.pack(fill=tk.BOTH, expand=True, pady=5)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text=" 新增音頻檔案 ", command=self.select_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text=" 清除清單 ", command=self.clear_list).pack(side=tk.LEFT, padx=5)

        hint_text = "支援: WAV, MP3, M4A, FLAC, OGG, AAC" + (" (支援檔案拖曳)" if HAS_DND else "")
        ttk.Label(toolbar, text=hint_text, foreground="gray").pack(side=tk.RIGHT, padx=5)

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

        if HAS_DND:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind('<<Drop>>', self.handle_drop)

        self.create_context_menu()

    def create_settings_area(self, parent):
        """創建設定區域"""
        frame = ttk.LabelFrame(parent, text=" 輸出設定 ", padding=15)
        frame.pack(fill=tk.X, pady=5)

        # 輸出目錄
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="輸出目錄:", width=10).pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.output_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="瀏覽...", command=self.select_output_dir).pack(side=tk.LEFT)

        # 輸出格式
        format_frame = ttk.Frame(frame)
        format_frame.pack(fill=tk.X, pady=5)
        ttk.Label(format_frame, text="輸出格式:", width=10).pack(side=tk.LEFT)
        ttk.Radiobutton(format_frame, text="TXT (純文字)", variable=self.format_var, value="txt").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(format_frame, text="SRT (字幕)", variable=self.format_var, value="srt").pack(side=tk.LEFT, padx=10)

        # 語言設定
        lang_frame = ttk.Frame(frame)
        lang_frame.pack(fill=tk.X, pady=5)
        ttk.Label(lang_frame, text="語言:", width=10).pack(side=tk.LEFT)
        self.lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.language_var,
            values=["auto", "zh", "en", "ja", "ko", "es", "fr", "de"],
            state="readonly",
            width=15
        )
        self.lang_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(lang_frame, text="(auto = 自動偵測)", foreground="gray").pack(side=tk.LEFT, padx=5)

        # 模型設定
        model_frame = ttk.Frame(frame)
        model_frame.pack(fill=tk.X, pady=5)
        ttk.Label(model_frame, text="模型:", width=10).pack(side=tk.LEFT)
        model_combo = ttk.Combobox(
            model_frame,
            textvariable=self.model_var,
            values=["Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-0.6B-int4", "Qwen/Qwen3-ASR-0.6B-int8"],
            width=30
        )
        model_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(model_frame, text="(量化版本需更少 VRAM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        # 資料類型
        dtype_frame = ttk.Frame(frame)
        dtype_frame.pack(fill=tk.X, pady=5)
        ttk.Label(dtype_frame, text="精度:", width=10).pack(side=tk.LEFT)
        ttk.Radiobutton(dtype_frame, text="FP16 (省VRAM)", variable=self.dtype_var, value="fp16").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(dtype_frame, text="BF16 (推薦)", variable=self.dtype_var, value="bf16").pack(side=tk.LEFT, padx=5)

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

        self.start_btn = ttk.Button(
            btn_container,
            text=" 開始轉換 ",
            style="Action.Large.TButton",
            command=self.start_processing
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(btn_container, text=" 關閉 ", style="Large.TButton", command=self.root.quit).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_container, text=" 關於 ", style="Large.TButton", command=self.show_about).pack(side=tk.LEFT, padx=5)

    # --- 功能實作 ---

    def handle_drop(self, event):
        files = self.root.splitlist(event.data)
        added = 0
        for f in files:
            is_valid, _ = self.core.validate_audio_file(f)
            if is_valid and f not in self.file_list:
                self.file_list.append(f)
                self.file_listbox.insert(tk.END, os.path.basename(f))
                added += 1
        if added:
            self.log_message(f"拖曳加入 {added} 個檔案", 'info')

    def select_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[
                ("音頻檔案", "*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma"),
                ("所有檔案", "*.*")
            ]
        )
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
        if d:
            self.output_dir_var.set(d)

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

    def check_environment(self):
        """檢查系統環境"""
        global torch
        if torch is None:
            self.log_message("錯誤: PyTorch 未安裝", 'error')
            self.log_message("請確認已啟動 qwen_asr 環境：", 'error')
            self.log_message("  $HOME/miniconda3/Scripts/conda.exe activate qwen_asr", 'info')
            messagebox.showerror(
                "環境錯誤",
                "找不到 PyTorch。\n\n"
                "請先啟動 conda 環境：\n"
                "  $HOME/miniconda3/Scripts/conda.exe activate qwen_asr\n\n"
                "然後再執行此程式。"
            )
            return

        if torch_cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            self.log_message(f"GPU: {gpu_name}", 'success')
            self.log_message(f"VRAM: {vram:.1f} GB", 'success')
        else:
            self.log_message("警告: CUDA 不可用，將使用 CPU（非常慢）", 'warning')

        self.log_message("系統環境檢測完成", 'success')

    def load_model(self):
        """載入模型"""
        if self.is_processing:
            messagebox.showwarning("提示", "處理中無法載入模型")
            return

        self.load_model_btn.config(state='disabled', text=" 載入中... ")
        threading.Thread(target=self._load_model_task, daemon=True).start()

    def _load_model_task(self):
        """背景載入模型"""
        try:
            self.log_message("開始載入模型...", 'info')

            dtype_map = {
                'fp16': torch.float16,
                'bf16': torch.bfloat16,
            }
            dtype = dtype_map.get(self.dtype_var.get(), torch.bfloat16)
            fmt = self.format_var.get()

            # 只有使用 SRT 格式才載入 ForcedAligner
            aligner = "Qwen/Qwen3-ForcedAligner-0.6B" if fmt == "srt" else None

            self.log_message(f"模型: {self.model_var.get()}", 'info')
            self.log_message(f"精度: {self.dtype_var.get().upper()}", 'info')
            mode_text = 'SRT (需要ForcedAligner)' if aligner else 'TXT (快速模式)'
            self.log_message(f"模式: {mode_text}", 'info')

            processor = self.core.Qwen3ASRProcessor(
                model_name=self.model_var.get(),
                language=None if self.language_var.get() == "auto" else self.language_var.get(),
                dtype=dtype,
                device="cuda:0" if torch_cuda_available else "cpu",
                aligner_name=aligner
            )

            success, error_msg = processor.load_model()

            if success:
                self.processor = processor
                self.model_loaded = True
                self.root.after(0, lambda: self.model_status_label.config(text="模型已載入", foreground="green"))
                self.root.after(0, lambda: self.log_message("模型載入成功！", 'success'))
            else:
                self.root.after(0, lambda: self.model_status_label.config(text="載入失敗", foreground="red"))
                self.root.after(0, lambda: self.log_message(f"載入失敗: {error_msg}", 'error'))

        except Exception as e:
            self.root.after(0, lambda: self.model_status_label.config(text="載入失敗", foreground="red"))
            self.root.after(0, lambda: self.log_message(f"錯誤: {e}", 'error'))
        finally:
            self.root.after(0, lambda: self.load_model_btn.config(state='normal', text=" 載入模型 "))

    def start_processing(self):
        if not self.model_loaded:
            messagebox.showwarning("提示", "請先載入模型")
            return
        if not self.file_list:
            messagebox.showwarning("提示", "請先新增音頻檔案")
            return
        if self.is_processing:
            return

        self.is_processing = True
        self.start_btn.config(state='disabled', text=" 處理中... ")
        threading.Thread(target=self.process_task, daemon=True).start()

    def process_task(self):
        """背景處理任務"""
        try:
            out_dir = self.output_dir_var.get()
            fmt = self.format_var.get()
            lang = None if self.language_var.get() == "auto" else self.language_var.get()

            self.core.ensure_output_directory(out_dir)

            self.log_message("-" * 40)
            self.log_message(f"開始任務: 格式={fmt.upper()}, 語言={lang or 'auto'}", 'info')

            # 更新處理器的語言設定
            self.processor.language = lang

            total = len(self.file_list)
            for i, f in enumerate(self.file_list, 1):
                # 更新進度條（同步更新，在轉換前）
                self.update_progress(i - 1, total)
                self.log_message(f"開始轉換: {os.path.basename(f)}", 'info')

                name = os.path.basename(f)
                base_name = os.path.splitext(name)[0]
                out_file = os.path.join(out_dir, f"{base_name}.{fmt}")

                # 進度回調 - 即時更新日誌
                def progress_callback(msg, elapsed):
                    self.log_message(f"  {msg}", 'info')

                success, error_msg, _ = self.processor.transcribe(
                    audio_path=f,
                    output_path=out_file,
                    output_format=fmt,
                    return_timestamps=(fmt == "srt"),
                    progress_callback=progress_callback
                )

                # 更新進度條（轉換完成後）
                self.update_progress(i, total)

                if success:
                    self.log_message(f"完成: {name}", 'success')
                else:
                    self.log_message(f"失敗: {name} ({error_msg})", 'error')

            self.log_message("任務完成", 'success')
            self.root.after(0, lambda: messagebox.showinfo("完成", "批次處理已結束"))

        except Exception as e:
            self.log_message(f"發生錯誤: {e}", 'error')
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.start_btn.config(state='normal', text=" 開始轉換 "))
            self.root.after(0, self.update_progress, 0, 0)

    def show_about(self):
        messagebox.showinfo(
            "關於",
            "Qwen3 ASR 語音轉文字工具 v1.0\n\n"
            "- 基於 Qwen3-ASR-0.6B 模型\n"
            "- 支援 30 種語言\n"
            "- 支援批量處理\n"
            "- 可輸出 TXT 或 SRT 格式\n\n"
            "VRAM 需求:\n"
            "- BF16: ~2-3 GB\n"
            "- FP16: ~2-3 GB\n"
            "- INT8: ~1.5-2 GB\n"
            "- INT4: ~0.8-1.2 GB"
        )

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

    app = Qwen3ASRGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
