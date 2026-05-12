"""
HTTP 对话接口

提供 POST /api/chat/text 和 POST /api/chat/voice 两个端点，
兼容非 WebSocket 客户端，内部调用已有的 LLM / TTS / ASR 服务。
"""

import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

from fastapi import APIRouter

from app.core.config import get_settings
from app.middleware.error_handler import AppException
from app.services.llm_service import QwenLLMService
from app.services.tts_service import BailianTTSService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["对话"])


def _validate_image_base64(image_b64: str) -> bool:
    """
    验证 base64 图片数据的有效性
    
    Args:
        image_b64: base64 编码的图片数据
        
    Returns:
        True 如果图片有效，False 否则
    """
    try:
        # 解码 base64
        image_bytes = base64.b64decode(image_b64)
        
        # 检查最小长度（至少是一个有效图片）
        if len(image_bytes) < 100:
            return False
            
        # 检查图片格式（通过文件头魔数检测）
        # JPEG: FF D8 FF
        # PNG:  89 50 4E 47
        # GIF:  47 49 46 38
        # WEBP: 52 49 46 46 ... 57 45 42 50
        
        header = image_bytes[:8]
        
        # JPEG/JPG
        if header[:3] == b'\xff\xd8\xff':
            return True
        # PNG
        if header[:4] == b'\x89PNG':
            return True
        # GIF
        if header[:6] in [b'GIF87a', b'GIF89a']:
            return True
        # WEBP
        if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return True
            
        return False
    except Exception:
        return False


# ---- 请求/响应模型 ----

class TextChatRequest(BaseModel):
    """纯文本对话请求"""
    text: str = Field(..., min_length=1, max_length=4096, description="用户输入文本")
    image_base64: str | None = Field(None, description="可选的图片 base64 数据")


class TextChatResponse(BaseModel):
    """纯文本对话响应"""
    reply: str = Field(..., description="模型回复文本")
    model: str = Field(..., description="使用的模型名称")


class VoiceChatRequest(BaseModel):
    """语音对话请求"""
    audio_base64: str = Field(..., min_length=1, description="base64 编码的音频数据")
    audio_format: str = Field("webm", description="音频格式: webm / ogg / wav")
    image_base64: str | None = Field(None, description="可选的图片 base64 数据")


class VoiceChatResponse(BaseModel):
    """语音对话响应"""
    asr_text: str = Field(..., description="语音识别结果")
    reply: str = Field(..., description="模型回复文本")
    audio_base64: str | None = Field(None, description="回复音频的 base64 数据（mp3 格式）")


# ---- 接口实现 ----

def _create_llm_service() -> QwenLLMService:
    """根据全局配置创建 LLM 服务实例"""
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise AppException(code=503, message="LLM 服务未配置 API Key")
    return QwenLLMService(
        api_key=settings.dashscope_api_key,
        model=settings.llm_model,
    )


@router.post("/text", response_model=TextChatResponse, summary="纯文本对话")
async def text_chat(req: TextChatRequest) -> TextChatResponse:
    """
    纯文本对话接口

    接收用户文本（可选附带图片），调用 LLM 生成回复。
    - 无图片时使用纯文本模型（qwen-turbo）
    - 有图片时自动切换到视觉模型（qwen-vl-plus）
    """
    llm = _create_llm_service()

    # 验证图片数据（如果提供）
    if req.image_base64:
        if not _validate_image_base64(req.image_base64):
            raise AppException(code=400, message="图片格式无效，请提供有效的 jpeg/jpg/png/gif/webp 格式图片")

    try:
        if req.image_base64:
            reply = ""
            async for chunk in llm.chat_stream_with_image(req.text, req.image_base64):
                reply += chunk
            used_model = "qwen-vl-plus"
        else:
            reply = await llm.chat(req.text)
            used_model = llm.model

        return TextChatResponse(reply=reply, model=used_model)

    except RuntimeError as exc:
        log.error("文本对话失败: %s", exc)
        # 检查是否是图片格式错误，返回更友好的错误信息
        if "image format is illegal" in str(exc):
            raise AppException(code=400, message="图片格式非法，请检查图片文件是否损坏或格式不支持") from exc
        raise AppException(code=502, message=f"LLM 服务调用失败: {exc}") from exc


