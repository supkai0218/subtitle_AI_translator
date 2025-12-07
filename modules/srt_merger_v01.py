from pathlib import Path
from typing import Optional, Callable, Tuple

class SRTMerger:
    """SRT字幕合併器類別 v01"""
    
    def __init__(self, progress_callback: Optional[Callable[[int, str], None]] = None, settings_paths: Optional[dict] = None):
        """
        初始化合併器
        
        Args:
            progress_callback: 進度回調函數，接收進度百分比和狀態訊息
            settings_paths: 從settings.json讀取的路徑配置
        """
        self.progress_callback = progress_callback
        self.settings_paths = settings_paths

    def report_progress(self, percentage: int, message: str):
        """回報進度"""
        if self.progress_callback:
            self.progress_callback(percentage, message)

    def process_line(self, line: str) -> str:
        """處理字幕行，移除冒號和多餘空格"""
        if ':' in line:
            _, content = line.split(':', 1)
            return content.strip()
        return line.strip()

    def merge_files(self, filename: str, input_subtitle_file: Optional[str] = None, 
                   input_timecode_file: Optional[str] = None, 
                   output_file: Optional[str] = None) -> Tuple[bool, str]:
        """
        合併字幕和時間碼檔案
        
        Args:
            filename: 基本檔名（不含副檔名和路徑）
            input_subtitle_file: 字幕檔案路徑，若為None則使用預設路徑
            input_timecode_file: 時間碼檔案路徑，若為None則使用預設路徑
            output_file: 輸出檔案路徑，若為None則使用預設路徑
        
        Returns:
            (success, message): 處理是否成功及相關訊息
        """
        try:
            self.report_progress(0, "開始合併SRT檔案...")
            
            # 設定預設路徑，使用設定路徑或預設路徑
            base_path = Path.cwd()
            
            if not input_subtitle_file:
                if self.settings_paths and 'txt_3A' in self.settings_paths:
                    input_subtitle_file = Path(self.settings_paths['txt_3A']) / f'3A-txt_{filename}.txt'
                else:
                    # 預設路徑：主程式目錄 / txt / 3A / {filename}
                    input_subtitle_file = base_path / 'txt' / '3A' / f'3A-txt_{filename}.txt'
                    
            if not input_timecode_file:
                if self.settings_paths and 'txt_1B' in self.settings_paths:
                    input_timecode_file = Path(self.settings_paths['txt_1B']) / f'1B-time_{filename}.txt'
                else:
                    # 預設路徑：主程式目錄 / txt / 1B / {filename}
                    input_timecode_file = base_path / 'txt' / '1B' / f'1B-time_{filename}.txt'
                    
            if not output_file:
                if self.settings_paths and 'srt_output' in self.settings_paths:
                    output_file = Path(self.settings_paths['srt_output']) / f'{filename}.srt'
                else:
                    # 預設路徑：主程式目錄 / {filename}.srt
                    output_file = base_path / f'{filename}.srt'

            # 檢查輸入檔案
            subtitle_path = Path(input_subtitle_file)
            timecode_path = Path(input_timecode_file)
            
            if not subtitle_path.exists():
                return False, f"找不到字幕檔案: {input_subtitle_file}"
            if not timecode_path.exists():
                return False, f"找不到時間碼檔案: {input_timecode_file}"

            self.report_progress(20, "讀取檔案...")

            # 讀取檔案
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                subtitles = [line.strip() for line in f if line.strip()]
            with open(timecode_path, 'r', encoding='utf-8') as f:
                timecodes = [line.strip() for line in f if line.strip()]

            # 檢查行數是否相符
            if len(subtitles) != len(timecodes):
                return False, f"字幕行數({len(subtitles)})與時間碼行數({len(timecodes)})不符"

            self.report_progress(50, "處理字幕內容...")

            # 確保輸出目錄存在
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 寫入合併後的SRT檔案
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, (subtitle, timecode) in enumerate(zip(subtitles, timecodes)):
                    index = str(i + 1)
                    subtitle_text = self.process_line(subtitle)
                    timecode_text = self.process_line(timecode)
                    
                    f.write(f"{index}\n")
                    f.write(f"{timecode_text}\n")
                    f.write(f"{subtitle_text}\n\n")

            self.report_progress(100, "合併完成")
            return True, f"成功合併 {len(subtitles)} 行字幕至 {output_file}"

        except Exception as e:
            return False, f"合併過程發生錯誤: {str(e)}"