# Version History:
# v0.4 - 新增時間碼過濾及修正功能，支援設定最大時長閾值和目標時長
# v0.3 - 快速執行版本
# v0.2 - 優化效能
# v0.1 - 初始版本

import json
import re
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Callable


class TextFilter:
    """文字過濾器類別 - v0.4 (含時間碼修正功能)"""

    def __init__(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        settings_paths: Optional[dict] = None,
        timecode_max_duration: Optional[float] = None,
        timecode_target_duration: Optional[float] = None
    ):
        """
        初始化文字過濾器

        Args:
            progress_callback: 進度回調函數，接收進度百分比和狀態訊息
            settings_paths: 從settings.json讀取的路徑配置
            timecode_max_duration: 時間碼最大時長閾值（秒），超過此值將修正
            timecode_target_duration: 時間碼修正後的目標時長（秒）
        """
        self.progress_callback = progress_callback
        self.settings_paths = settings_paths
        self.patterns = self._load_patterns()
        
        # 時間碼修正參數
        self.timecode_max_duration = timecode_max_duration
        self.timecode_target_duration = timecode_target_duration

    def report_progress(self, percentage: int, message: str):
        """回報進度"""
        if self.progress_callback:
            self.progress_callback(percentage, message)

    def _get_filter_db_path(self) -> Path:
        """依設定檔解析 1B 過濾資料庫路徑"""
        base_dir = Path(os.getcwd())
        if self.settings_paths:
            custom_path = self.settings_paths.get('filter_patterns_db')
            if custom_path:
                path = Path(custom_path)
                if not path.is_absolute():
                    path = base_dir / path
                return path
        return base_dir / 'json' / 'filter_patterns.json'

    def _load_patterns(self) -> Dict[str, List[str]]:
        """載入過濾規則"""
        filter_db_path = self._get_filter_db_path()
        try:
            # 確保資料夾存在
            filter_db_path.parent.mkdir(parents=True, exist_ok=True)

            # 讀取規則檔案
            with open(filter_db_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except FileNotFoundError:
            # 如果檔案不存在，建立預設規則到指定位置
            default_patterns = {
                "moan": [
                    r'^[あぁアァ]+$',
                    r'^[んンッ]+$',
                    r'^[いぃイィ]+$',
                    r'^[うぅウゥ]+$',
                    r'^[えぇエェ]+$',
                    r'^[おぉオォ]+$'
                ]
            }

            filter_db_path.parent.mkdir(parents=True, exist_ok=True)

            with open(filter_db_path, 'w', encoding='utf-8') as f:
                json.dump(default_patterns, f, ensure_ascii=False, indent=2)
            return default_patterns

        except json.JSONDecodeError:
            raise ValueError(f"規則資料庫檔案格式錯誤: {filter_db_path}")

    def _time_to_milliseconds(self, time_str: str) -> int:
        """
        將時間字串轉換為毫秒
        
        Args:
            time_str: 格式如 "00:01:23,456"
        
        Returns:
            總毫秒數
        """
        try:
            # 分解 HH:MM:SS,mmm
            time_part, ms_part = time_str.split(',')
            h, m, s = map(int, time_part.split(':'))
            ms = int(ms_part)
            
            total_ms = (h * 3600 + m * 60 + s) * 1000 + ms
            return total_ms
        except Exception:
            raise ValueError(f"時間字串格式錯誤: {time_str}")

    def _milliseconds_to_time(self, ms: int) -> str:
        """
        將毫秒轉換回時間字串
        
        Args:
            ms: 總毫秒數
        
        Returns:
            時間字串，格式如 "00:01:23,456"
        """
        milliseconds = ms % 1000
        total_seconds = ms // 1000
        
        seconds = total_seconds % 60
        total_minutes = total_seconds // 60
        minutes = total_minutes % 60
        hours = total_minutes // 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _parse_timecode(self, timecode_str: str) -> Tuple[int, int]:
        """
        解析時間碼字串，返回起始和結束時間（以毫秒為單位）
        
        Args:
            timecode_str: 格式如 "00:01:23,456 --> 00:01:25,789"
        
        Returns:
            (start_ms, end_ms): 起始和結束時間（毫秒）
        """
        parts = timecode_str.split('-->')
        if len(parts) != 2:
            raise ValueError(f"時間碼格式錯誤: {timecode_str}")
        
        start_str = parts[0].strip()
        end_str = parts[1].strip()
        
        start_ms = self._time_to_milliseconds(start_str)
        end_ms = self._time_to_milliseconds(end_str)
        
        return start_ms, end_ms

    def _adjust_timecode_if_needed(self, timecode_str: str) -> str:
        """
        根據設定調整時間碼（如果需要）
        
        Args:
            timecode_str: 原始時間碼字串
        
        Returns:
            調整後的時間碼字串
        """
        # 如果未啟用時間碼修正功能，直接返回
        if self.timecode_max_duration is None or self.timecode_target_duration is None:
            return timecode_str
        
        try:
            start_ms, end_ms = self._parse_timecode(timecode_str)
            duration_ms = end_ms - start_ms
            duration_sec = duration_ms / 1000.0
            
            # 檢查是否超過閾值
            if duration_sec > self.timecode_max_duration:
                # 修正結束時間
                new_end_ms = start_ms + int(self.timecode_target_duration * 1000)
                
                start_str = self._milliseconds_to_time(start_ms)
                new_end_str = self._milliseconds_to_time(new_end_ms)
                
                return f"{start_str} --> {new_end_str}"
            
            return timecode_str
            
        except Exception as e:
            # 解析失敗時返回原始值，避免中斷處理
            self.report_progress(-1, f"警告：時間碼 {timecode_str} 解析失敗，保持原值: {str(e)}")
            return timecode_str

    def process_file(self, input_file: str, filename: str) -> Tuple[bool, str]:
        """
        處理文字檔案並輸出過濾後的結果

        Args:
            input_file: 輸入文字檔案的完整路徑
            filename: 輸出檔案的基本名稱（不含副檔名）

        Returns:
            (success, message): 處理是否成功及相關訊息
        """
        try:
            self.report_progress(0, "開始處理文字過濾...")

            # 驗證輸入檔案
            input_path = Path(input_file)
            if not input_path.exists():
                return False, f"找不到輸入檔案: {input_file}"
            if not input_path.name.startswith('1A-txt_'):
                return False, f"輸入檔案名稱格式不正確: {input_path.name}"

            # 讀取時間碼檔案
            timecode_file = input_path.parent / f"1A-time_{filename}.txt"
            if not timecode_file.exists():
                return False, f"找不到對應的時間碼檔案: {timecode_file}"

            self.report_progress(20, "讀取檔案...")

            # 讀取檔案
            with open(input_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(timecode_file, 'r', encoding='utf-8') as f:
                timecodes = f.readlines()

            if len(lines) != len(timecodes):
                return False, f"字幕行數({len(lines)})與時間碼行數({len(timecodes)})不符"

            self.report_progress(40, "執行過濾...")

            # 找出需要過濾的行
            filtered_lines: Set[int] = set()
            for i, line in enumerate(lines):
                parts = line.strip().split(':', 1)
                if len(parts) != 2:
                    continue

                text = parts[1].strip()
                # 檢查每個分類的規則
                for patterns in self.patterns.values():
                    for pattern in patterns:
                        if re.search(pattern, text):
                            filtered_lines.add(i)
                            break
                    if i in filtered_lines:
                        break

            self.report_progress(60, "準備輸出...")

            # 使用設定檔的路徑或預設路徑
            if self.settings_paths and 'txt_1B' in self.settings_paths:
                output_dir = Path(self.settings_paths['txt_1B'])
                if not output_dir.is_absolute():
                    output_dir = Path(os.getcwd()) / output_dir
            else:
                # 預設路徑：主程式目錄 / txt / 1B
                output_dir = Path(os.getcwd()) / 'txt' / '1B'

            output_dir.mkdir(parents=True, exist_ok=True)

            # 準備輸出檔案
            filtered_lines_list: List[str] = []
            filtered_timecodes_list: List[str] = []
            new_line_number = 1
            adjusted_count = 0  # 記錄調整的時間碼數量

            for i, (line, timecode) in enumerate(zip(lines, timecodes)):
                if i not in filtered_lines:
                    line_parts = line.strip().split(':', 1)
                    timecode_parts = timecode.strip().split(':', 1)

                    if len(line_parts) == 2 and len(timecode_parts) == 2:
                        text = line_parts[1].strip()
                        time = timecode_parts[1].strip()
                        
                        # 套用時間碼修正
                        original_time = time
                        adjusted_time = self._adjust_timecode_if_needed(time)
                        if adjusted_time != original_time:
                            adjusted_count += 1

                        filtered_lines_list.append(f"{new_line_number}:{text}\n")
                        filtered_timecodes_list.append(f"{new_line_number}:{adjusted_time}\n")
                        new_line_number += 1

            self.report_progress(80, "寫入檔案...")

            # 寫入過濾後的文字檔
            text_output = output_dir / f"1B-txt_{filename}.txt"
            with open(text_output, 'w', encoding='utf-8') as f:
                f.writelines(filtered_lines_list)

            # 寫入過濾後的時間碼檔
            time_output = output_dir / f"1B-time_{filename}.txt"
            with open(time_output, 'w', encoding='utf-8') as f:
                f.writelines(filtered_timecodes_list)

            self.report_progress(100, "處理完成")
            
            # 構建結果訊息
            result_msg = f"成功過濾 {len(filtered_lines)} 行，剩餘 {len(filtered_lines_list)} 行"
            if self.timecode_max_duration is not None and adjusted_count > 0:
                result_msg += f"，調整 {adjusted_count} 個時間碼"
            
            return True, result_msg

        except Exception as e:
            return False, f"處理過程發生錯誤: {str(e)}"
