# AI Validator v1 - 翻譯驗證模組
import logging
import re
from typing import List, Dict, Tuple
from pathlib import Path

class TranslationValidator:
    """翻譯結果驗證器 v1 - 獨立的驗證層，包含格式修復功能"""

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

    def validate_response(self, response: str, expected_count: int) -> Tuple[bool, List[str], str]:
        """驗證並解析API響應

        Args:
            response: API返回的原始響應字符串
            expected_count: 預期的翻譯行數

        Returns:
            (是否有效, 解析的翻譯列表, 錯誤訊息)
        """
        try:
            # 步驟1：檢查響應是否為空
            if not response or not response.strip():
                return False, [], "API響應為空"

            # 步驟2：解析響應
            parsed_result = self._parse_response(response, expected_count)

            # 步驟3：修復格式問題
            repaired_result = self._repair_format(parsed_result, expected_count)

            # 步驟4：驗證修復後的結果
            is_valid, error_msg = self._validate_parsed_result(repaired_result, expected_count)

            if not is_valid:
                return False, repaired_result, error_msg

            return True, repaired_result, "驗證通過"

        except Exception as e:
            error_msg = f"驗證過程錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, [], error_msg

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

            # 解析編號格式（支援點號和冒號）
            lines = response.strip().split("\n")
            translations = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 嘗試匹配 "1. " 或 "1:" 格式
                matched = False
                for i in range(1, expected_count + 1):
                    # 嘗試點號格式 "1. "
                    if line.startswith(f"{i}. "):
                        translation = line[len(f"{i}. "):].strip()
                        translations.append(translation)
                        matched = True
                        break
                    # 嘗試冒號格式 "1:"
                    elif line.startswith(f"{i}:"):
                        translation = line[len(f"{i}:"):].strip()
                        translations.append(translation)
                        matched = True
                        break

                # 如果行以編號開頭但未匹配，記錄警告
                if not matched and any(line.startswith(f"{i}") for i in range(1, expected_count + 1)):
                    self.logger.warning(f"無法解析翻譯行: {line[:50]}")

            # 確保返回正確數量的翻譯
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

    def _validate_parsed_result(self, parsed_result: List[str], expected_count: int) -> Tuple[bool, str]:
        """驗證解析後的翻譯結果

        檢查項目：
        1. 行數是否正確
        2. 是否有過多空白翻譯
        3. 格式是否正確（每行應為"序號:內容"格式）

        Args:
            parsed_result: 解析後的翻譯列表
            expected_count: 預期的翻譯行數

        Returns:
            (是否有效, 錯誤訊息)
        """
        try:
            # 檢查行數是否匹配
            if len(parsed_result) != expected_count:
                msg = f"翻譯行數不匹配: 預期{expected_count}行，實際{len(parsed_result)}行"
                self.logger.warning(msg)
                return False, msg

            # 檢查格式是否正確
            format_errors = []
            for i, line in enumerate(parsed_result, 1):
                if not re.match(r'^\d+:.+', line):
                    format_errors.append(f"第{i}行格式錯誤: {line[:30]}")

            if format_errors:
                msg = f"格式錯誤: {len(format_errors)}行不符合'序號:內容'格式"
                self.logger.warning(msg)
                for error in format_errors[:5]:  # 只記錄前5個錯誤
                    self.logger.debug(error)
                return False, msg

            # 檢查是否有過多的空白翻譯
            empty_count = sum(1 for t in parsed_result if not t.split(':', 1)[1].strip())

            if empty_count > 0:
                empty_ratio = empty_count / len(parsed_result)

                if empty_ratio > 0.5:
                    msg = f"翻譯結果包含過多空白內容: {empty_count}/{len(parsed_result)}（{empty_ratio*100:.1f}%）"
                    self.logger.warning(msg)

                    # 記錄空白位置
                    empty_indices = [i+1 for i, t in enumerate(parsed_result) if not t.split(':', 1)[1].strip()]
                    self.logger.debug(f"空白翻譯位於行號: {empty_indices}")

                    return False, msg
                else:
                    # 有少量空白但不超過50%，發出警告但不失敗
                    msg = f"翻譯結果包含少量空白內容: {empty_count}/{len(parsed_result)}（{empty_ratio*100:.1f}%）"
                    self.logger.warning(msg)

            return True, "驗證通過"

        except Exception as e:
            msg = f"驗證過程錯誤: {str(e)}"
            self.logger.error(msg)
            return False, msg

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
