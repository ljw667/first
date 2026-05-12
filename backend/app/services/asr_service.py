"""
阿里云百炼实时语音识别（ASR）服务模块

通过 WebSocket 协议连接阿里云 DashScope 平台的 Qwen-ASR-Realtime 模型，
使用 Realtime API 协议（session.update / input_audio_buffer.append / session.finish），
实现流式音频识别，支持实时中间结果与最终结果的回调。
"""

import base64
import json
import logging
import uuid
from typing import Any, Callable, Coroutine

import websockets

log = logging.getLogger(__name__)

ASR_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
ASR_MODEL = "qwen3-asr-flash-realtime"


class AliyunASRService:
    """
    阿里云百炼实时语音识别服务

    封装与 DashScope Qwen-ASR-Realtime 的完整交互流程：
    connect → start_transcription → send_audio(循环) → finish_transcription → disconnect

    协议说明：
    - 连接后服务端先发送 session.created 事件
    - 客户端发送 session.update 配置会话参数
    - 客户端通过 input_audio_buffer.append 发送 Base64 编码的音频
    - 服务端返回 conversation.item.input_audio_transcription.text（中间结果）
    - 服务端返回 conversation.item.input_audio_transcription.completed（最终结果）
    - 客户端发送 session.finish 结束会话
    """

    def __init__(self, api_key: str) -> None:
        """
        初始化 ASR 服务

        Args:
            api_key: 阿里云百炼平台 API Key
        """
        self._api_key = api_key
        self._ws: websockets.asyncio.connection.ClientConnection | None = None
        self._connected: bool = False
        self._session_ready: bool = False

        # 外部回调：识别结果回调，签名为 (result_text: str, is_final: bool) -> None
        self.on_result: Callable[[str, bool], Coroutine[Any, Any, None]] | None = None
        # 外部回调：错误回调
        self.on_error: Callable[[str], Coroutine[Any, Any, None]] | None = None

    @property
    def connected(self) -> bool:
        """是否已建立 WebSocket 连接"""
        return self._connected

    @property
    def task_started(self) -> bool:
        """ASR 会话是否已就绪（兼容 ws.py 中的判断）"""
        return self._session_ready

    async def connect(self) -> None:
        """
        建立到阿里云 ASR 服务的 WebSocket 连接

        连接时在 header 中携带 API Key 进行鉴权。
        连接成功后等待服务端返回 session.created 事件。
        """
        if self._connected:
            log.warning("ASR WebSocket 已连接，无需重复连接")
            return

        headers = {
            "Authorization": f"bearer {self._api_key}",
        }

        log.info("正在连接阿里云 ASR 服务: %s", ASR_WS_URL)
        try:
            self._ws = await websockets.connect(
                f"{ASR_WS_URL}?model={ASR_MODEL}",
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=30,
            )
            self._connected = True
            log.info("ASR WebSocket 连接成功")
        except Exception as exc:
            log.error("ASR WebSocket 连接失败: %s", exc)
            raise

    async def start_transcription(
        self,
        format: str = "pcm",
        sample_rate: int = 16000,
        language: str = "zh",
    ) -> None:
        """
        发送 session.update 事件，配置并启动语音识别会话

        连接成功后必须先调用此方法，收到 session.updated 事件后
        才能开始发送音频数据。

        Args:
            format: 音频编码格式，支持 pcm / opus，默认 pcm
            sample_rate: 采样率，支持 16000 / 8000，默认 16000
            language: 语言代码，zh=中文, en=英文, yue=粤语 等，默认 zh
        """
        if not self._connected or self._ws is None:
            raise RuntimeError("ASR WebSocket 尚未连接，请先调用 connect()")

        if self._session_ready:
            log.warning("ASR 会话已就绪，无需重复启动")
            return

        # 先等待服务端的 session.created 事件
        await self._wait_for_session_created()

        # 发送 session.update 配置会话
        session_update_msg: dict[str, Any] = {
            "event_id": uuid.uuid4().hex[:32],
            "type": "session.update",
            "session": {
                "input_audio_format": format,
                "sample_rate": sample_rate,
                "input_audio_transcription": {
                    "language": language,
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.0,
                    "silence_duration_ms": 400,
                },
            },
        }

        await self._ws.send(json.dumps(session_update_msg))
        log.info("已发送 session.update 配置")

        # 等待 session.updated 确认
        await self._wait_for_session_updated()

    async def _wait_for_session_created(self) -> None:
        """等待服务端返回 session.created 事件"""
        if self._ws is None:
            return

        async for raw_message in self._ws:
            event = self._parse_event(raw_message)
            if event is None:
                continue

            event_type = event.get("type", "")

            if event_type == "session.created":
                session_id = event.get("session", {}).get("id", "unknown")
                log.info("ASR 会话已创建, session_id=%s", session_id)
                return

            if event_type == "error":
                error_msg = event.get("error", {}).get("message", "未知错误")
                log.error("ASR 会话创建失败: %s", error_msg)
                raise RuntimeError(f"ASR 会话创建失败: {error_msg}")

            log.warning("等待 session.created 时收到意外事件: %s", event_type)

    async def _wait_for_session_updated(self) -> None:
        """等待服务端返回 session.updated 事件"""
        if self._ws is None:
            return

        async for raw_message in self._ws:
            event = self._parse_event(raw_message)
            if event is None:
                continue

            event_type = event.get("type", "")

            if event_type == "session.updated":
                self._session_ready = True
                log.info("ASR 会话配置已更新，可以开始发送音频")
                return

            if event_type == "error":
                error_msg = event.get("error", {}).get("message", "未知错误")
                log.error("ASR 会话配置失败: %s", error_msg)
                raise RuntimeError(f"ASR 会话配置失败: {error_msg}")

            log.warning("等待 session.updated 时收到意外事件: %s", event_type)

    async def send_audio(self, audio_bytes: bytes) -> None:
        """
        向 ASR 服务发送音频数据

        音频会被 Base64 编码后通过 input_audio_buffer.append 事件发送。
        必须在 start_transcription 成功后调用。

        Args:
            audio_bytes: PCM / Opus 编码的音频二进制数据
        """
        if not self._session_ready or self._ws is None:
            raise RuntimeError("ASR 会话尚未就绪，请先调用 start_transcription()")

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        append_msg: dict[str, Any] = {
            "event_id": uuid.uuid4().hex[:32],
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }

        await self._ws.send(json.dumps(append_msg))
        log.debug("已发送音频数据, 原始长度=%d 字节", len(audio_bytes))

    async def finish_transcription(self) -> None:
        """
        发送 session.finish 事件，通知服务端结束识别会话

        仅发送指令，不等待 session.finished（由后台 listen_for_results 处理），
        避免与后台协程在 recv 上冲突。
        """
        if not self._session_ready or self._ws is None:
            log.warning("ASR 会话未就绪，无需结束")
            return

        finish_msg: dict[str, Any] = {
            "event_id": uuid.uuid4().hex[:32],
            "type": "session.finish",
        }

        try:
            await self._ws.send(json.dumps(finish_msg))
            log.info("已发送 session.finish 事件")
        except Exception as exc:
            log.warning("发送 session.finish 失败: %s", exc)

    async def _drain_until_finished(self) -> None:
        """
        持续接收服务端事件，直到收到 session.finished 或 error

        过程中会将识别结果通过 on_result 回调通知外部。
        """
        if self._ws is None:
            return

        async for raw_message in self._ws:
            event = self._parse_event(raw_message)
            if event is None:
                continue

            event_type = event.get("type", "")
            await self._dispatch_event(event_type, event)

            if event_type == "session.finished":
                log.info("ASR 会话已结束")
                self._session_ready = False
                return

            if event_type == "error":
                error_msg = event.get("error", {}).get("message", "未知错误")
                log.error("ASR 会话错误: %s", error_msg)
                self._session_ready = False
                if self.on_error is not None:
                    await self.on_error(error_msg)
                return

    async def _dispatch_event(self, event_type: str, event: dict[str, Any]) -> None:
        """
        根据事件类型分发处理

        支持的事件类型：
        - conversation.item.input_audio_transcription.text: 中间识别结果
        - conversation.item.input_audio_transcription.completed: 最终识别结果
        - input_audio_buffer.speech_started: VAD 检测到语音开始
        - input_audio_buffer.speech_stopped: VAD 检测到语音结束
        - conversation.item.created: 对话项创建
        - input_audio_buffer.committed: 音频缓冲区已提交
        - error: 错误事件
        """
        if event_type == "conversation.item.input_audio_transcription.text":
            await self._handle_transcription_text(event)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self._handle_transcription_completed(event)

        elif event_type == "input_audio_buffer.speech_started":
            log.debug("VAD 检测到语音开始")

        elif event_type == "input_audio_buffer.speech_stopped":
            log.debug("VAD 检测到语音结束")

        elif event_type in ("conversation.item.created", "input_audio_buffer.committed"):
            log.debug("收到事件: %s", event_type)

        elif event_type not in ("session.finished", "error"):
            log.warning("收到未知事件类型: %s", event_type)

    async def _handle_transcription_text(self, event: dict[str, Any]) -> None:
        """
        处理中间识别结果事件

        事件包含 text（已确认文本）和 stash（临时草稿），
        拼接后为当前最完整的预览句子。
        """
        text: str = event.get("text", "")
        stash: str = event.get("stash", "")
        full_text = text + stash

        if full_text:
            log.debug("中间识别结果: text=%s, stash=%s", text, stash)
            if self.on_result is not None:
                await self.on_result(full_text, False)

    async def _handle_transcription_completed(self, event: dict[str, Any]) -> None:
        """
        处理最终识别结果事件

        事件包含 transcript 字段，为整句话的最终识别文本。
        """
        transcript: str = event.get("transcript", "")
        if transcript:
            log.info("最终识别结果: %s", transcript)
            if self.on_result is not None:
                await self.on_result(transcript, True)

    async def receive_results(self) -> None:
        """
        持续接收识别结果的后台协程

        适用于在发送音频的同时并行接收结果。
        在 start_transcription 成功后调用，
        会一直运行直到连接断开或会话结束。
        """
        if self._ws is None:
            return

        try:
            async for raw_message in self._ws:
                event = self._parse_event(raw_message)
                if event is None:
                    continue

                event_type = event.get("type", "")
                await self._dispatch_event(event_type, event)

                if event_type == "session.finished":
                    log.info("ASR 会话已结束")
                    self._session_ready = False
                    break

                if event_type == "error":
                    error_msg = event.get("error", {}).get("message", "未知错误")
                    log.error("ASR 会话错误: %s", error_msg)
                    self._session_ready = False
                    if self.on_error is not None:
                        await self.on_error(error_msg)
                    break

        except websockets.exceptions.ConnectionClosed as exc:
            log.warning("ASR WebSocket 连接已关闭: code=%s, reason=%s", exc.code, exc.reason)
            self._connected = False
            self._session_ready = False

    async def listen_for_results(self) -> None:
        """
        持续监听 ASR 识别结果的后台协程

        与 receive_results 功能一致，作为更语义化的别名，
        适用于通过 asyncio.create_task 在后台运行。
        """
        await self.receive_results()

    async def disconnect(self) -> None:
        """
        断开与 ASR 服务的 WebSocket 连接

        直接关闭连接，不等待服务端确认（因为后台 listen_for_results
        可能正在占用 recv，调用 finish_transcription 会冲突）。
        """
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as exc:
                log.warning("关闭 ASR WebSocket 时出错: %s", exc)

            self._ws = None

        self._connected = False
        self._session_ready = False
        log.info("ASR WebSocket 连接已断开")

    @staticmethod
    def _parse_event(raw_message: str | bytes) -> dict[str, Any] | None:
        """
        解析服务端返回的 JSON 事件

        Args:
            raw_message: WebSocket 接收到的原始消息

        Returns:
            解析后的事件字典，解析失败返回 None
        """
        try:
            if isinstance(raw_message, bytes):
                log.debug("收到二进制消息, 长度=%d（ASR 服务不应返回二进制帧）", len(raw_message))
                return None
            return json.loads(raw_message)
        except json.JSONDecodeError:
            log.warning("无法解析 ASR 事件: %s", str(raw_message)[:200])
            return None
