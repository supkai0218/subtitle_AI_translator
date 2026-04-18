# v0.89.05 新增 empty_threshold 參數（預設1%），可由 GUI 調控空白翻譯閾值
# AI Validator v2 - 翻譯驗證模組

import logging
import re
from typing import List, Dict, Tuple
from pathlib import Path
from enum import Enum

class ValidationStatus(Enum):
    """驗證狀態枚舉"""
    PASS = "pass"                      # 驗證通過
    ACCEPTABLE = "acceptable"          # 驗證通過（帶警告：少量空白翻譯）
    FIXABLE = "fixable"                # 格式問題可修復，無需重翻
    RETRY_NEEDED = "retry_needed"      # 需要重新翻譯

class TranslationValidator:
    """翻譯結果驗證器 v2 - 獨立的驗證層，包含格式修復功能"""

    def __init__(self, config: Dict = None):
        """初始化驗證器

        Args:
            config: 配置字典，包含驗證相關設定
        """
        self.config = config or {}
        self.log_level = self.config.get("log_level", "INFO")

        # 設定日誌
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def validate_response(self, response: str, expected_count: int, empty_threshold: float = 0.01) -> Tuple[ValidationStatus, List[str], str]:
        """驗證並解析API響應

        Args:
            response: API返回的原始響應字符串
            expected_count: 預期的翻譯行數
            empty_threshold: 空白翻譯閾值，預設 1%（0.01）。超過此比例則要求重翻。

        Returns:
            (驗證狀態, 解析的翻譯列表, 訊息)
            - PASS: 驗證完全通過
            - ACCEPTABLE: 驗證通過，但有少量空白翻譯（可接受）
            - FIXABLE: 格式問題已修復，無需重翻
            - RETRY_NEEDED: 需要重新翻譯
        """
        try:
            # 步驟1：檢查響應是否為空
            if not response or not response.strip():
                return ValidationStatus.RETRY_NEEDED, [], "API響應為空"

            # 步驟2：解析響應
            parsed_result = self._parse_response(response, expected_count)

            # 步驟3：修復格式問題
            repaired_result = self._repair_format(parsed_result, expected_count)

            # 步驟4：驗證修復後的結果（新增：區分錯誤類型）
            validation_result = self._validate_parsed_result(repaired_result, expected_count, empty_threshold)
            status = validation_result[0]
            error_msg = validation_result[1]

            if status == ValidationStatus.PASS:
                return ValidationStatus.PASS, repaired_result, "驗證通過"

            if status == ValidationStatus.ACCEPTABLE:
                return ValidationStatus.ACCEPTABLE, repaired_result, error_msg

            if status == ValidationStatus.FIXABLE:
                # 格式問題已自動修復，視為可接受
                return ValidationStatus.FIXABLE, repaired_result, error_msg

            # RETRY_NEEDED：需要 caller 重新翻譯
            return ValidationStatus.RETRY_NEEDED, repaired_result, error_msg

        except Exception as e:
            error_msg = f"驗證過程錯誤: {str(e)}"
            self.logger.error(error_msg)
            return ValidationStatus.RETRY_NEEDED, [], error_msg

    def _parse_response(self, response: str, expected_count: int) -> List[str]:
        """解析API響應為翻譯列表

        支援多種格式：
        - "1. 翻譯內容"（點號+空格）
        - "1:翻譯內容"（冒號）
        - JSON格式

        Args:
            response: API響應字符串
            expected_count: 預期的翻譯行數

        Returns:
            解析後的翻譯列表
        """
        try:
            # 嘗試解析JSON格式
            if response.strip().startswith("{"):
                import json
                data = json.loads(response)
                if "translations" in data:
                    translations = []
                    for item in data["translations"]:
                        translations.append(item.get("translated", ""))
                    return translations

            # 解析編號格式（支援點號和冒號，如 "1. " 或 "1:" 或 "51:"）
            lines = response.strip().split("\n")
            translations = []

            # 正則表達式：匹配行首的 "數字. " 或 "數字:" 格式
            # 支援如 "1. ", "1:", "51: ", "51. " 等
            pattern = re.compile(r'^\d+[\.:]\s*')

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 使用正則表達式移除行首可能的序號
                cleaned_line = pattern.sub('', line).strip()
                
                # 如果清理後還有內容，則加入列表
                # 注意：即便清理後為空（可能是 AI 只輸出序號），也加入空字串以維持行數對應（後續會修復）
                translations.append(cleaned_line)

            # 確保返回正確數量的翻譯
            # 如果解析出的行數過多，可能需要過濾或截斷，但這裡先遵循原始邏輯
            if len(translations) > expected_count:
                # 如果行數過多，嘗試移除空行
                translations = [t for t in translations if t]
                
            # 補齊或截斷到預期行數
            while len(translations) < expected_count:
                translations.append("")
            
            return translations[:expected_count]

        except Exception as e:
            self.logger.error(f"解析響應錯誤: {str(e)}")
            return [""] * expected_count

    def _repair_format(self, parsed_result: List[str], expected_count: int) -> List[str]:
        """修復翻譯結果的格式問題

        主要修復：
        1. 確保每行都有正確的序號格式
        2. 對於無序號的行，自動添加序號

        Args:
            parsed_result: 解析後的翻譯列表
            expected_count: 預期的翻譯行數

        Returns:
            修復格式後的翻譯列表（每項為"序號:翻譯內容"格式）
        """
        try:
            repaired_lines = []

            for i, line in enumerate(parsed_result, 1):
                line = line.strip()

                # 檢查是否已經有正確的序號格式
                if re.match(r'^\d+:', line):
                    # 已經有序號，檢查序號是否正確
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        current_num = int(parts[0])
                        if current_num == i:
                            # 序號正確，保持原樣
                            repaired_lines.append(line)
                        else:
                            # 序號不正確，修正為正確序號
                            repaired_lines.append(f"{i}:{parts[1].strip()}")
                    else:
                        # 格式錯誤，重新格式化
                        repaired_lines.append(f"{i}:{line}")
                else:
                    # 沒有序號，添加序號
                    repaired_lines.append(f"{i}:{line}")

            # 確保返回正確數量的行
            while len(repaired_lines) < expected_count:
                repaired_lines.append(f"{len(repaired_lines) + 1}:")

            return repaired_lines[:expected_count]

        except Exception as e:
            self.logger.error(f"格式修復錯誤: {str(e)}")
            # 如果修復失敗，返回原始結果
            return parsed_result

    def _validate_parsed_result(self, parsed_result: List[str], expected_count: int, empty_threshold: float = 0.01) -> Tuple[ValidationStatus, str]:
        """驗證解析後的翻譯結果（v2 區分錯誤類型）

        檢查項目：
        1. 行數是否正確
        2. 是否有過多空白翻譯
        3. 格式是否正確（每行應為"序號:內容"格式，內容可為空）

        錯誤分類：
        - PASS: 完全通過
        - ACCEPTABLE: 少量空白翻譯（可接受）
        - FIXABLE: 格式問題已自動修復，無需重翻
        - RETRY_NEEDED: 行數嚴重不足或結構性錯誤，需要重翻

        Args:
            parsed_result: 解析後的翻譯列表
            expected_count: 預期的翻譯行數
            empty_threshold: 空白翻譯閾值，預設 1%（0.01）。超過此比例則要求重翻。

        Returns:
            (驗證狀態, 訊息)
        """
        try:
            # 檢查行數是否匹配
            if len(parsed_result) != expected_count:
                # 行數差距過大才需要重翻
                if len(parsed_result) < expected_count * 0.5:
                    msg = f"翻譯行數嚴重不足: 預期{expected_count}行，實際{len(parsed_result)}行"
                    self.logger.warning(msg)
                    return ValidationStatus.RETRY_NEEDED, msg
                else:
                    # 行數略少，可通過補空白修復
                    msg = f"翻譯行數略少: 預期{expected_count}行，實際{len(parsed_result)}行（已補空白）"
                    self.logger.warning(msg)
                    return ValidationStatus.FIXABLE, msg

            # 檢查格式是否正確（內容可為空，只檢查序號:格式）
            # 改用 \d+: 而非 \d+:.+，接受空白翻譯
            structural_errors = []  # 結構性錯誤（無序號或格式完全不符）
            for i, line in enumerate(parsed_result, 1):
                if not re.match(r'^\d+:', line):
                    structural_errors.append(f"第{i}行: {line[:30]}")

            if structural_errors:
                msg = f"格式錯誤: {len(structural_errors)}行缺少序號標記（已嘗試修復）"
                self.logger.warning(msg)
                for error in structural_errors[:5]:
                    self.logger.debug(error)
                # 格式錯誤視為可修復，無需重翻
                return ValidationStatus.FIXABLE, msg

            # 檢查是否有過多的空白翻譯
            empty_count = sum(1 for t in parsed_result if not t.split(':', 1)[1].strip())

            if empty_count > 0:
                empty_ratio = empty_count / len(parsed_result)

                if empty_ratio > empty_threshold:
                    msg = f"翻譯結果包含過多空白內容: {empty_count}/{len(parsed_result)}（{empty_ratio*100:.1f}%，閾值{empty_threshold*100:.1f}%）"
                    self.logger.warning(msg)
                    empty_indices = [i+1 for i, t in enumerate(parsed_result) if not t.split(':', 1)[1].strip()]
                    self.logger.debug(f"空白翻譯位於行號: {empty_indices}")
                    # 空白過多仍需要重翻
                    return ValidationStatus.RETRY_NEEDED, msg
                else:
                    # 有少量空白但不超過閾值，發出警告但視為可接受
                    msg = f"翻譯結果包含少量空白內容: {empty_count}/{len(parsed_result)}（{empty_ratio*100:.1f}%，閾值{empty_threshold*100:.1f}%）"
                    self.logger.warning(msg)
                    return ValidationStatus.ACCEPTABLE, msg

            return ValidationStatus.PASS, "驗證通過"

        except Exception as e:
            msg = f"驗證過程錯誤: {str(e)}"
            self.logger.error(msg)
            return ValidationStatus.RETRY_NEEDED, msg

    def validate_with_original(self, original_batch: List[str], translated_batch: List[str]) -> Tuple[bool, str]:
        """與原文對比驗證翻譯結果

        檢查項目：
        1. 行數是否匹配
        2. 翻譯長度是否合理

        Args:
            original_batch: 原文列表
            translated_batch: 翻譯列表

        Returns:
            (是否有效, 錯誤訊息)
        """
        try:
            # 檢查行數是否匹配
            if len(original_batch) != len(translated_batch):
                msg = f"翻譯行數不匹配: 原文{len(original_batch)}行，翻譯{len(translated_batch)}行"
                self.logger.warning(msg)
                return False, msg

            # 檢查翻譯長度合理性
            length_warnings = []
            for i, (orig, trans) in enumerate(zip(original_batch, translated_batch)):
                if orig.strip() and trans.strip():
                    # 解析翻譯內容（去掉序號）
                    trans_content = trans.split(':', 1)[1] if ':' in trans else trans
                    # 翻譯不應該過短或過長
                    if len(trans_content) < len(orig) * 0.1 or len(trans_content) > len(orig) * 5:
                        warning = f"第{i+1}行翻譯長度可能異常: 原文{len(orig)}字，翻譯{len(trans_content)}字"
                        self.logger.warning(warning)
                        length_warnings.append(warning)

            if length_warnings:
                self.logger.debug(f"長度警告數量: {len(length_warnings)}")

            return True, "驗證通過"

        except Exception as e:
            msg = f"驗證過程錯誤: {str(e)}"
            self.logger.error(msg)
            return False, msg
