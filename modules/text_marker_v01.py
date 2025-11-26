import json
import re
import os
from pathlib import Path
from typing import Tuple, Optional, Callable

class SensitiveWordReplacer:
    """
    敏感詞取代器 v01
    - v01: 修改 process_files 方法以接受動態的 input_path，解決路徑寫死問題。
    """
    def __init__(self, filename: str, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        初始化 SensitiveWordReplacer。
        
        :param filename: 檔案名稱（用於決定輸出路徑）
        :param progress_callback: 進度回調函數，格式為 (progress: int, message: str) -> None
        """
        self.filename = filename  # 傳入的檔案名稱
        self.db_path = Path("json/markers_db.json")  # 資料庫路徑
        # --- 移除寫死的 self.sub_path ---
        self.output_path = Path(f"txt/1C/1C-txt_{self.filename}.txt")  # 輸出文字檔路徑
        self.progress_callback = progress_callback  # 進度回調函數

    def _update_progress(self, progress: int, message: str):
        """更新進度"""
        if self.progress_callback:
            self.progress_callback(progress, message)

    def load_sensitive_words(self) -> dict:
        """讀取敏感詞資料庫"""
        try:
            self._update_progress(10, "讀取敏感詞資料庫...")
            if not self.db_path.exists():
                raise FileNotFoundError(f"敏感詞資料庫不存在: {self.db_path}")
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            word_map = {}
            for category in data.values():
                for code, entry in category["items"].items():
                    # 確保 'jp' 鍵存在且是一個列表
                    jp_words = entry.get("jp", [])
                    if isinstance(jp_words, list):
                        for word in jp_words:
                            word_map[word] = f"[[{code}]]"
            self._update_progress(20, "敏感詞資料庫讀取完成")
            return word_map
        except Exception as e:
            raise Exception(f"無法讀取或解析敏感詞資料庫: {str(e)}")

    def load_subtitles(self, input_path: Path) -> list:
        """
        讀取字幕檔
        
        :param input_path: 要讀取的來源字幕檔路徑物件
        """
        try:
            self._update_progress(30, f"讀取字幕檔: {input_path.name}...")
            with open(input_path, "r", encoding="utf-8") as f:
                subtitles = f.readlines()
            self._update_progress(40, "字幕檔讀取完成")
            return subtitles
        except Exception as e:
            raise Exception(f"無法讀取字幕檔: {str(e)}")

    def replace_sensitive_words(self, subtitles: list, word_map: dict) -> list:
        """取代敏感詞"""
        try:
            self._update_progress(50, "開始取代敏感詞...")
            if not word_map:
                self._update_progress(70, "敏感詞字典為空，跳過取代。")
                return subtitles

            def replace_match(match):
                return word_map.get(match.group(0), match.group(0))
            
            # 建立一個安全的正規表達式模式
            pattern = re.compile("|".join(re.escape(word) for word in word_map.keys()))
            filtered_subtitles = [pattern.sub(replace_match, line) for line in subtitles]
            self._update_progress(70, "敏感詞取代完成")
            return filtered_subtitles
        except Exception as e:
            raise Exception(f"取代敏感詞時發生錯誤: {str(e)}")

    def save_subtitles(self, subtitles: list):
        """儲存取代後的字幕檔"""
        try:
            self._update_progress(80, "儲存取代後的字幕檔...")
            # 確保輸出目錄存在
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.writelines(subtitles)
            self._update_progress(90, f"字幕檔儲存完成: {self.output_path.name}")
        except Exception as e:
            raise Exception(f"無法儲存字幕檔: {str(e)}")

    def process_files(self, input_path: str) -> Tuple[bool, str]:
        """
        執行取代流程
        
        :param input_path: 來源字幕檔的完整路徑字串
        """
        try:
            self._update_progress(0, "開始處理敏感詞取代...")
            
            # --- 關鍵修正：使用傳入的 input_path ---
            source_file = Path(input_path)
            if not source_file.exists():
                return False, f"指定的輸入檔案不存在: {input_path}"

            # 讀取敏感詞資料庫
            word_map = self.load_sensitive_words()
            
            # 讀取字幕檔（傳入路徑）
            subtitles = self.load_subtitles(source_file)
            
            # 取代敏感詞
            filtered_subtitles = self.replace_sensitive_words(subtitles, word_map)
            
            # 儲存取代後的字幕檔
            self.save_subtitles(filtered_subtitles)
            
            self._update_progress(100, "處理完成")
            return True, f"處理完成，已儲存至: {self.output_path}"
        except Exception as e:
            self._update_progress(0, f"處理失敗: {str(e)}")
            return False, str(e)

