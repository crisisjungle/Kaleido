"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""

    _DEEPSEEK_LEGACY_MODEL_ALIASES = {
        "deepseek-chat": ("deepseek-v4-flash", "disabled"),
        "deepseek-reasoner": ("deepseek-v4-flash", "enabled"),
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _is_deepseek(self) -> bool:
        return (
            "deepseek" in (self.base_url or "").lower()
            or "deepseek" in (self.model or "").lower()
        )

    def _resolve_deepseek_request(
        self,
        force_non_thinking: bool = False
    ) -> tuple[str, Optional[str], Optional[str]]:
        """解析 DeepSeek V4 兼容模型名与思考模式。"""
        model = self.model or ""
        if not self._is_deepseek():
            return model, None, None

        normalized_model = model.strip().lower()
        resolved_model = model
        thinking_mode: Optional[str] = None

        legacy_mapping = self._DEEPSEEK_LEGACY_MODEL_ALIASES.get(normalized_model)
        if legacy_mapping:
            resolved_model, thinking_mode = legacy_mapping

        configured_mode = (Config.DEEPSEEK_THINKING_MODE or "auto").strip().lower()
        if force_non_thinking:
            thinking_mode = "disabled"
        elif configured_mode in {"enabled", "disabled"}:
            thinking_mode = configured_mode

        reasoning_effort = None
        if thinking_mode == "enabled":
            configured_effort = (Config.DEEPSEEK_REASONING_EFFORT or "high").strip().lower()
            if configured_effort in {"max", "xhigh"}:
                reasoning_effort = "max"
            else:
                # DeepSeek 文档中 low / medium 会映射到 high，这里直接统一。
                reasoning_effort = "high"

        return resolved_model, thinking_mode, reasoning_effort
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        force_non_thinking: bool = False
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        resolved_model, thinking_mode, reasoning_effort = self._resolve_deepseek_request(
            force_non_thinking=force_non_thinking
        )

        kwargs = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format

        if thinking_mode in {"enabled", "disabled"}:
            kwargs["extra_body"] = {"thinking": {"type": thinking_mode}}
        if thinking_mode == "enabled" and reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        # DeepSeek 在 JSON 输出场景偶发空内容；这里统一走非思考模式，并在本地解析 JSON，
        # 保持与旧版 deepseek-chat / deepseek-reasoner 行为一致。
        use_response_format = not self._is_deepseek()

        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if use_response_format else None,
            force_non_thinking=self._is_deepseek()
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}")
