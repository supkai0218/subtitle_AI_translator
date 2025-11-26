import os
import re

class SrtSeparator:
    """
    將標準 SRT 檔案拆解為兩個文字檔：
      - 字幕文字檔：1A-txt_{filename}.txt
      - 時間軸檔：1A-time_{filename}.txt
      
    輸入 SRT 檔案預設位於主程式所在目錄下的 "srt/in" 資料夾，
    檔名以傳入的 base filename 為主（檔案副檔名為 .srt）。
    """

    def parse_srt(self, srt_file_path):
        """
        讀取並解析 SRT 檔案，回傳時間軸與字幕的對照字典。
        
        參數:
            srt_file_path (str): 輸入 SRT 檔案路徑
        
        回傳:
            tuple: (timecode_dict, subtitle_dict)
                timecode_dict: {index: timecode string}
                subtitle_dict: {index: subtitle text}
        """
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用連續空行分隔每個字幕區塊
        blocks = re.split(r'\n\n+', content.strip())
        timecode_dict = {}
        subtitle_dict = {}
        
        for block in blocks:
            lines = block.splitlines()
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                except ValueError:
                    continue
                timecode = lines[1]
                text = "\n".join(lines[2:])
                timecode_dict[index] = timecode
                subtitle_dict[index] = text
        return timecode_dict, subtitle_dict

    def save_files(self, timecode_dict, subtitle_dict, output_dir, base_filename):
        """
        儲存兩個文字檔：
          - 字幕文字檔：1A-txt_{base_filename}.txt
          - 時間軸檔：1A-time_{base_filename}.txt
        
        參數:
            timecode_dict (dict): 時間軸對照字典
            subtitle_dict (dict): 字幕文字對照字典
            output_dir (str): 輸出資料夾路徑，由主程式定義
            base_filename (str): 基本檔名（不含副檔名）
        
        回傳:
            tuple: (subtitle_file_path, timecode_file_path)
        """
        subtitle_filename = f"1A-txt_{base_filename}.txt"
        timecode_filename = f"1A-time_{base_filename}.txt"
        subtitle_path = os.path.join(output_dir, subtitle_filename)
        timecode_path = os.path.join(output_dir, timecode_filename)
        
        # 儲存字幕文字檔
        with open(subtitle_path, 'w', encoding='utf-8') as f:
            for idx in sorted(subtitle_dict.keys()):
                f.write(f"{idx}:{subtitle_dict[idx]}\n")
        
        # 儲存時間軸檔
        with open(timecode_path, 'w', encoding='utf-8') as f:
            for idx in sorted(timecode_dict.keys()):
                f.write(f"{idx}:{timecode_dict[idx]}\n")
        
        return subtitle_path, timecode_path

    def convert(self, output_dir, base_filename):
        """
        執行 SRT 檔案拆解，並輸出字幕文字與時間軸檔案。
        
        輸入 SRT 檔案固定位於主程式所在目錄下的 "srt/in" 資料夾，
        檔名為 {base_filename}.srt。
        
        參數:
            output_dir (str): 輸出檔案的目錄，由主程式定義
            base_filename (str): 基本檔名（不含副檔名），同時用於輸入及輸出檔案名稱
            
        回傳:
            tuple: (subtitle_file_path, timecode_file_path)
        """
        # 組合輸入檔案路徑：主程式目錄下的 "srt/in" 資料夾 + {base_filename}.srt
        current_dir = os.getcwd()
        input_srt_path = os.path.join(current_dir, "srt", "in", f"{base_filename}.srt")
        
        if not os.path.exists(input_srt_path):
            raise FileNotFoundError(f"找不到 SRT 檔案：{input_srt_path}")
        
        timecode_dict, subtitle_dict = self.parse_srt(input_srt_path)
        return self.save_files(timecode_dict, subtitle_dict, output_dir, base_filename)
