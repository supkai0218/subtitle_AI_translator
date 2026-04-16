#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3-ASR OpenVINO GUI (CPU 版本)
使用 QwenASRMiniTool 的 OpenVINO INT8 量化模型，CPU 推理
"""

import os
import sys
import threading
import time
from pathlib import Path

# 嘗試導入必要套件
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("[ERROR] tkinter 未安裝，請使用: pip install tkinter")
    sys.exit(1)

# 設定 stdout 編碼
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 預設路徑
DEFAULT_MODEL_DIR = Path(r"D:\Python\QwenASR\ov_models")
DEFAULT_OUTPUT_DIR = Path(r"D:\Python\Subtitle_AI_translator\temp\asr_output")

# 支援的語言
LANGUAGES = [
    "自動偵測",
    "Chinese", "English", "Japanese", "Korean", "French", "German",
    "Spanish", "Portuguese", "Russian", "Arabic", "Thai", "Vietnamese",
    "Indonesian", "Malay", "Cantonese"
]

SAMPLE_RATE = 16000


def find_qwen_asr_ov():
    """找到 QwenASR 的 OpenVINO 模型目錄"""
    candidates = [
        Path(r"D:\Python\QwenASR\ov_models"),
        Path(r"D:\Python\QwenASR\source\ov_models"),
    ]
    for p in candidates:
        if p.exists() and (p / "qwen3_asr_int8").exists():
            return p
    return None


def get_audio_files(paths):
    """取得音頻檔案列表"""
    audio_exts = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
    files = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            if p.suffix.lower() in audio_exts:
                files.append(p)
        elif p.is_dir():
            for f in p.rglob('*'):
                if f.suffix.lower() in audio_exts:
                    files.append(f)
    return files


class QwenASROpenVINOGUI:
    """Qwen3-ASR OpenVINO GUI 主類別"""

    def __init__(self, root):
        self.root = root
        self.root.title("Qwen3-ASR OpenVINO (CPU)")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # 預設值
        self.model_dir_var = tk.StringVar(value=str(DEFAULT_MODEL_DIR))
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.language_var = tk.StringVar(value="自動偵測")
        self.threads_var = tk.StringVar(value="自動")
        self.diarize_var = tk.BooleanVar(value=False)
        self.speakers_var = tk.StringVar(value="自動")

        # 處理器
        self.processor = None
        self.is_loading = False
        self.is_processing = False
        self.file_list = []

        # 建立 UI
        self.create_ui()

        # 檢查環境
        self.check_environment()

    def check_environment(self):
        """檢查必要的套件是否已安裝"""
        try:
            import openvino
            self.log_message(f"[OK] OpenVINO: {openvino.__version__}", 'success')
        except ImportError:
            self.log_message("[ERROR] OpenVINO 未安裝", 'error')
            self.log_message("請在 qwen_ov 環境中執行:", 'error')
            self.log_message("  pip install openvino onnxruntime librosa opencc-python-reimplemented", 'error')

        try:
            import onnxruntime
            self.log_message(f"[OK] ONNXRuntime: {onnxruntime.__version__}", 'success')
        except ImportError:
            self.log_message("[WARN] ONNXRuntime 未安裝", 'warn')

    def create_ui(self):
        """建立 UI"""
        # 標題
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, pady=10)
        ttk.Label(
            title_frame,
            text="Qwen3-ASR OpenVINO (CPU 版本)",
            font=("Microsoft JhengHei", 14, "bold")
        ).pack()

        # Notebook 分頁
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: 基本設定
        self.create_basic_tab(notebook)

        # Tab 2: 進階設定
        self.create_advanced_tab(notebook)

        # Tab 3: 關於
        self.create_about_tab(notebook)

        # 狀態列
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        self.status_label = ttk.Label(status_frame, text="就緒", relief=tk.SUNKEN)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def create_basic_tab(self, notebook):
        """建立基本設定分頁"""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" 基本設定 ")

        # 模型設定
        model_frame = ttk.LabelFrame(frame, text=" 模型設定 ", padding=10)
        model_frame.pack(fill=tk.X, pady=5)

        ttk.Label(model_frame, text="模型目錄:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(model_frame, textvariable=self.model_dir_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(model_frame, text="瀏覽...", command=self.browse_model_dir).grid(row=0, column=2, padx=5)

        ttk.Label(model_frame, text="輸出目錄:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(model_frame, textvariable=self.output_dir_var, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(model_frame, text="瀏覽...", command=self.browse_output_dir).grid(row=1, column=2, padx=5)

        # 語言設定
        lang_frame = ttk.LabelFrame(frame, text=" 語言設定 ", padding=10)
        lang_frame.pack(fill=tk.X, pady=5)

        ttk.Label(lang_frame, text="辨識語言:").grid(row=0, column=0, sticky=tk.W, pady=2)
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.language_var, values=LANGUAGES, width=20, state="readonly")
        lang_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(lang_frame, text="CPU 執行緒:").grid(row=1, column=0, sticky=tk.W, pady=2)
        threads_combo = ttk.Combobox(lang_frame, textvariable=self.threads_var, values=["自動", "2", "4", "6", "8", "12", "16"], width=20, state="readonly")
        threads_combo.grid(row=1, column=1, sticky=tk.W, padx=5)

        # 說話者分離
        diarize_frame = ttk.LabelFrame(frame, text=" 說話者分離 ", padding=10)
        diarize_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(diarize_frame, text="啟用說話者分離", variable=self.diarize_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(diarize_frame, text="說話者人數:").grid(row=0, column=1, sticky=tk.W, padx=20)
        speakers_combo = ttk.Combobox(diarize_frame, textvariable=self.speakers_var, values=["自動", "2", "3", "4", "5", "6", "7", "8"], width=10, state="readonly")
        speakers_combo.grid(row=0, column=2, sticky=tk.W)

        # 檔案列表
        file_frame = ttk.LabelFrame(frame, text=" 檔案列表 ", padding=10)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="新增檔案...", command=self.add_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="新增資料夾...", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清除全部", command=self.clear_files).pack(side=tk.LEFT, padx=5)

        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, yscrollcommand=scrollbar.set, height=8)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)

        # 控制按鈕
        ctrl_frame = ttk.Frame(frame)
        ctrl_frame.pack(fill=tk.X, pady=10)
        self.load_btn = ttk.Button(ctrl_frame, text=" 載入模型 ", command=self.load_model)
        self.load_btn.pack(side=tk.LEFT, padx=5)
        self.start_btn = ttk.Button(ctrl_frame, text=" 開始轉換 ", command=self.start_process, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # 日誌
        log_frame = ttk.LabelFrame(frame, text=" 日誌 ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(log_frame, height=10, yscrollcommand=log_scroll.set, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

    def create_advanced_tab(self, notebook):
        """建立進階設定分頁"""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" 進階設定 ")

        # VAD 設定
        vad_frame = ttk.LabelFrame(frame, text=" VAD 語音偵測設定 ", padding=10)
        vad_frame.pack(fill=tk.X, pady=5)

        self.vad_threshold_var = tk.StringVar(value="0.5")
        ttk.Label(vad_frame, text="偵測閾值:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(vad_frame, textvariable=self.vad_threshold_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(vad_frame, text="(0.3-0.7, 越高越嚴格)").grid(row=0, column=2, sticky=tk.W)

        self.max_group_sec_var = tk.StringVar(value="20")
        ttk.Label(vad_frame, text="最大群組秒數:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(vad_frame, textvariable=self.max_group_sec_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(vad_frame, text="(10-30秒)").grid(row=1, column=2, sticky=tk.W)

        # ASR 設定
        asr_frame = ttk.LabelFrame(frame, text=" ASR 設定 ", padding=10)
        asr_frame.pack(fill=tk.X, pady=5)

        self.max_tokens_var = tk.StringVar(value="300")
        ttk.Label(asr_frame, text="最大生成 Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(asr_frame, textvariable=self.max_tokens_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(asr_frame, text="(日文建議400)").grid(row=0, column=2, sticky=tk.W)

        self.max_chunk_sec_var = tk.StringVar(value="30")
        ttk.Label(asr_frame, text="最大音訊片段(秒):").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(asr_frame, textvariable=self.max_chunk_sec_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        # 字幕分割設定
        sub_frame = ttk.LabelFrame(frame, text=" 字幕分割設定 ", padding=10)
        sub_frame.pack(fill=tk.X, pady=5)

        self.max_chars_var = tk.StringVar(value="20")
        ttk.Label(sub_frame, text="每行最大字數:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(sub_frame, textvariable=self.max_chars_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)

        self.min_sub_sec_var = tk.StringVar(value="0.6")
        ttk.Label(sub_frame, text="最小字幕秒數:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(sub_frame, textvariable=self.min_sub_sec_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)

        self.gap_sec_var = tk.StringVar(value="0.08")
        ttk.Label(sub_frame, text="字幕間距(秒):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(sub_frame, textvariable=self.gap_sec_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)

        # 說明
        info_frame = ttk.LabelFrame(frame, text=" 說明 ", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        info_text = """
