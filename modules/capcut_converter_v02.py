import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

class CapcutConverter:
    """CapCut字幕轉換器 - 快速執行版本"""
    
    def __init__(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        初始化轉換器
        
        Args:
            progress_callback: 進度回調函數，接收進度百分比和狀態訊息
        """
        self.progress_callback = progress_callback
        self.track_count = 0  # 追踪處理的軌道數
        self.segment_count = 0  # 追踪處理的字幕段落數

    def report_progress(self, percentage: int, message: str):
        """回報進度"""
        if self.progress_callback:
            self.progress_callback(percentage, message)

    def process_subtitle_content(self, content: str) -> str:
        """處理字幕內容，移除標籤和方括號"""
        try:
            content_json = json.loads(content)
            if content_json:
                return content_json.get('text', '')
        except json.JSONDecodeError:
            import re
            cleaned = re.sub(r'<.*?>', '', content)
            cleaned = re.sub(r'\[|\]', '', cleaned)
            return cleaned
        return ''

    def convert_microseconds(self, time_in_micros: int) -> str:
        """將微秒轉換為時間碼格式 (HH:MM:SS,mmm)"""
        seconds = time_in_micros // 1_000_000
        microseconds = time_in_micros % 1_000_000
        ms = microseconds // 1000
        
        minutes = seconds // 60
        hours = minutes // 60
        
        seconds = seconds % 60
        minutes = minutes % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

    def process_file(self, input_file: str, filename: str) -> Tuple[bool, str]:
        """
        處理CapCut JSON檔案並輸出文字和時間碼檔案
        
        Args:
            input_file: 輸入JSON檔案的完整路徑
            filename: 輸出檔案的基本名稱（不含副檔名）
            
        Returns:
            (success, message): 處理是否成功及相關訊息
        """
        try:
            self.report_progress(0, "開始處理CapCut字幕檔...")
            
            # 驗證輸入檔案
            input_path = Path(input_file)
            if not input_path.exists():
                return False, f"找不到輸入檔案: {input_file}"
            
            # 讀取JSON檔案
            self.report_progress(10, "讀取JSON檔案...")
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.report_progress(20, "解析JSON資料結構...")
            
            # 獲取材料和軌道資料
            materials = data.get('materials', {})
            tracks = data.get('tracks', [])
            
            # 找出所有文字軌道
            text_tracks = [track for track in tracks if track.get('type') == 'text']
            if not text_tracks:
                return False, "找不到文字軌道"
                
            self.track_count = len(text_tracks)
            self.report_progress(30, f"找到 {self.track_count} 個文字軌道")
            
            # 收集所有軌道的字幕段落
            all_segments = []
            for track in text_tracks:
                segments = track.get('segments', [])
                all_segments.extend(segments)
                self.segment_count += len(segments)

            # 根據開始時間排序
            all_segments.sort(key=lambda x: x['target_timerange']['start'])
            
            self.report_progress(40, f"處理 {self.segment_count} 個字幕段落...")
            
            # 建立輸出目錄
            output_dir = input_path.parent.parent.parent / 'txt' / '1A'
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 準備輸出檔案路徑
            text_file = output_dir / f"1A-txt_{filename}.txt"
            time_file = output_dir / f"1A-time_{filename}.txt"
            
            # 處理每個字幕段落
            subtitles = []
            processed_count = 0
            
            for segment in all_segments:
                material_id = segment['material_id']
                text_material = next((t for t in materials.get('texts', []) 
                                    if t['id'] == material_id), None)
                
                if text_material:
                    target_timerange = segment['target_timerange']
                    start_time = target_timerange['start']
                    duration = target_timerange['duration']
                    end_time = start_time + duration
                    
                    content = self.process_subtitle_content(text_material['content'])
                    
                    subtitles.append({
                        'index': len(subtitles) + 1,
                        'start': self.convert_microseconds(start_time),
                        'end': self.convert_microseconds(end_time),
                        'content': content
                    })
                    
                    processed_count += 1
                    if processed_count % 10 == 0:  # 每處理10個段落更新一次進度
                        progress = 40 + (processed_count / self.segment_count * 30)
                        self.report_progress(int(progress), 
                            f"已處理 {processed_count}/{self.segment_count} 個字幕段落...")
                    
            self.report_progress(70, "正在寫入文字檔...")
            
            # 寫入文字檔
            with open(text_file, 'w', encoding='utf-8') as f:
                for sub in subtitles:
                    f.write(f"{sub['index']}:{sub['content']}\n")
            
            self.report_progress(85, "正在寫入時間碼檔...")
            
            # 寫入時間碼檔
            with open(time_file, 'w', encoding='utf-8') as f:
                for sub in subtitles:
                    f.write(f"{sub['index']}:{sub['start']} --> {sub['end']}\n")
            
            self.report_progress(100, "處理完成")
            return True, f"成功處理 {len(subtitles)} 個字幕段落，來自 {self.track_count} 個文字軌道"
            
        except json.JSONDecodeError:
            return False, f"JSON格式錯誤: {input_file}"
        except Exception as e:
            return False, f"處理過程發生錯誤: {str(e)}"

def main():
    """
    測試用主函數
    用法範例：
    1. 將此檔案放在專案根目錄
    2. 確保已有 json/capcut/{filename}.json 檔案
    3. 執行此腳本進行測試
    """
    def print_progress(percentage, message):
        print(f"Progress {percentage}%: {message}")
    
    # 測試設定
    filename = "test"  # 不含副檔名
    input_file = f"json/capcut/{filename}.json"
    
    # 執行轉換
    converter = CapcutConverter(print_progress)
    success, message = converter.process_file(input_file, filename)
    
    # 輸出結果
    print(f"\n處理結果: {'成功' if success else '失敗'}")
    print(f"訊息: {message}")

if __name__ == "__main__":
    main()
