#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影片音頻分離工具
支援批次處理影片檔案並提取音頻

作者: Auto-generated
版本: 1.0.0
支援格式:
    輸入: .ts, .mp4, .avi
    輸出: .wav, .aac, .mp3
"""

import os
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

# ============================================================================
# 常數定義
# ============================================================================

SUPPORTED_VIDEO_FORMATS = ['.ts', '.mp4', '.avi']
SUPPORTED_AUDIO_FORMATS = ['.wav', '.aac', '.mp3']

# FFmpeg 命令參數映射
FFMPEG_COMMANDS = {
    'wav': ['-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2'],
    'aac': ['-vn', '-acodec', 'aac', '-ab', '192k'],
    'mp3': ['-vn', '-acodec', 'libmp3lame', '-ab', '192k']
}


# ============================================================================
# 工具函數
# ============================================================================

def check_ffmpeg_installed() -> bool:
    """
    檢查 ffmpeg 是否已安裝
    
    Returns:
        bool: True 表示已安裝，False 表示未安裝
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def validate_video_file(file_path: str) -> Tuple[bool, str]:
    """
    驗證影片檔案是否有效
    
    Args:
        file_path: 檔案路徑
    
    Returns:
        Tuple[bool, str]: (是否有效, 錯誤訊息)
    """
    # 檢查檔案是否存在
    if not os.path.exists(file_path):
        return False, f"檔案不存在: {file_path}"
    
    # 檢查是否為檔案
    if not os.path.isfile(file_path):
        return False, f"路徑不是檔案: {file_path}"
    
    # 檢查檔案格式
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_FORMATS:
        return False, f"不支援的格式: {ext} (支援: {', '.join(SUPPORTED_VIDEO_FORMATS)})"
    
    return True, ""


def validate_output_format(format_str: str) -> bool:
    """
    驗證音頻格式是否支援
    
    Args:
        format_str: 格式字串（如 'mp3' 或 '.mp3'）
    
    Returns:
        bool: True 表示支援，False 表示不支援
    """
    format_ext = f".{format_str.lower()}" if not format_str.startswith('.') else format_str.lower()
    return format_ext in SUPPORTED_AUDIO_FORMATS


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


def get_ffmpeg_command(input_file: str, output_file: str, audio_format: str) -> List[str]:
    """
    生成 ffmpeg 命令
    
    Args:
        input_file: 輸入檔案路徑
        output_file: 輸出檔案路徑
        audio_format: 音頻格式（wav/aac/mp3）
    
    Returns:
        List[str]: 完整的 ffmpeg 命令列表
    """
    base_cmd = ['ffmpeg', '-i', input_file]
    format_args = FFMPEG_COMMANDS.get(audio_format, FFMPEG_COMMANDS['mp3'])
    return base_cmd + format_args + ['-y', output_file]


# ============================================================================
# 核心類別
# ============================================================================