VAD (Voice Activity Detection) 語音偵測設定:
  - 偵測閾值: 控制語音偵測的靈敏度，越高越嚴格
  - 最大群組秒數: 單一語音段的最長時間

ASR 設定:
  - 最大生成 Token: 控制單次生成的最大長度
  - 最大音訊片段: 每次處理的音訊最長時間

字幕分割:
  - 每行最大字數: 影響字幕每行的長度
  - 最小字幕秒數: 每個字幕片段的最短時間
  - 字幕間距: 字幕之間的間隔時間
        """
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)

    def create_about_tab(self, notebook):
        """建立關於分頁"""
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=" 關於 ")

        about_text = """
Qwen3-ASR OpenVINO GUI
=======================

基於 Qwen3-ASR-0.6B 模型，使用 OpenVINO INT8 量化進行 CPU 推理。

特色:
  - 純 CPU 運行，無需 GPU
  - 支援 30 種語言
  - VAD 語音偵測自動分段
  - 說話者分離（需額外模型）
  - 輸出 SRT 字幕格式

模型來源: QwenASRMiniTool
https://github.com/dseditor/QwenASRMiniTool

硬體需求:
  - RAM: 6 GB 以上
  - VRAM: 0 GB (純 CPU)
        """
        ttk.Label(frame, text=about_text, justify=tk.LEFT).pack(anchor=tk.NW, pady=10)

    def browse_model_dir(self):
        """瀏覽模型目錄"""
        path = filedialog.askdirectory(title="選擇模型目錄")
        if path:
            self.model_dir_var.set(path)

    def browse_output_dir(self):
        """瀏覽輸出目錄"""
        path = filedialog.askdirectory(title="選擇輸出目錄")
        if path:
            self.output_dir_var.set(path)

    def add_files(self):
        """新增音頻檔案"""
        files = filedialog.askopenfilenames(
            title="選擇音頻檔案",
            filetypes=[
                ("音頻檔案", "*.mp3 *.wav *.flac *.m4a *.ogg *.aac *.wma"),
                ("所有檔案", "*.*")
            ]
        )
        for f in files:
            path = Path(f)
            if path not in self.file_list:
                self.file_list.append(path)
                self.file_listbox.insert(tk.END, path.name)

    def add_folder(self):
        """新增資料夾中的所有音頻檔案"""
        folder = filedialog.askdirectory(title="選擇資料夾")
        if folder:
            audio_exts = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
            for f in Path(folder).rglob('*'):
                if f.suffix.lower() in audio_exts and f not in self.file_list:
                    self.file_list.append(f)
                    self.file_listbox.insert(tk.END, f.name)

    def clear_files(self):
        """清除所有檔案"""
        self.file_list.clear()
        self.file_listbox.delete(0, tk.END)

    def log_message(self, msg, level='info'):
        """寫入日誌"""
        colors = {
            'info': '#ffffff',
            'success': '#00ff00',
            'error': '#ff6666',
            'warn': '#ffff00'
        }
        self.log_text.config(state=tk.NORMAL)
        self.log_text.tag_config(level, foreground=colors.get(level, '#ffffff'))
        self.log_text.insert(tk.END, msg + '\n', level)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def set_status(self, msg):
        """設定狀態列"""
        self.status_label.config(text=msg)

    def load_model(self):
        """載入模型（背景執行）"""
        if self.is_loading:
            return

        self.is_loading = True
        self.load_btn.config(state=tk.DISABLED, text="載入中...")
        self.log_message("開始載入模型...")
        self.set_status("載入模型中...")

        def load_thread():
            try:
                import importlib.util
                import sys

                # 動態載入 qwen3-asr-ov.py 模組
                script_dir = Path(__file__).parent.resolve()
                module_path = script_dir / "qwen3-asr-ov.py"
                module_name = "qwen3_asr_ov"

                # 將工具目錄加入 sys.path，讓 processor_numpy 可以被找到
                if str(script_dir) not in sys.path:
                    sys.path.insert(0, str(script_dir))

                spec = importlib.util.spec_from_file_location(module_name, str(module_path))
                qwen3_asr_ov = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = qwen3_asr_ov
                spec.loader.exec_module(qwen3_asr_ov)
                QwenASROpenVINO = qwen3_asr_ov.QwenASROpenVINO

                threads = self.threads_var.get()
                cpu_threads = 0 if threads == "自動" else int(threads)

                self.processor = QwenASROpenVINO(
                    model_dir=self.model_dir_var.get(),
                    cpu_threads=cpu_threads
                )
                self.processor.max_chunk_secs = int(self.max_chunk_sec_var.get())

                self.root.after(0, lambda: self.log_message("[OK] 開始編譯模型（首次約需30-60秒）...", 'info'))
                self.processor.load(device="CPU")

                self.root.after(0, lambda: self.log_message("[OK] 模型載入完成！", 'success'))
                self.root.after(0, lambda: self.set_status("就緒"))
                self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

            except Exception as e:
                import traceback
                err = str(e)
                tb = traceback.format_exc()
                self.root.after(0, lambda err=err: self.log_message(f"[ERROR] 載入失敗: {err}", 'error'))
                if 'verbose' in sys.argv:
                    self.root.after(0, lambda tb=tb: self.log_message(tb, 'error'))
            finally:
                self.root.after(0, lambda: self.set_loading(False))

        threading.Thread(target=load_thread, daemon=True).start()

    def set_loading(self, loading):
        """設定載入狀態"""
        self.is_loading = loading
        self.load_btn.config(state=tk.NORMAL if not loading else tk.DISABLED, text=" 載入模型 ")

    def start_process(self):
        """開始處理"""
        if self.is_processing or not self.processor:
            return

        if not self.file_list:
            messagebox.showwarning("警告", "請先新增音頻檔案")
            return

        self.is_processing = True
        self.start_btn.config(state=tk.DISABLED, text=" 處理中... ")
        self.log_message("-" * 50)
        self.log_message("開始處理...")

        def process_thread():
            output_dir = Path(self.output_dir_var.get())
            output_dir.mkdir(parents=True, exist_ok=True)

            lang = None if self.language_var.get() == "自動偵測" else self.language_var.get()
            total = len(self.file_list)

            for i, audio_path in enumerate(self.file_list, 1):
                self.root.after(0, lambda i=i, p=audio_path: self.log_message(f"[{i}/{total}] 處理: {p.name}", 'info'))
                self.root.after(0, lambda i=i: self.update_progress(i, total))

                output_path = output_dir / f"{audio_path.stem}.srt"

                try:
                    result = self.processor.process_file(
                        audio_path=str(audio_path),
                        output_path=str(output_path),
                        language=lang,
                        diarize=self.diarize_var.get()
                    )
                    if result:
                        self.root.after(0, lambda p=audio_path, o=output_path: self.log_message(f"[OK] 完成: {p.name} -> {o.name}", 'success'))
                    else:
                        self.root.after(0, lambda p=audio_path: self.log_message(f"[WARN] 無輸出: {p.name}", 'warn'))

                except Exception as e:
                    import traceback
                    err = str(e)
                    self.root.after(0, lambda p=audio_path, err=err: self.log_message(f"[ERROR] 失敗: {p.name} - {err}", 'error'))

            self.root.after(0, lambda: self.log_message("-" * 50))
            self.root.after(0, lambda: self.log_message("[OK] 全部處理完成！", 'success'))
            self.root.after(0, lambda: self.update_progress(0, 0))
            self.root.after(0, lambda: self.set_processing(False))

        threading.Thread(target=process_thread, daemon=True).start()

    def set_processing(self, processing):
        """設定處理狀態"""
        self.is_processing = processing
        self.start_btn.config(state=tk.NORMAL if not processing else tk.DISABLED, text=" 開始轉換 ")

    def update_progress(self, current, total):
        """更新進度"""
        if total > 0:
            p = (current / total) * 100
            self.status_label.config(text=f"處理中: {p:.0f}% ({current}/{total})")
        else:
            self.status_label.config(text="就緒")


def main():
    root = tk.Tk()
    app = QwenASROpenVINOGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