@router.post("/voice", response_model=VoiceChatResponse, summary="语音对话")
async def voice_chat(req: VoiceChatRequest) -> VoiceChatResponse:
    """
    语音对话接口

    接收 base64 编码的音频，依次调用：
    1. ASR 识别音频 → 文本
    2. LLM 生成回复
    3. TTS 合成回复音频

    返回识别文本、回复文本和回复音频。
    """
    settings = get_settings()

    if not settings.dashscope_api_key:
        raise AppException(code=503, message="服务未配置 API Key")

    # 验证图片数据（如果提供）
    if req.image_base64:
        if not _validate_image_base64(req.image_base64):
            raise AppException(code=400, message="图片格式无效，请提供有效的 jpeg/jpg/png/gif/webp 格式图片")

    # ---- 1. ASR 语音识别 ----
    try:
        from app.services.asr_service import AliyunASRService
        from app.utils.audio_converter import convert_to_pcm, detect_audio_format

        audio_bytes = base64.b64decode(req.audio_base64)
        detected_format = detect_audio_format(req.audio_format)
        pcm_audio = convert_to_pcm(audio_bytes, detected_format)

        if not pcm_audio:
            raise AppException(code=400, message="音频格式转换失败，请检查音频数据")

        asr_text = ""
        asr = AliyunASRService(api_key=settings.dashscope_api_key)

        asr_result_future: list[dict[str, Any]] = []

        async def _on_result(text: str, is_final: bool) -> None:
            if is_final:
                asr_result_future.append({"text": text, "is_final": True})

        async def _on_error(error_msg: str) -> None:
            asr_result_future.append({"error": error_msg})

        asr.on_result = _on_result
        asr.on_error = _on_error

        await asr.connect()
        await asr.start_transcription(
            format="pcm",
            sample_rate=settings.asr_sample_rate,
            language=settings.asr_language,
        )
        await asr.send_audio(pcm_audio)
        await asr.finish_transcription()

        import asyncio
        for _ in range(60):
            if asr_result_future:
                break
            await asyncio.sleep(0.5)

        await asr.disconnect()

        if not asr_result_future:
            raise AppException(code=502, message="ASR 识别超时，未收到结果")

        result = asr_result_future[0]
        if "error" in result:
            raise AppException(code=502, message=f"ASR 识别失败: {result['error']}")

        asr_text = result["text"]

    except AppException:
        raise
    except Exception as exc:
        log.error("语音识别失败: %s", exc)
        raise AppException(code=502, message=f"语音识别失败: {exc}") from exc

    if not asr_text.strip():
        raise AppException(code=400, message="语音识别结果为空，请重新录音")

    # ---- 2. LLM 生成回复 ----
    llm = _create_llm_service()
    try:
        if req.image_base64:
            reply = ""
            async for chunk in llm.chat_stream_with_image(asr_text, req.image_base64):
                reply += chunk
        else:
            reply = await llm.chat(asr_text)
    except RuntimeError as exc:
        log.error("LLM 调用失败: %s", exc)
        raise AppException(code=502, message=f"LLM 服务调用失败: {exc}") from exc

    # ---- 3. TTS 合成语音 ----
    audio_b64: str | None = None
    try:
        tts = BailianTTSService(voice=settings.tts_voice)
        await tts.connect()
        audio_bytes = await tts.send_text(reply)
        await tts.disconnect()

        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as exc:
        log.warning("TTS 合成失败，返回纯文本回复: %s", exc)

    return VoiceChatResponse(
        asr_text=asr_text,
        reply=reply,
        audio_base64=audio_b64,
    )
