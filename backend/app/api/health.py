"""
健康检查端点

提供 GET /api/health 接口，返回服务状态和各依赖服务的可用性。
"""

import logging
import time
from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings

log = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])

# 应用启动时间戳，用于计算 uptime
_start_time: float = time.time()


def _check_llm() -> dict[str, Any]:
    """检查 LLM 服务配置是否就绪"""
    settings = get_settings()
    if settings.dashscope_api_key:
        return {"status": "ready", "model": settings.llm_model}
    return {"status": "not_configured", "model": settings.llm_model}


def _check_tts() -> dict[str, Any]:
    """检查 TTS 服务配置是否就绪"""
    settings = get_settings()
    return {"status": "ready", "voice": settings.tts_voice}


def _check_asr() -> dict[str, Any]:
    """检查 ASR 服务配置是否就绪"""
    settings = get_settings()
    if settings.dashscope_api_key:
        return {"status": "ready", "model": settings.asr_model}
    return {"status": "not_configured", "model": settings.asr_model}


@router.get("/health", summary="健康检查")
async def health_check() -> dict[str, Any]:
    """
    返回服务健康状态

    检查各依赖服务（LLM / TTS / ASR）是否配置就绪，
    返回运行时长和服务版本信息。
    """
    uptime = int(time.time() - _start_time)

    services = {
        "llm": _check_llm(),
        "tts": _check_tts(),
        "asr": _check_asr(),
    }

    all_ready = all(
        svc.get("status") == "ready" for svc in services.values()
    )

    return {
        "status": "healthy" if all_ready else "degraded",
        "services": services,
        "uptime": uptime,
        "version": "0.2.0",
    }
