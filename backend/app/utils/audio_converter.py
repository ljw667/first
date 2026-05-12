"""
音频格式转换工具

提供从 WebM/Opus 到 PCM/Opus 的转换功能，适配前端 MediaRecorder 录制的格式与后端 ASR 服务需求。
"""

import io
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
    
    ffmpeg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'ffmpeg.exe')
    ffprobe_path = os.path.join(os.path.dirname(__file__), '..', '..', 'ffprobe.exe')
    
    if os.path.exists(ffmpeg_path):
        AudioSegment.converter = ffmpeg_path
        log.info(f"使用本地 ffmpeg: {ffmpeg_path}")
    else:
        log.warning(f"未找到本地 ffmpeg: {ffmpeg_path}")
    
    if os.path.exists(ffprobe_path):
        AudioSegment.ffprobe = ffprobe_path
        log.info(f"使用本地 ffprobe: {ffprobe_path}")
    else:
        log.warning(f"未找到本地 ffprobe: {ffprobe_path}")
except ImportError:
    HAS_PYDUB = False
    log.warning("pydub 未安装，音频转换功能受限")


def convert_to_pcm(audio_bytes: bytes, input_format: str = "webm") -> Optional[bytes]:
    """
    将音频数据转换为 PCM 格式（16kHz, 16-bit, mono）
    
    Args:
        audio_bytes: 原始音频数据
        input_format: 输入格式，支持 webm, ogg, wav
        
    Returns:
        PCM 格式的音频字节数据（纯PCM，无WAV头），转换失败返回 None
    """
    if not HAS_PYDUB:
        log.error("pydub 未安装，无法进行音频转换")
        return None
    
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=input_format)
        
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        
        pcm_bytes = audio.raw_data
        log.debug(f"音频转换完成: {len(audio_bytes)} bytes -> {len(pcm_bytes)} bytes (PCM)")
        log.debug(f"音频参数: 采样率={audio.frame_rate}, 通道数={audio.channels}, 位深度={audio.sample_width * 8}")
        return pcm_bytes
    
    except Exception as exc:
        log.error(f"音频转换失败: {exc}")
        return None


def detect_audio_format(mime_type: str) -> str:
    """
    从 MIME 类型推断音频格式
    
    Args:
        mime_type: 前端发送的 MIME 类型
        
    Returns:
        pydub 支持的格式字符串
    """
    if mime_type is None:
        return "webm"
    
    mime_type = mime_type.lower()
    
    if "webm" in mime_type:
        return "webm"
    elif "ogg" in mime_type:
        return "ogg"
    elif "wav" in mime_type:
        return "wav"
    else:
        log.warning(f"未知的 MIME 类型: {mime_type}，默认使用 webm")
        return "webm"
