#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3 ASR 語音轉文字工具
支援音頻檔案轉換為文字/字幕

作者: Auto-generated
版本: 1.0.0
支援輸入: .wav, .mp3, .m4a, .flac, .ogg, .aac
支援輸出: .txt (純文字), .srt (字幕格式)
"""

import os
import sys
import argparse
import torch
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# ============================================================================
# 常數定義
# ============================================================================

SUPPORTED_AUDIO_FORMATS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.wma']
SUPPORTED_OUTPUT_FORMATS = ['txt', 'srt']

DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"
DEFAULT_LANGUAGE = None  # None = auto detect

# 語言代碼映射到完整名稱
LANGUAGE_CODE_MAP = {
    'ja': 'Japanese',
    'jp': 'Japanese',
    'zh': 'Chinese',
    'en': 'English',
    'ko': 'Korean',
    'th': 'Thai',
    'vi': 'Vietnamese',
    'id': 'Indonesian',
    'ms': 'Malay',
    'tl': 'Filipino',
    'ar': 'Arabic',
    'de': 'German',
    'fr': 'French',
    'es': 'Spanish',
    'pt': 'Portuguese',
    'it': 'Italian',
    'ru': 'Russian',
    'tr': 'Turkish',
    'hi': 'Hindi',
    'nl': 'Dutch',
    'sv': 'Swedish',
    'da': 'Danish',
    'fi': 'Finnish',
    'pl': 'Polish',
    'cs': 'Czech',
    'fa': 'Persian',
    'el': 'Greek',
    'ro': 'Romanian',
    'hu': 'Hungarian',
    'mk': 'Macedonian',
    'yue': 'Cantonese',
    'cn': 'Chinese',
}

# ============================================================================
# 工具函數
# ============================================================================

def check_cuda_available() -> bool:
    """檢查 CUDA 是否可用"""
    return torch.cuda.is_available()


def check_model_installed() -> bool:
    """檢查 qwen-asr 是否已安裝"""
    try:
        import qwen_asr
        return True
    except ImportError:
        return False


def validate_audio_file(file_path: str) -> Tuple[bool, str]:
    """
    驗證音頻檔案是否有效

    Args:
        file_path: 檔案路徑

    Returns:
        Tuple[bool, str]: (是否有效, 錯誤訊息)
    """
    if not os.path.exists(file_path):
        return False, f"檔案不存在: {file_path}"

    if not os.path.isfile(file_path):
        return False, f"路徑不是檔案: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_AUDIO_FORMATS:
        return False, f"不支援的格式: {ext} (支援: {', '.join(SUPPORTED_AUDIO_FORMATS)})"

    return True, ""


def ensure_output_directory(dir_path: str) -> Tuple[bool, str]:
    """
    確保輸出目錄存在

    Args:
        dir_path: 目錄路徑

    Returns:
        Tuple[bool, str]: (是否成功, 錯誤訊息)
    """
    try:
        os.makedirs(dir_path, exist_ok=True)
        return True, ""
    except Exception as e:
        return False, f"無法創建輸出目錄: {e}"


def format_timestamp(seconds: float) -> str:
    """
    將秒數轉換為 SRT 時間格式 (HH:MM:SS,mmm)

    Args:
        seconds: 秒數

    Returns:
        str: SRT 時間格式字串
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(transcription_result: dict, output_path: str) -> Tuple[bool, str]:
    """
    將轉換結果生成 SRT 字幕檔

    Args:
        transcription_result: 轉換結果字典
        output_path: 輸出檔案路徑

    Returns:
        Tuple[bool, str]: (是否成功, 錯誤訊息)
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # 檢查是否有時間戳資訊
            if 'segments' in transcription_result:
                for idx, segment in enumerate(transcription_result['segments'], 1):
                    start = segment.get('start', 0)
                    end = segment.get('end', 0)
                    text = segment.get('text', '').strip()

                    if text:
                        f.write(f"{idx}\n")
                        f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
                        f.write(f"{text}\n\n")
            else:
                # 只有文字，沒有時間戳
                text = transcription_result.get('text', '')
                f.write(text)

        return True, ""
    except Exception as e:
        return False, f"生成 SRT 失敗: {e}"


# ============================================================================
# 核心類別
# ============================================================================

class Qwen3ASRProcessor:
    """Qwen3 ASR 處理器類別"""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        language: Optional[str] = DEFAULT_LANGUAGE,
        dtype: torch.dtype = torch.bfloat16,
        device: str = "cuda:0",
        aligner_name: Optional[str] = None
    ):
        """
        初始化 ASR 處理器

        Args:
            model_name: 模型名稱或本地路徑
            language: 語言（None = 自動偵測）
            dtype: 資料類型 (bfloat16/float16/float32)
            device: 設備 (cuda:0/cpu)
            aligner_name: Forced Aligner 模型名稱 (None = 不使用時間戳)
        """
        self.model_name = model_name
        self.language = language
        self.dtype = dtype
        self.device = device
        self.aligner_name = aligner_name
        self.model = None
        self.file_list: List[str] = []
        self.results: Dict[str, List[str]] = {'success': [], 'failed': []}

    def load_model(self) -> Tuple[bool, str]:
        """
        載入模型

        Returns:
            Tuple[bool, str]: (是否成功, 錯誤訊息)
        """
        try:
            from qwen_asr import Qwen3ASRModel

            print(f"正在載入模型: {self.model_name}")
            print(f"資料類型: {self.dtype}")
            print(f"設備: {self.device}")

            self.model = Qwen3ASRModel.from_pretrained(
                self.model_name,
                dtype=self.dtype,
                device_map=self.device,
                max_inference_batch_size=1,
                max_new_tokens=256,
                forced_aligner=self.aligner_name,
            )

            print("[OK] 模型載入成功")
            return True, ""

        except ImportError:
            return False, "請先安裝 qwen-asr: pip install qwen-asr"
        except Exception as e:
            return False, f"模型載入失敗: {e}"

    def add_file(self, file_path: str) -> bool:
        """
        添加單一檔案到處理列表

        Args:
            file_path: 檔案路徑

        Returns:
            bool: True 表示成功添加，False 表示驗證失敗
        """
        is_valid, error_msg = validate_audio_file(file_path)
        if not is_valid:
            print(f"[WARNING] {error_msg}")
            return False

        self.file_list.append(file_path)
        return True

    def add_files(self, file_paths: List[str]) -> int:
        """
        添加多個檔案到處理列表

        Args:
            file_paths: 檔案路徑列表

        Returns:
            int: 成功添加的檔案數量
        """
        count = 0
        for file_path in file_paths:
            if self.add_file(file_path):
                count += 1
        return count

    def transcribe(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        output_format: str = "txt",
        return_timestamps: bool = False,
        progress_callback=None
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        轉換單一音頻檔案

        Args:
            audio_path: 音頻檔案路徑
            output_path: 輸出檔案路徑（None = 不輸出檔案）
            output_format: 輸出格式 (txt/srt)
            return_timestamps: 是否回傳時間戳資訊
            progress_callback: 進度回調函數 (current_text, elapsed_seconds)

        Returns:
            Tuple[bool, str, Optional[dict]]: (是否成功, 錯誤訊息, 結果字典)
        """
        if self.model is None:
            return False, "模型未載入", None

        import sys
        import time

        try:
            start_time = time.time()
            elapsed = 0

            print(f"  開始轉換: {os.path.basename(audio_path)}")
            print(f"  [時間: {elapsed:.1f}s] 載入音頻資料...")
            sys.stdout.flush()

            if progress_callback:
                progress_callback(f"[{elapsed:.1f}s] 載入音頻資料...", elapsed)

            # 轉換語言代碼為完整名稱
            lang = self.language
            if lang is not None and lang.lower() in LANGUAGE_CODE_MAP:
                lang = LANGUAGE_CODE_MAP[lang.lower()]

            print(f"  [時間: {elapsed:.1f}s] 開始 ASR 推論...")
            sys.stdout.flush()
            if progress_callback:
                progress_callback(f"[{elapsed:.1f}s] 開始 ASR 推論...", elapsed)

            # 執行轉換
            result = self.model.transcribe(
                audio=audio_path,
                language=lang,
                return_time_stamps=return_timestamps
            )

            elapsed = time.time() - start_time
            print(f"  [時間: {elapsed:.1f}s] ASR 推論完成")
            sys.stdout.flush()

            # 顯示轉換結果文字
            text = result.get('text', '')
            if text:
                # 截斷過長的文字
                display_text = text[:300] + "..." if len(text) > 300 else text
                print(f"  [時間: {elapsed:.1f}s] 辨識文字: {display_text}")
            else:
                print(f"  [時間: {elapsed:.1f}s] 無辨識文字")
            sys.stdout.flush()

            if progress_callback:
                progress_callback(f"[{elapsed:.1f}s] {text[:100]}...", elapsed)

            # 如果需要輸出檔案
            if output_path:
                success, error_msg = self._save_result(result, output_path, output_format)
                if not success:
                    return False, error_msg, result
                print(f"  [時間: {elapsed:.1f}s] 已儲存: {output_path}")
            sys.stdout.flush()

            elapsed = time.time() - start_time
            print(f"  [時間: {elapsed:.1f}s] 轉換完成!")
            sys.stdout.flush()

            return True, "", result

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"  [時間: {elapsed:.1f}s] 轉換失敗: {e}")
            sys.stdout.flush()
            return False, f"轉換失敗: {e}", None

    def _save_result(
        self,
        result: dict,
        output_path: str,
        output_format: str
    ) -> Tuple[bool, str]:
        """儲存結果到檔案"""
        try:
            if output_format == "srt":
                return generate_srt(result, output_path)
            else:
                # 純文字格式
                text = result.get('text', '')
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                return True, ""
        except Exception as e:
            return False, f"儲存失敗: {e}"

    def process_all(
        self,
        output_dir: str,
        output_format: str = "txt",
        verbose: bool = False
    ) -> Dict[str, List[str]]:
        """
        批次處理所有檔案

        Args:
            output_dir: 輸出目錄
            output_format: 輸出格式 (txt/srt)
            verbose: 是否顯示詳細資訊

        Returns:
            Dict[str, List[str]]: 處理結果
        """
        total = len(self.file_list)

        if total == 0:
            print("[WARNING] 沒有要處理的檔案")
            return self.results

        # 確保輸出目錄存在
        success, error_msg = ensure_output_directory(output_dir)
        if not success:
            print(f"[ERROR] {error_msg}")
            return self.results

        # 顯示處理開始訊息
        print(f"\n{'=' * 70}")
        print(f"開始批次處理 {total} 個檔案")
        print(f"模型: {self.model_name}")
        print(f"語言: {self.language or '自動偵測'}")
        print(f"輸出格式: {output_format.upper()}")
        print(f"輸出目錄: {os.path.abspath(output_dir)}")
        print(f"{'=' * 70}\n")

        # 遍歷處理每個檔案
        for idx, audio_file in enumerate(self.file_list, 1):
            base_name = os.path.splitext(os.path.basename(audio_file))[0]
            output_file = os.path.join(
                output_dir,
                f"{base_name}.{output_format}"
            )

            print(f"[{idx}/{total}] 處理: {os.path.basename(audio_file)}")

            if verbose:
                file_size = os.path.getsize(audio_file) / (1024 * 1024)
                print(f"  檔案大小: {file_size:.2f} MB")
                print(f"  輸出路徑: {output_file}")

            success, error_msg, _ = self.transcribe(
                audio_path=audio_file,
                output_path=output_file,
                output_format=output_format
            )

            if success:
                output_size = os.path.getsize(output_file) / (1024 * 1024)
                print(f"[OK] 成功: {os.path.basename(output_file)} ({output_size:.2f} MB)")
                self.results['success'].append(audio_file)
            else:
                print(f"[FAIL] 失敗: {error_msg}")
                self.results['failed'].append(audio_file)

            print()

        self._print_summary()
        return self.results

    def _print_summary(self):
        """輸出處理摘要"""
        success_count = len(self.results['success'])
        failed_count = len(self.results['failed'])
        total_count = success_count + failed_count

        print(f"{'=' * 70}")
        print(f"處理完成！")
        print(f"{'=' * 70}")
        print(f"總計: {total_count} 個檔案")
        print(f"[OK] 成功: {success_count} 個")
        print(f"[FAIL] 失敗: {failed_count} 個")

        if failed_count > 0:
            print(f"\n失敗的檔案:")
            for file_path in self.results['failed']:
                print(f"  - {os.path.basename(file_path)}")

        print(f"{'=' * 70}\n")


