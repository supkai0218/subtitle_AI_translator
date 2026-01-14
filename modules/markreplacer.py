#v04 標記文字取代器 改進版，修正路徑處理

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

    def debug_log(self, message: str):
        """統一的偵錯輸出，若無回呼則退回 print"""
        if self.progress_callback:
            try:
                self.progress_callback(-1, f"[MarkReplacer偵錯] {message}")
            except Exception:
                print(f"[MarkReplacer偵錯] {message}")
        else:
            print(f"[MarkReplacer偵錯] {message}")

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
            self.debug_log(f"警告: 嘗試取得標記 {marker} 但資料庫未載入")
            return f"[[資料庫未載入_{marker}]]"
            
        category, item_id = marker.split('-')
        
        try:
            item = self.db[category]["items"][f"{category}-{item_id}"]
            translation = item['input_zh']  # 直接使用原意譯文
            
            if ',' in translation:
                translation = random.choice(translation.split(','))
            
            # 診斷：記錄成功的替換（限制輸出數量）
            if not hasattr(self, '_translation_log_count'):
                self._translation_log_count = 0
            if self._translation_log_count < 3:
                self.debug_log(f"標記 [[{marker}]] -> {translation}")
                self._translation_log_count += 1
                
            return translation
        except KeyError as e:
            self.debug_log(f"警告: 資料庫中找不到標記 {marker}，KeyError: {e}")
            self.debug_log(f"  可用類別: {list(self.db.keys())}")
            if category in self.db:
                available_items = list(self.db[category].get("items", {}).keys())[:5]
                self.debug_log(f"  類別 {category} 中的項目範例: {available_items}")
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
            settings_repr = self.settings_paths if self.settings_paths else 'None'
            self.debug_log(f"process_file() 收到 settings_paths={settings_repr}")
            
            if self.settings_paths and 'markers_db' in self.settings_paths:
                db_path = Path(self.settings_paths['markers_db'])
                self.debug_log(f"markers_db 使用 settings 路徑: {db_path}")
            else:
                # 預設路徑：主程式目錄 / json / markers_db.json
                db_path = base_path / 'json' / 'markers_db.json'
                self.debug_log(f"markers_db 回退到預設路徑: {db_path}")
            
            # 根據傳入的 input_stage 動態決定來源路徑
            if self.settings_paths and f'txt_{input_stage}' in self.settings_paths:
                input_dir = Path(self.settings_paths[f'txt_{input_stage}'])
                self.debug_log(f"輸入資料夾使用 settings 路徑: {input_dir}")
            else:
                # 預設路徑：主程式目錄 / txt / {stage}
                input_dir = base_path / 'txt' / input_stage
                self.debug_log(f"輸入資料夾回退到預設路徑: {input_dir}")
            
            input_path = input_dir / f'{input_stage}-txt_{filename}.txt'
            self.debug_log(f"完整輸入檔案路徑: {input_path}")
            
            if self.settings_paths and 'txt_3A' in self.settings_paths:
                output_dir = Path(self.settings_paths['txt_3A'])
                self.debug_log(f"輸出資料夾使用 settings 路徑: {output_dir}")
            else:
                # 預設路徑：主程式目錄 / txt / 3A
                output_dir = base_path / 'txt' / '3A'
                self.debug_log(f"輸出資料夾回退到預設路徑: {output_dir}")
            
            output_file = output_dir / f'3A-txt_{filename}.txt'
            self.debug_log(f"完整輸出檔案路徑: {output_file}")

            # 驗證輸入
            if not db_path.exists():
                self.debug_log(f"markers_db 不存在: {db_path}")
                return False, f"找不到標記資料庫: {db_path}"
            if not input_path.exists():
                self.debug_log(f"輸入檔案不存在: {input_path}")
                return False, f"找不到輸入檔案: {input_path}"

            # 載入標記資料庫
            self.report_progress(20, "載入標記資料庫...")
            with open(db_path, 'r', encoding='utf-8') as f:
                self.db = json.load(f)
            
            # 診斷：檢查資料庫內容
            db_categories = list(self.db.keys()) if self.db else []
            self.debug_log(f"標記資料庫已載入，包含類別: {db_categories}")
            if self.db:
                for cat in db_categories[:3]:  # 只顯示前3個類別
                    items_count = len(self.db[cat].get("items", {}))
                    self.debug_log(f"  類別 {cat}: {items_count} 個標記項目")

            # 讀取輸入檔案
            self.report_progress(40, f"讀取輸入檔案... ({input_path.name})")
            with open(input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            self.debug_log(f"讀取了 {len(lines)} 行輸入")

            # 處理每一行
            self.report_progress(60, "替換標記...")
            processed_lines = []
            replacement_count = 0  # 診斷：計數實際替換次數
            for line_num, line in enumerate(lines, 1):
                parts = line.strip().split(':', 1)
                if len(parts) == 2:
                    number, text = parts
                    original_text = text.strip()
                    processed_text = self.replace_markers(original_text)
                    if original_text != processed_text:
                        replacement_count += 1
                        if replacement_count <= 3:  # 只記錄前3次替換
                            self.debug_log(f"第{line_num}行替換: [{original_text}] -> [{processed_text}]")
                    processed_lines.append(f"{number}:{processed_text}\n")
                else:
                    # 如果行不包含 ':', 保持原樣
                    processed_lines.append(line)
            
            self.debug_log(f"完成處理，共替換了 {replacement_count} 行文字")

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