class VideoAudioExtractor:
    """影片音頻提取器類別"""
    
    def __init__(self, output_dir: str, audio_format: str = 'mp3'):
        """
        初始化提取器
        
        Args:
            output_dir: 輸出資料夾路徑
            audio_format: 音頻格式 (wav/aac/mp3)
        """
        self.output_dir = output_dir
        self.audio_format = audio_format.lower()
        self.file_list: List[str] = []
        self.results: Dict[str, List[str]] = {'success': [], 'failed': []}
        
        # 驗證音頻格式
        if not validate_output_format(self.audio_format):
            raise ValueError(f"不支援的音頻格式: {audio_format}")
    
    def add_file(self, file_path: str) -> bool:
        """
        添加單一檔案到處理列表
        
        Args:
            file_path: 檔案路徑
        
        Returns:
            bool: True 表示成功添加，False 表示驗證失敗
        """
        is_valid, error_msg = validate_video_file(file_path)
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
    
    def extract_audio(self, video_path: str, output_path: str, verbose: bool = False) -> Tuple[bool, str]:
        """
        提取音頻核心功能
        
        Args:
            video_path: 影片檔案路徑
            output_path: 輸出音頻檔案路徑
            verbose: 是否顯示詳細資訊
        
        Returns:
            Tuple[bool, str]: (是否成功, 錯誤訊息)
        """
        try:
            # 生成 ffmpeg 命令
            cmd = get_ffmpeg_command(video_path, output_path, self.audio_format)
            
            if verbose:
                print(f"  執行命令: {' '.join(cmd)}")
            
            # 執行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分鐘超時
            )
            
            # 檢查執行結果
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "未知錯誤"
                return False, f"ffmpeg 執行失敗: {error_msg}"
            
            # 檢查輸出檔案是否成功創建
            if not os.path.exists(output_path):
                return False, "輸出檔案未生成"
            
            return True, ""
            
        except subprocess.TimeoutExpired:
            return False, "處理超時（超過 10 分鐘）"
        except Exception as e:
            return False, f"未預期的錯誤: {str(e)}"
    
    def process_all(self, verbose: bool = False) -> Dict[str, List[str]]:
        """
        批次處理所有檔案
        
        Args:
            verbose: 是否顯示詳細資訊
        
        Returns:
            Dict[str, List[str]]: 包含成功和失敗檔案列表的字典
        """
        total = len(self.file_list)
        
        if total == 0:
            print("[WARNING] 沒有要處理的檔案")
            return self.results
        
        # 確保輸出目錄存在
        success, error_msg = ensure_output_directory(self.output_dir)
        if not success:
            print(f"[ERROR] {error_msg}")
            return self.results
        
        # 顯示處理開始訊息
        print(f"\n{'=' * 70}")
        print(f"開始批次處理 {total} 個檔案")
        print(f"輸出格式: {self.audio_format.upper()}")
        print(f"輸出目錄: {os.path.abspath(self.output_dir)}")
        print(f"{'=' * 70}\n")
        
        # 遍歷處理每個檔案
        for idx, video_file in enumerate(self.file_list, 1):
            # 生成輸出檔案路徑
            base_name = os.path.splitext(os.path.basename(video_file))[0]
            output_file = os.path.join(
                self.output_dir,
                f"{base_name}.{self.audio_format}"
            )
            
            # 顯示進度
            print(f"[{idx}/{total}] 處理: {os.path.basename(video_file)}")
            
            if verbose:
                file_size = os.path.getsize(video_file) / (1024 * 1024)  # MB
                print(f"  檔案大小: {file_size:.2f} MB")
                print(f"  輸出路徑: {output_file}")
            
            # 執行提取
            success, error_msg = self.extract_audio(video_file, output_file, verbose)
            
            # 記錄結果
            if success:
                output_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
                print(f"[OK] 成功: {os.path.basename(output_file)} ({output_size:.2f} MB)")
                self.results['success'].append(video_file)
            else:
                print(f"[FAIL] 失敗: {error_msg}")
                self.results['failed'].append(video_file)
            
            print()  # 空行分隔
        
        # 顯示處理摘要
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
        description='影片音頻提取工具 - 批次處理影片並提取音頻',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  %(prog)s video1.mp4 video2.ts -o ./output -f mp3
  %(prog)s *.mp4 -o ./audio_files -f wav
  %(prog)s input.ts -o ./output -f aac -v

支援格式:
  輸入: .ts, .mp4, .avi
  輸出: .wav, .aac, .mp3
        """
    )
    
    parser.add_argument(
        'input_files',
        nargs='+',
        help='輸入影片檔案路徑（支援 ts, mp4, avi）'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='./output',
        help='輸出資料夾路徑（預設: ./output）'
    )
    
    parser.add_argument(
        '-f', '--format',
        choices=['wav', 'aac', 'mp3'],
        default='mp3',
        help='輸出音頻格式（預設: mp3）'
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
    ║          影片音頻提取工具 Video Audio Extractor          ║
    ║                      Version 1.0.0                         ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # 解析命令列參數
    args = parse_arguments()
    
    # 檢查 ffmpeg 是否已安裝
    print("檢查 ffmpeg...")
    if not check_ffmpeg_installed():
        print("[ERROR] 錯誤: 未安裝 ffmpeg")
        print("\n請先安裝 ffmpeg:")
        print("  Windows: choco install ffmpeg")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   sudo apt install ffmpeg")
        return 1
    print("[OK] ffmpeg 已安裝\n")
    
    try:
        # 創建提取器實例
        extractor = VideoAudioExtractor(
            output_dir=args.output,
            audio_format=args.format
        )
        
        # 添加檔案到處理列表
        print("驗證輸入檔案...")
        valid_count = extractor.add_files(args.input_files)
        
        if valid_count == 0:
            print("[ERROR] 錯誤: 沒有有效的影片檔案可處理")
            return 1
        
        print(f"[OK] 找到 {valid_count} 個有效的影片檔案")
        
        # 執行批次處理
        results = extractor.process_all(verbose=args.verbose)
        
        # 返回狀態碼（如果有失敗則返回 1）
        return 0 if len(results['failed']) == 0 else 1
    
    except ValueError as e:
        print(f"[ERROR] 錯誤: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\n[WARNING] 使用者中斷處理")
        return 1
    except Exception as e:
        print(f"[ERROR] 未預期的錯誤: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
