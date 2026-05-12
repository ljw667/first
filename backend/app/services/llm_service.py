"""
阿里云百炼大模型对话服务模块
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_SYSTEM_PROMPT = (
    "你是一个友好的智能语音助手。请用简洁、口语化的语言回答用户的问题。"
    "回答要适合语音播报，避免使用复杂的格式、列表或过长的句子。"
)

_VL_MODEL = "qwen-vl-plus"


class QwenLLMService:
    """
    阿里云百炼大模型对话服务
    """

    def __init__(self, api_key: str, model: str = "qwen-turbo") -> None:
        self._api_key = api_key
        self._model = model
        self._system_prompt = _SYSTEM_PROMPT

        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=DASHSCOPE_BASE_URL,
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self._system_prompt = value

    async def chat_stream(self, user_text: str) -> AsyncGenerator[str, None]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_text},
        ]

        log.info("LLM streaming request, model=%s, text=%s", self._model, user_text[:50])

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as exc:
            log.error("LLM API error: %s", exc)
            raise RuntimeError(f"LLM API error: {exc}") from exc

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            log.error("LLM stream error: %s", exc)
            raise RuntimeError(f"LLM stream error: {exc}") from exc

    async def chat_stream_with_image(
        self, user_text: str, image_base64: str
    ) -> AsyncGenerator[str, None]:
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            },
        ]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        log.info(
            "LLM VL streaming request, model=%s, text=%s",
            _VL_MODEL,
            user_text[:50],
        )

        try:
            stream = await self._client.chat.completions.create(
                model=_VL_MODEL,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as exc:
            log.error("LLM VL API error: %s", exc)
            raise RuntimeError(f"LLM VL API error: {exc}") from exc

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            log.error("LLM VL stream error: %s", exc)
            raise RuntimeError(f"LLM VL stream error: {exc}") from exc

    async def chat(self, user_text: str) -> str:
        chunks: list[str] = []
        async for chunk in self.chat_stream(user_text):
            chunks.append(chunk)
        return "".join(chunks)
