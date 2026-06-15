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
        self.fallback_api_key = Config.LLM_FALLBACK_API_KEY
        self.fallback_base_url = Config.LLM_FALLBACK_BASE_URL
        self.fallback_model = Config.LLM_FALLBACK_MODEL_NAME

    def _has_fallback(self) -> bool:
        return bool(self.fallback_api_key)

    def _build_client(self, api_key: str, base_url: str) -> OpenAI:
        return OpenAI(api_key=api_key, base_url=base_url)

    def _create_completion(
        self,
        kwargs: Dict[str, Any],
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict],
        force_non_thinking: bool,
    ) -> Any:
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not self._has_fallback():
                raise

            fallback_client = self._build_client(
                self.fallback_api_key,
                self.fallback_base_url or self.base_url,
            )
            fallback_kwargs = self._prepare_completion_kwargs(
                base_url=self.fallback_base_url or self.base_url,
                model=self.fallback_model or kwargs.get("model"),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                force_non_thinking=force_non_thinking,
            )
            try:
                return fallback_client.chat.completions.create(**fallback_kwargs)
            except Exception:
                raise exc

    def _is_deepseek_target(self, base_url: Optional[str], model: Optional[str]) -> bool:
        return (
            "deepseek" in (base_url or "").lower()
            or "deepseek" in (model or "").lower()
        )

    def _resolve_deepseek_request(
        self,
        base_url: Optional[str],
        model: Optional[str],
        force_non_thinking: bool = False
    ) -> tuple[str, Optional[str], Optional[str]]:
        """解析 DeepSeek V4 兼容模型名与思考模式。"""
        model = model or ""
        if not self._is_deepseek_target(base_url, model):
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

    def _prepare_completion_kwargs(
        self,
        *,
        base_url: Optional[str],
        model: Optional[str],
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict],
        force_non_thinking: bool,
    ) -> Dict[str, Any]:
        resolved_model, thinking_mode, reasoning_effort = self._resolve_deepseek_request(
            base_url=base_url,
            model=model,
            force_non_thinking=force_non_thinking,
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

        return kwargs

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
        kwargs = self._prepare_completion_kwargs(
            base_url=self.base_url,
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            force_non_thinking=force_non_thinking,
        )
        
        response = self._create_completion(
            kwargs,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            force_non_thinking=force_non_thinking,
        )
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
        use_response_format = not self._is_deepseek_target(self.base_url, self.model)

        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if use_response_format else None,
            force_non_thinking=self._is_deepseek_target(self.base_url, self.model)
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