# ============================================================================
# 命令列介面
# ============================================================================

def parse_arguments():
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description='Qwen3 ASR 語音轉文字工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  %(prog)s audio1.wav audio2.mp3 -o ./output
  %(prog)s *.wav -o ./subtitle -f srt
  %(prog)s audio.mp3 -o ./output -l zh --dtype int8

支援格式:
  輸入: .wav, .mp3, .m4a, .flac, .ogg, .aac, .wma
  輸出: .txt (純文字), .srt (字幕格式)
        """
    )

    parser.add_argument(
        'input_files',
        nargs='+',
        help='輸入音頻檔案路徑'
    )

    parser.add_argument(
        '-o', '--output',
        default='./output',
        help='輸出資料夾路徑（預設: ./output）'
    )

    parser.add_argument(
        '-f', '--format',
        choices=['txt', 'srt'],
        default='txt',
        help='輸出格式（預設: txt）'
    )

    parser.add_argument(
        '-l', '--language',
        default=None,
        help='指定語言（如: zh, en, ja, auto=自動偵測）'
    )

    parser.add_argument(
        '-m', '--model',
        default=DEFAULT_MODEL,
        help=f'模型名稱（預設: {DEFAULT_MODEL}）'
    )

    parser.add_argument(
        '-d', '--dtype',
        choices=['bf16', 'fp16', 'fp32'],
        default='bf16',
        help='資料類型（預設: bf16, 4GB VRAM 建議用 bf16）'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='顯示詳細處理資訊'
    )

    return parser.parse_args()


def main():
    """主程式入口"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║              Qwen3 ASR 語音轉文字工具                    ║
    ║                      Version 1.0.0                         ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    # 解析命令列參數
    args = parse_arguments()

    # 檢查 CUDA
    print("檢查系統環境...")
    if not check_cuda_available():
        print("[WARNING] CUDA 不可用，將使用 CPU（非常慢）")
        device = "cpu"
    else:
        device = "cuda:0"
        print(f"[OK] CUDA 可用: {torch.cuda.get_device_name(0)}")
        print(f"[OK] VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 檢查 qwen-asr
    if not check_model_installed():
        print("[ERROR] 錯誤: qwen-asr 未安裝")
        print("\n請先安裝 qwen-asr:")
        print("  pip install qwen-asr")
        print("\n或使用 conda 環境:")
        print("  conda activate qwen_asr")
        return 1
    print("[OK] qwen-asr 已安裝\n")

    # 轉換 dtype
    dtype_map = {
        'bf16': torch.bfloat16,
        'fp16': torch.float16,
        'fp32': torch.float32
    }
    dtype = dtype_map.get(args.dtype, torch.bfloat16)

    try:
        # 創建處理器實例
        processor = Qwen3ASRProcessor(
            model_name=args.model,
            language=args.language,
            dtype=dtype,
            device=device
        )

        # 載入模型
        success, error_msg = processor.load_model()
        if not success:
            print(f"[ERROR] {error_msg}")
            return 1

        # 添加檔案
        print("\n驗證輸入檔案...")
        valid_count = processor.add_files(args.input_files)

        if valid_count == 0:
            print("[ERROR] 錯誤: 沒有有效的音頻檔案可處理")
            return 1

        print(f"[OK] 找到 {valid_count} 個有效的音頻檔案")

        # 執行處理
        results = processor.process_all(
            output_dir=args.output,
            output_format=args.format,
            verbose=args.verbose
        )

        return 0 if len(results['failed']) == 0 else 1

    except KeyboardInterrupt:
        print("\n\n[WARNING] 使用者中斷處理")
        return 1
    except Exception as e:
        print(f"[ERROR] 未預期的錯誤: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
