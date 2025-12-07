import json
import random
import re
from pathlib import Path
from typing import Tuple, Optional, Callable

class MarkerReplacer:
    """標記文字取代器類別 v03"""
    
    def __init__(self, progress_callback: Optional[Callable[[int, str], None]] = None, settings_paths: Optional[dict] = None):
        """
        初始化標記取代器
        
        Args:
            progress_callback: 進度回調函數，接收進度百分比和狀態訊息
            settings_paths: 從settings.json讀取的路徑配置
        """
        self.progress_callback = progress_callback
        self.settings_paths = settings_paths
        self.db = {}

    def report_progress(self, percentage: int, message: str):
        """回報進度"""
        if self.progress_callback:
            self.progress_callback(percentage, message)

    def get_translation(self, marker: str) -> str:
        """
        從資料庫獲取標記的翻譯
        
        Args:
            marker: 標記ID (例如: "A-1")
            
        Returns:
            標記對應的翻譯文字
        """
        # 修正: 確保 self.db 有被載入
        if not self.db:
            return f"[[資料庫未載入_{marker}]]"
            
        category, item_id = marker.split('-')
        
        try:
            item = self.db[category]["items"][f"{category}-{item_id}"]
            translation = item['input_zh']  # 直接使用原意譯文
            
            if ',' in translation:
                translation = random.choice(translation.split(','))
                
            return translation
        except KeyError:
            print(f"警告: 資料庫中找不到標記 {marker}")
            return f"[[{marker}]]"

    def replace_markers(self, text: str) -> str:
        """
        替換文字中的標記
        
        Args:
            text: 包含標記的原始文字
            
        Returns:
            替換標記後的文字
        """
        pattern = r'\[\[([A-Z]-\d+)\]\]'
        
        def replace_func(match):
            marker = match.group(1)
            return self.get_translation(marker)
            
        return re.sub(pattern, replace_func, text)

    def process_file(self, filename: str, input_stage: str = '2B') -> Tuple[bool, str]:
        """
        處理標記替換
        
        Args:
            filename: 檔案名稱（不含副檔名）
            input_stage: 輸入檔案的階段 ('2B', '1C', etc.)
            
        Returns:
            (success, message): 處理是否成功及相關訊息
        """
        try:
            self.report_progress(0, "開始處理標記替換...")

            # --- 關鍵修正：動態設定檔案路徑 ---
            # 使用設定路徑或預設路徑
            base_path = Path.cwd()
            
            if self.settings_paths and 'markers_db' in self.settings_paths:
                db_path = Path(self.settings_paths['markers_db'])
            else:
                # 預設路徑：主程式目錄 / json / markers_db.json
                db_path = base_path / 'json' / 'markers_db.json'
            
            # 根據傳入的 input_stage 動態決定來源路徑
            if self.settings_paths and f'txt_{input_stage}' in self.settings_paths:
                input_dir = Path(self.settings_paths[f'txt_{input_stage}'])
            else:
                # 預設路徑：主程式目錄 / txt / {stage}
                input_dir = base_path / 'txt' / input_stage
            
            input_path = input_dir / f'{input_stage}-txt_{filename}.txt'
            
            if self.settings_paths and 'txt_3A' in self.settings_paths:
                output_dir = Path(self.settings_paths['txt_3A'])
            else:
                # 預設路徑：主程式目錄 / txt / 3A
                output_dir = base_path / 'txt' / '3A'
            
            output_file = output_dir / f'3A-txt_{filename}.txt'

            # 驗證輸入
            if not db_path.exists():
                return False, f"找不到標記資料庫: {db_path}"
            if not input_path.exists():
                return False, f"找不到輸入檔案: {input_path}"

            # 載入標記資料庫
            self.report_progress(20, "載入標記資料庫...")
            with open(db_path, 'r', encoding='utf-8') as f:
                self.db = json.load(f)

            # 讀取輸入檔案
            self.report_progress(40, f"讀取輸入檔案... ({input_path.name})")
            with open(input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 處理每一行
            self.report_progress(60, "替換標記...")
            processed_lines = []
            for line in lines:
                parts = line.strip().split(':', 1)
                if len(parts) == 2:
                    number, text = parts
                    processed_text = self.replace_markers(text.strip())
                    processed_lines.append(f"{number}:{processed_text}\n")
                else:
                    # 如果行不包含 ':', 保持原樣
                    processed_lines.append(line)

            # 確保輸出目錄存在
            output_dir.mkdir(parents=True, exist_ok=True)

            # 寫入輸出檔案
            self.report_progress(80, "寫入輸出檔案...")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.writelines(processed_lines)

            self.report_progress(100, "標記替換完成")
            return True, f"成功處理 {len(processed_lines)} 行文字"

        except json.JSONDecodeError:
            return False, f"標記資料庫格式錯誤: {db_path}"
        except Exception as e:
            return False, f"處理過程發生錯誤: {str(e)}"