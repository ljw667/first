"""
Edge TTS 语音合成服务模块（免费）

使用 Microsoft Edge 浏览器的语音合成服务，完全免费。
"""

import asyncio
import logging

import edge_tts

log = logging.getLogger(__name__)

# Edge TTS 可用的中文发音人
CHINESE_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",    # 晓晓（女）- 推荐
    "xiaoyi": "zh-CN-XiaoyiNeural",        # 小艺（女）
    "yunjian": "zh-CN-YunjianNeural",      # 云健（男）
    "yunxi": "zh-CN-YunxiNeural",          # 云希（男）
    "yunxia": "zh-CN-YunxiaNeural",        # 云夏（男）
    "yunyang": "zh-CN-YunyangNeural",      # 云阳（男）
    "xiaobei": "zh-CN-liaoning-XiaobeiNeural",  # 小北（女，辽宁话）
    "xiaoni": "zh-CN-shaanxi-XiaoniNeural",     # 小尼（女，陕西话）
}


class BailianTTSService:
    """
    Edge TTS 语音合成服务（兼容原有接口）

    使用 Microsoft Edge 浏览器的语音合成服务，完全免费。
    """

    def __init__(self, api_key: str = "", voice: str = "xiaoxiao") -> None:
        """
        初始化 TTS 服务

        Args:
            api_key: 预留参数（Edge TTS 不需要 API Key）
            voice: 发音人名称，默认 xiaoyun
        """
        self._voice_name = CHINESE_VOICES.get(voice, "zh-CN-XiaoyunNeural")
        self._sample_rate = 16000
        self._connected = False

    @property
    def connected(self) -> bool:
        """是否已初始化"""
        return self._connected

    @property
    def task_started(self) -> bool:
        """是否有合成任务在进行中"""
        return True

    @property
    def voice(self) -> str:
        """当前发音人名称"""
        return self._voice_name

    async def connect(self) -> None:
        """初始化服务（Edge TTS 无需真正连接）"""
        self._connected = True
        log.info("Edge TTS 服务已初始化, voice=%s", self._voice_name)

    async def send_text(self, text: str) -> bytes:
        """
        发送文本给 TTS 服务进行合成

        Args:
            text: 要合成为语音的文本

        Returns:
            PCM 音频二进制数据（16kHz, 16-bit, mono）
        """
        if not self._connected:
            raise RuntimeError("TTS 服务尚未初始化，请先调用 connect()")

        if not text.strip():
            log.warning("空文本，跳过 TTS 合成")
            return b""

        try:
            communicate = edge_tts.Communicate(text, self._voice_name)
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            
            log.debug("Edge TTS 合成成功, 音频长度=%d 字节", len(audio_bytes))
            return audio_bytes
        except Exception as exc:
            log.error("Edge TTS 合成异常: %s", exc)
            raise

    async def flush(self) -> None:
        """无需 flush，空实现保持接口一致"""
        pass

    async def receive_audio(self) -> bytes:
        """返回空字节（保持接口一致）"""
        return b""

    async def disconnect(self) -> None:
        """断开连接（Edge TTS 无需断开）"""
        self._connected = False
        log.info("Edge TTS 服务已断开")