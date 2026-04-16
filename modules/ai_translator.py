# v0.88.01 新增一鍵全自動翻譯


import json
import requests
import time
import asyncio
from typing import List, Dict, Tuple, Optional
import logging
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from pathlib import Path

# 條件導入aiohttp，如果沒有安裝則禁用並行功能
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None

class BatchStatus(Enum):
    """批次狀態枚舉"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class BatchInfo:
    """批次資訊"""
    index: int
    lines: List[str]
    status: BatchStatus
    result: List[str]
    error_message: str = ""
    retry_count: int = 0

class AITranslator:
    """AI翻譯模組 v1b - 純通信層（移除驗證邏輯）"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.api_provider = config.get("api_provider", "openrouter")
        self.api_url = config.get("api_url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "anthropic/claude-3-sonnet")
        self.source_language = config.get("source_language", "ja")
        self.target_language = config.get("target_language", "zh-TW")
        self.batch_size = config.get("batch_size", 10)
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 2)
        self.max_concurrent_requests = config.get("max_concurrent_requests", 5)
        
        # 偵測免費模型（OpenRouter 免費模型以 :free 結尾）
        self.is_free_model = self.model.endswith(":free")
        # 免費模型限制：20 RPM，所以每次請求間至少間隔 4 秒
        self.free_model_delay = config.get("free_model_delay", 4)
        
        # v1b：移除 enable_validation，驗證由外部模組負責
        
        # 設定日誌
        log_level = config.get("log_level", "INFO")
        log_level = getattr(logging, log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # 批次管理
        self.batches: List[BatchInfo] = []
    
    def validate_api_connection(self) -> Tuple[bool, str]:
        """驗證API連線"""
        try:
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, this is a connection test."}
            ]
            
            start_time = time.time()
            response = self._make_api_request(test_messages, max_tokens=50)
            elapsed_time = time.time() - start_time
            
            if response:
                msg = f"API連線成功 (回應時間: {elapsed_time:.2f}秒)"
                self.logger.info(msg)
                return True, msg
            else:
                return False, "API連線失敗：回應為空"
        except Exception as e:
            error_msg = f"API連線錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def translate_batch(self, text_lines: List[str], context_info: Optional[Dict] = None, 
                       progress_callback=None) -> Tuple[bool, str, str]:
        """批次翻譯文字行 - v1b純通信版本
        
        返回原始API響應，不進行驗證
        
        Args:
            text_lines: 要翻譯的文字行列表
            context_info: 上下文信息
            progress_callback: 進度回調函數
        
        Returns:
            (成功標誌, 原始API響應, 錯誤訊息)
        """
        try:
            total_batches = (len(text_lines) + self.batch_size - 1) // self.batch_size
            
            self.logger.info(f"開始翻譯：總行數={len(text_lines)}, 批次數={total_batches}")
            
            # 免費模型強制使用循序模式，避免並行請求觸發速率限制
            if self.is_free_model:
                self.logger.info("偵測到免費模型，強制使用循序翻譯模式（避免429速率限制）")
                return self._translate_batch_sequential(text_lines, context_info, progress_callback)
            elif self.max_concurrent_requests > 1 and total_batches > 1:
                return self._translate_batch_concurrent(text_lines, context_info, progress_callback)
            else:
                return self._translate_batch_sequential(text_lines, context_info, progress_callback)
                
        except Exception as e:
            error_msg = f"批次翻譯錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, "", error_msg
    
    def _translate_batch_sequential(self, text_lines: List[str], context_info: Optional[Dict] = None, 
                                  progress_callback=None) -> Tuple[bool, str, str]:
        """循序批次翻譯"""
        try:
            all_responses = []
            total_batches = (len(text_lines) + self.batch_size - 1) // self.batch_size
            
            for i in range(0, len(text_lines), self.batch_size):
                batch = text_lines[i:i + self.batch_size]
                batch_num = i // self.batch_size + 1
                
                if progress_callback:
                    progress_callback(f"翻譯批次 {batch_num}/{total_batches}")
                
                success, response, error_msg = self._translate_single_batch(batch, context_info)
                
                if not success:
                    return False, "", error_msg
                
                all_responses.append(response)
                
                # 避免API限制，批次間延遲（免費模型使用更長間隔）
                if i + self.batch_size < len(text_lines):
                    delay = self.free_model_delay if self.is_free_model else self.retry_delay
                    self.logger.debug(f"批次間延遲 {delay} 秒")
                    time.sleep(delay)
            
            # 合併所有響應
            combined_response = "\n".join(all_responses)
            return True, combined_response, "翻譯完成"
            
        except Exception as e:
            error_msg = f"循序翻譯錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, "", error_msg
    
    def _translate_batch_concurrent(self, text_lines: List[str], context_info: Optional[Dict] = None, 
                                  progress_callback=None) -> Tuple[bool, str, str]:
        """並行批次翻譯"""
        if not AIOHTTP_AVAILABLE:
            self.logger.warning("aiohttp不可用，降級為循序處理")
            if progress_callback:
                progress_callback("aiohttp不可用，使用循序翻譯模式")
            return self._translate_batch_sequential(text_lines, context_info, progress_callback)
        
        try:
            # 準備批次
            self.batches = []
            for i in range(0, len(text_lines), self.batch_size):
                batch_lines = text_lines[i:i + self.batch_size]
                batch_info = BatchInfo(
                    index=i // self.batch_size,
                    lines=batch_lines,
                    status=BatchStatus.PENDING,
                    result=[]
                )
                self.batches.append(batch_info)
            
            # 執行並行翻譯
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, error_msg = loop.run_until_complete(
                    self._process_batches_async(context_info, progress_callback)
                )
            finally:
                loop.close()
            
            if not success:
                return False, "", error_msg
            
            # 收集結果
            all_responses = []
            for batch in sorted(self.batches, key=lambda x: x.index):
                if batch.status == BatchStatus.COMPLETED:
                    all_responses.append(batch.result)
                else:
                    return False, "", f"批次 {batch.index + 1} 翻譯失敗: {batch.error_message}"
            
            combined_response = "\n".join(all_responses)
            return True, combined_response, "並行翻譯完成"
            
        except Exception as e:
            error_msg = f"並行翻譯錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, "", error_msg
    
    async def _process_batches_async(self, context_info: Optional[Dict], progress_callback) -> Tuple[bool, str]:
        """異步處理批次"""
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        
        async def process_single_batch(batch_info: BatchInfo):
            async with semaphore:
                await self._translate_batch_async(batch_info, context_info, progress_callback)
        
        tasks = [process_single_batch(batch) for batch in self.batches]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 檢查是否有失敗的批次
        failed_batches = [b for b in self.batches if b.status == BatchStatus.FAILED]
        
        if failed_batches:
            error_messages = [f"批次{b.index + 1}: {b.error_message}" for b in failed_batches]
            return False, f"翻譯失敗: {'; '.join(error_messages)}"
        
        return True, "所有批次翻譯完成"
    
    async def _translate_batch_async(self, batch_info: BatchInfo, context_info: Optional[Dict], progress_callback):
        """異步翻譯單一批次"""
        try:
            batch_info.status = BatchStatus.PROCESSING
            
            if progress_callback:
                progress_callback(f"處理批次 {batch_info.index + 1}")
            
            # 準備翻譯內容
            numbered_lines = []
            for idx, line in enumerate(batch_info.lines, 1):
                if line.strip():
                    numbered_lines.append(f"{idx}. {line.strip()}")
            
            if not numbered_lines:
                batch_info.result = ""
                batch_info.status = BatchStatus.COMPLETED
                return
            
            # 建立訊息
            messages = self._prepare_messages(numbered_lines, context_info)
            
            # 發送異步API請求
            response = await self._make_api_request_async(messages)
            
            if response:
                batch_info.result = response
                batch_info.status = BatchStatus.COMPLETED
            else:
                batch_info.status = BatchStatus.FAILED
                batch_info.error_message = "API回應為空"
                
        except Exception as e:
            batch_info.status = BatchStatus.FAILED
            batch_info.error_message = str(e)
            self.logger.error(f"批次 {batch_info.index + 1} 翻譯錯誤: {str(e)}")
    
    async def _make_api_request_async(self, messages: List[Dict], max_tokens: int = 2000) -> Optional[str]:
        """發送異步API請求，含429速率限制重試"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp不可用，無法執行異步請求")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/subtitle-ai-translator",
            "X-Title": "Subtitle AI Translator"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        # 免費模型 429 重試次數獨立設定
        max_429_retries = 5 if self.is_free_model else self.max_retries
        
        for attempt in range(max_429_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.api_url, headers=headers, json=data) as response:
                        # 處理429速率限制：等待後重試
                        if response.status == 429:
                            if attempt < max_429_retries:
                                retry_after = response.headers.get("Retry-After")
                                if retry_after:
                                    wait_time = float(retry_after)
                                elif self.is_free_model:
                                    wait_time = max(5, self.free_model_delay)
                                else:
                                    wait_time = self.retry_delay * (2 ** attempt)
                                self.logger.warning(
                                    f"收到429速率限制，等待 {wait_time:.1f} 秒後重試 "
                                    f"(第 {attempt + 1}/{max_429_retries} 次重試)"
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                self.logger.error(
                                    f"已達最大重試次數 ({max_429_retries})，仍收到429速率限制。"
                                    f"免費模型有嚴格的速率限制，請稍後再試。"
                                )
                                return None
                        
                        response.raise_for_status()
                        result = await response.json()
                        
                        if "choices" in result and len(result["choices"]) > 0:
                            choice = result["choices"][0]
                            return choice["message"]["content"]
                        
                        return None
                        
            except (aiohttp.ClientError, Exception) as e:
                if attempt < max_429_retries and "429" in str(e):
                    wait_time = max(5, self.free_model_delay) if self.is_free_model else self.retry_delay * (2 ** attempt)
                    self.logger.warning(f"請求失敗，等待 {wait_time:.1f} 秒後重試: {str(e)}")
                    await asyncio.sleep(wait_time)
                    continue
                self.logger.error(f"API請求錯誤: {str(e)}")
                return None
        
        return None
    
    def _translate_single_batch(self, batch: List[str], context_info: Optional[Dict] = None) -> Tuple[bool, str, str]:
        """翻譯單一批次（同步版本）"""
        try:
            # 準備翻譯內容
            numbered_lines = []
            for idx, line in enumerate(batch, 1):
                if line.strip():
                    numbered_lines.append(f"{idx}. {line.strip()}")
            
            if not numbered_lines:
                return True, "", "空批次跳過"
            
            # 建立訊息
            messages = self._prepare_messages(numbered_lines, context_info)
            
            # 發送API請求
            response = self._make_api_request(messages)
            
            if response:
                return True, response, "翻譯成功"
            else:
                return False, "", "API回應為空"
                
        except Exception as e:
            error_msg = f"批次翻譯錯誤: {str(e)}"
            self.logger.error(error_msg)
            return False, "", error_msg
    
    def _prepare_messages(self, numbered_lines: List[str], context_info: Optional[Dict] = None) -> List[Dict]:
        """準備發送給AI的訊息"""
        prompts = self.config.get("prompts", {})
        
        # 建立system prompt
        system_prompt = prompts.get("system_prompt", self._get_default_system_prompt())
        system_prompt = self._replace_variables(system_prompt, {
            "source_lang": self._get_language_name(self.source_language),
            "target_lang": self._get_language_name(self.target_language),
            "translation_style": prompts.get("translation_style", "自然對話風格")
        })
        
        # 建立user prompt
        user_prompt_template = prompts.get("user_prompt_template", self._get_default_user_prompt())
        subtitle_content = "\n".join(numbered_lines)
        
        user_prompt = self._replace_variables(user_prompt_template, {
            "subtitle_content": subtitle_content,
            "video_type": prompts.get("video_type", "一般影片"),
            "character_info": prompts.get("character_info", "無特殊設定"),
            "source_lang": self._get_language_name(self.source_language),
            "target_lang": self._get_language_name(self.target_language)
        })
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def _make_api_request(self, messages: List[Dict], max_tokens: int = 2000) -> Optional[str]:
        """發送API請求（同步版本），含429速率限制智慧重試
        
        免費模型的上游 provider 會有 per-request cooldown（約3-5秒），
        所以 429 重試使用固定等待時間而非指數退避。
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/subtitle-ai-translator",
            "X-Title": "Subtitle AI Translator"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        # 免費模型 429 重試次數獨立設定（因為每次重試只是等待，成本很低）
        max_429_retries = 5 if self.is_free_model else self.max_retries
        
        for attempt in range(max_429_retries + 1):
            try:
                response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
                
                # 處理429速率限制：等待後重試
                if response.status_code == 429:
                    if attempt < max_429_retries:
                        # 優先使用伺服器的 Retry-After header
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            wait_time = float(retry_after)
                        elif self.is_free_model:
                            # 免費模型：上游 provider 有 per-request cooldown
                            # 使用固定 5 秒等待（經實測確認有效）
                            wait_time = max(5, self.free_model_delay)
                        else:
                            # 付費模型：指數退避
                            wait_time = self.retry_delay * (2 ** attempt)
                        self.logger.warning(
                            f"收到429速率限制，等待 {wait_time:.1f} 秒後重試 "
                            f"(第 {attempt + 1}/{max_429_retries} 次重試)"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(
                            f"已達最大重試次數 ({max_429_retries})，仍收到429速率限制。"
                            f"免費模型有嚴格的速率限制，請稍後再試。"
                        )
                        return None
                
                response.raise_for_status()
                
                result = response.json()
                
                if "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0]
                    return choice["message"]["content"]
                
                return None
                
            except requests.RequestException as e:
                if attempt < max_429_retries and "429" in str(e):
                    wait_time = max(5, self.free_model_delay) if self.is_free_model else self.retry_delay * (2 ** attempt)
                    self.logger.warning(f"請求失敗，等待 {wait_time:.1f} 秒後重試: {str(e)}")
                    time.sleep(wait_time)
                    continue
                self.logger.error(f"API請求錯誤: {str(e)}")
                return None
        
        return None
    
    def _replace_variables(self, template: str, variables: Dict[str, str]) -> str:
        """替換模板中的變數"""
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result
    
    def _get_language_name(self, lang_code: str) -> str:
        """取得語言名稱"""
        lang_map = {
            "ja": "日文",
            "en": "英文",
            "ko": "韓文",
            "zh-TW": "繁體中文",
            "zh-CN": "簡體中文",
            "zh": "中文"
        }
        return lang_map.get(lang_code, lang_code)
    
    def _get_default_system_prompt(self) -> str:
        """取得預設system prompt"""
        return """你是字幕翻譯AI。必須嚴格遵守以下格式：

輸入格式："{序號}:{日文內容}"
輸出格式："{序號}:{中文翻譯}"

重要規則：
1. 只輸出翻譯結果，不要確認或解釋
2. 保留輸入中的特殊標記（如[[A-1]]），直接複製到輸出
3. 翻譯風格：自然對話，台灣用語
4. 序號必須與輸入相同
5. 不添加任何額外說明或註解"""
    
    def _get_default_user_prompt(self) -> str:
        """取得預設user prompt"""
        return """請翻譯以下日文字幕為繁體中文。

翻譯要點：
- 考慮前後字幕的上下文，確保句子完整性
- 使用台灣日常用語
- 保持原文的語氣和情感

待翻譯內容：
{subtitle_content}"""
