import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Callable

class TextFilter:
    """文字過濾器類別 - 快速執行版本"""
    
    def __init__(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        初始化文字過濾器
        
        Args:
            progress_callback: 進度回調函數，接收進度百分比和狀態訊息
        """
        self.progress_callback = progress_callback
        self.patterns = self._load_patterns()

    def report_progress(self, percentage: int, message: str):
        """回報進度"""
        if self.progress_callback:
            self.progress_callback(percentage, message)

    def _load_patterns(self) -> Dict[str, List[str]]:
        """載入過濾規則"""
        try:
            # 修改為使用主程式目錄下的固定路徑
            filter_db_path = Path('json/filter_patterns.json')
            
            # 確保json目錄存在
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
            
            # 寫入預設規則到指定位置
            filter_db_path = Path('json/filter_patterns.json')
            filter_db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filter_db_path, 'w', encoding='utf-8') as f:
                json.dump(default_patterns, f, ensure_ascii=False, indent=2)
            return default_patterns
            
        except json.JSONDecodeError:
            raise ValueError(f"規則資料庫檔案格式錯誤: {filter_db_path}")

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
            filtered_lines = set()
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

            # 建立輸出目錄
            output_dir = input_path.parent.parent / '1B'
            output_dir.mkdir(parents=True, exist_ok=True)

            # 準備輸出檔案
            filtered_lines_list = []
            filtered_timecodes_list = []
            new_line_number = 1

            for i, (line, timecode) in enumerate(zip(lines, timecodes)):
                if i not in filtered_lines:
                    line_parts = line.strip().split(':', 1)
                    timecode_parts = timecode.strip().split(':', 1)
                    
                    if len(line_parts) == 2 and len(timecode_parts) == 2:
                        text = line_parts[1].strip()
                        time = timecode_parts[1].strip()
                        
                        filtered_lines_list.append(f"{new_line_number}:{text}\n")
                        filtered_timecodes_list.append(f"{new_line_number}:{time}\n")
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
            return True, f"成功過濾 {len(filtered_lines)} 行，剩餘 {len(filtered_lines_list)} 行"

        except Exception as e:
            return False, f"處理過程發生錯誤: {str(e)}"
