"""
WebSocket 语音聊天端点与消息分发模块

处理 /ws/voice-chat 路径的 WebSocket 连接，
支持文本帧（JSON）和二进制帧（音频数据）的接收与分发，
集成阿里云百炼实时语音识别（ASR）服务、大模型对话（LLM）服务与语音合成（TTS）服务。
"""

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.services.asr_service import AliyunASRService
from app.services.llm_service import QwenLLMService
from app.services.tts_service import BailianTTSService
from app.utils.audio_converter import convert_to_pcm, detect_audio_format

log = logging.getLogger(__name__)

VALID_STATES = {"idle", "listening", "thinking", "speaking"}

# 当前连接的 ASR 实例（模块级全局变量）
current_asr: AliyunASRService | None = None

# 当前连接的 LLM 实例（模块级全局变量）
current_llm: QwenLLMService | None = None

# 当前正在进行的 LLM 流式生成任务（用于打断时取消）
current_llm_task: asyncio.Task | None = None

# 当前连接的 TTS 实例（模块级全局变量）
current_tts: BailianTTSService | None = None

# 当前会话的音频片段缓存
audio_chunks_cache: list[bytes] = []

# 当前音频格式
current_audio_format: str = "webm"

# 当前会话暂存的图片 base64 数据（用户上传图片后暂存，LLM 处理完后清空）
current_image_base64: str | None = None


async def send_json(websocket: WebSocket, data: dict[str, Any]) -> None:
    """向客户端发送文本帧（JSON）"""
    await websocket.send_json(data)


async def send_audio(websocket: WebSocket, audio_bytes: bytes) -> None:
    """向客户端发送二进制音频帧"""
    await websocket.send_bytes(audio_bytes)



async def _initialize_services(websocket: WebSocket, api_key: str) -> bool:
    """
    公共的服务初始化逻辑：创建 ASR、LLM、TTS 实例并建立连接。

    被 handle_session_start 和 reinitialize_services 复用，
    避免初始化代码重复。

    返回:
        True  - 全部初始化成功
        False - 任一服务初始化失败（已向前端发送 error 消息）
    """
    global current_asr, current_llm, current_tts

    # 实例化 ASR 服务
    current_asr = AliyunASRService(api_key=api_key)

    # 设置识别结果回调：将 ASR 结果推送给前端，最终结果触发 LLM 对话
    async def _on_asr_result(text: str, is_final: bool) -> None:
        global current_llm_task, current_image_base64

        msg_type = "asr_final" if is_final else "asr_partial"
        await send_json(websocket, {
            "type": msg_type,
            "payload": {"text": text, "is_final": is_final},
        })

        # 收到最终识别结果时，调用 LLM 进行流式对话
        if is_final and current_llm is not None:
            # 如果已有 LLM 任务在运行，先取消
            if current_llm_task is not None and not current_llm_task.done():
                current_llm_task.cancel()
                log.info("取消前一个 LLM 流式任务")

            # 捕获当前图片数据（在闭包中使用）
            image_to_send = current_image_base64
            # 有图片时立即清空，避免重复使用
            if image_to_send:
                current_image_base64 = None
                log.info("暂存图片已取出并清空")

            # LLM 流式生成协程
            async def _stream_llm_response(user_text: str, image_b64: str | None) -> None:
                global current_llm_task
                try:
                    is_first = True
                    llm_response_text = ""

                    # 专模专用：有图片走多模态模型，无图片走纯文本模型
                    if image_b64:
                        stream = current_llm.chat_stream_with_image(user_text, image_b64)
                    else:
                        stream = current_llm.chat_stream(user_text)

                    async for chunk in stream:
                        await send_json(websocket, {
                            "type": "llm_chunk",
                            "payload": {
                                "text": chunk,
                                "sentence_index": 0,
                                "is_first": is_first,
                            },
                        })
                        is_first = False
                        llm_response_text += chunk

                    # 流式生成结束，发送 llm_done 消息
                    await send_json(websocket, {
                        "type": "llm_done",
                        "payload": {"total_sentences": 1},
                    })

                    # LLM 流结束后，将完整文本发送给 TTS 合成语音
                    if current_tts is not None and llm_response_text:
                        try:
                            audio_bytes = await current_tts.send_text(llm_response_text)
                            if audio_bytes:
                                await send_audio(websocket, audio_bytes)
                                log.info("TTS 音频已推送给前端, 长度=%d 字节", len(audio_bytes))
                            else:
                                log.warning("TTS 返回空音频")
                                await send_json(websocket, {
                                    "type": "tts_error",
                                    "payload": {"detail": "TTS 返回空音频"},
                                })
                        except Exception as exc:
                            log.warning("TTS 合成失败: %s", exc)
                            await send_json(websocket, {
                                "type": "tts_error",
                                "payload": {"detail": f"TTS 合成失败: {exc}"},
                            })

                except asyncio.CancelledError:
                    log.info("LLM 流式生成被取消")
                except Exception as exc:
                    log.error("LLM 流式生成失败: %s", exc)
                    await send_json(websocket, {
                        "type": "error",
                        "detail": f"LLM 生成失败: {exc}",
                    })
                finally:
                    current_llm_task = None

            # 启动后台任务进行 LLM 流式生成
            current_llm_task = asyncio.create_task(_stream_llm_response(text, image_to_send))
            log.info("LLM 流式生成任务已启动, user_text=%s, has_image=%s", text[:100], image_to_send is not None)

    current_asr.on_result = _on_asr_result

    # 设置错误回调
    async def _on_asr_error(error_msg: str) -> None:
        await send_json(websocket, {"type": "error", "detail": f"ASR 错误: {error_msg}"})

    current_asr.on_error = _on_asr_error

    # 建立 ASR WebSocket 连接
    try:
        await current_asr.connect()
    except Exception as exc:
        log.error("ASR 连接失败: %s", exc)
        await send_json(websocket, {"type": "error", "detail": "ASR 服务连接失败"})
        current_asr = None
        return False

    # 启动 ASR 识别任务
    try:
        await current_asr.start_transcription(
            format="pcm",
            sample_rate=16000,
            language="zh",
        )
    except Exception as exc:
        log.error("ASR 任务启动失败: %s", exc)
        await send_json(websocket, {"type": "error", "detail": "ASR 任务启动失败"})
        await current_asr.disconnect()
        current_asr = None
        return False

    # 创建后台协程持续监听 ASR 识别结果
    asyncio.create_task(current_asr.receive_results())
    log.info("ASR 后台监听协程已启动")

    # 初始化 LLM 服务（纯文本模型 qwen-turbo；多模态请求由 chat_stream_with_image 使用 qwen-vl-plus）
    current_llm = QwenLLMService(api_key=api_key, model="qwen-turbo")
    log.info("LLM 服务已初始化, model=qwen-turbo")

    # 初始化 TTS 服务并建立连接
    try:
        current_tts = BailianTTSService(api_key=api_key, voice="xiaoxiao")
        await current_tts.connect()
        log.info("TTS 服务已初始化并连接成功, voice=xiaoxiao")
    except Exception as exc:
        log.error("TTS 服务初始化失败: %s", exc)
        await send_json(websocket, {"type": "error", "detail": "TTS 服务连接失败"})
        current_tts = None
        return False

    return True


async def handle_session_start(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """
    处理会话开始消息
    从环境变量读取 API Key，调用 _initialize_services 完成 ASR/LLM/TTS 初始化。
    """
    log.info("收到会话开始信号: %s", data)

    # 从环境变量读取阿里云百炼 API Key（由 main.py 中 load_dotenv 加载 .env）
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        log.error("未配置 DASHSCOPE_API_KEY 环境变量")
        await send_json(websocket, {"type": "error", "detail": "服务端未配置 ASR API Key"})
        return

    # 调用公共初始化函数
    await _initialize_services(websocket, api_key)


async def reinitialize_services(websocket: WebSocket, api_key: str) -> bool:
    """
    打断后重建 ASR/LLM/TTS 服务，使后端能够立即接收新指令。

    流程：
      1. 调用 _initialize_services 重新创建并连接所有服务
      2. 初始化成功后向前端发送 interrupt_ack 消息，通知前端可开始新录音

    返回:
        True  - 重建成功，前端可继续交互
        False - 重建失败（已向前端发送 error 消息）
    """
    log.info("开始重建 ASR/LLM/TTS 服务...")

    success = await _initialize_services(websocket, api_key)
    if not success:
        log.error("重建服务失败，无法恢复交互")
        return False

    # 初始化成功，向前端发送打断确认，通知前端可开始新录音
    await send_json(websocket, {
        "type": "interrupt_ack",
        "payload": {"status": "ready"},
    })
    log.info("服务重建完成，已发送 interrupt_ack，前端可开始新录音")
    return True


async def handle_audio_start(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """处理音频开始消息"""
    global audio_chunks_cache, current_audio_format
    log.info("收到音频开始信号")
    connection_state["status"] = "listening"

    audio_chunks_cache = []
    current_audio_format = data.get("format", "webm")
    log.info(f"音频格式: {current_audio_format}")


async def handle_audio_end(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """处理音频结束消息"""
    global current_asr, audio_chunks_cache, current_audio_format

    log.info("收到音频结束信号")
    connection_state["status"] = "thinking"

    if audio_chunks_cache:
        full_audio = b"".join(audio_chunks_cache)
        log.info(f"合并音频片段: {len(audio_chunks_cache)} 个片段，总长度: {len(full_audio)} 字节")

        detected_format = detect_audio_format(current_audio_format)
        pcm_audio = convert_to_pcm(full_audio, detected_format)

        if pcm_audio:
            if current_asr is not None and current_asr.task_started:
                try:
                    await current_asr.send_audio(pcm_audio)
                    log.info("PCM 音频已发送到 ASR")
                except Exception as exc:
                    log.warning("发送音频到 ASR 失败: %s", exc)
        else:
            log.error("音频转换失败")

    audio_chunks_cache = []

    if current_asr is not None and current_asr.task_started:
        try:
            await current_asr.finish_transcription()
            log.info("ASR 识别任务已结束")
        except Exception as exc:
            log.warning("结束 ASR 任务时出错: %s", exc)


async def handle_interrupt(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """
    处理打断消息，实现全双工低延迟交互。

    流程：
      1. 取消正在进行的 LLM 流式生成任务
      2. 清理旧的 LLM/TTS/ASR 实例
      3. 调用 reinitialize_services 重建所有服务
      4. 重建成功后将状态切换为 listening，等待前端新录音
    """
    global current_asr, current_llm, current_llm_task, current_tts, current_image_base64

    log.info("收到打断信号")

    # 打断时取消正在进行的 LLM 流式生成
    if current_llm_task is not None and not current_llm_task.done():
        current_llm_task.cancel()
        log.info("LLM 流式生成任务已取消")
    current_llm_task = None

    # 打断时清理 LLM 实例
    current_llm = None
    log.info("LLM 实例已清理")

    # 打断时清空暂存图片
    current_image_base64 = None
    log.info("暂存图片已清空")

    # 打断时断开 TTS 连接
    if current_tts is not None:
        try:
            await current_tts.disconnect()
        except Exception as exc:
            log.warning("打断时断开 TTS 连接出错: %s", exc)
        current_tts = None
        log.info("打断处理完成，TTS 连接已断开")

    # 打断时断开 ASR 连接
    if current_asr is not None:
        try:
            await current_asr.disconnect()
        except Exception as exc:
            log.warning("打断时断开 ASR 连接出错: %s", exc)
        current_asr = None
        log.info("打断处理完成，ASR 连接已断开")

    # 读取 API Key，用于重建服务
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        log.error("打断后重建服务失败：未配置 DASHSCOPE_API_KEY")
        await send_json(websocket, {"type": "error", "detail": "服务端未配置 API Key，无法恢复"})
        connection_state["status"] = "idle"
        return

    # 重建 ASR/LLM/TTS 服务，使后端能立即接收新指令
    success = await reinitialize_services(websocket, api_key)
    if success:
        # 重建成功，进入 listening 状态，等待前端新录音
        connection_state["status"] = "listening"
        log.info("打断处理完成，状态已切换为 listening，等待前端新录音")
    else:
        # 重建失败，回退到 idle 状态
        connection_state["status"] = "idle"
        log.warning("打断后服务重建失败，状态回退为 idle")


async def handle_tts_audio(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """处理前端 TTS 音频播放确认消息"""
    log.debug("收到 TTS 音频确认消息: %s", data)


async def handle_image_upload(
    data: dict[str, Any],
    connection_state: dict[str, str],
    websocket: WebSocket,
) -> None:
    """
    处理图片上传消息

    接收前端发来的图片 base64 数据，暂存到 current_image_base64，
    后续 ASR 最终结果触发 LLM 时会一并传入图片。
    """
    global current_image_base64

    payload = data.get("payload", {})
    image_b64 = payload.get("image_base64")

    if not image_b64:
        log.warning("图片上传消息缺少 image_base64 字段")
        await send_json(websocket, {
            "type": "image_ack",
            "payload": {"status": "error", "detail": "缺少 image_base64 字段"},
        })
        return

    current_image_base64 = image_b64
    log.info("图片已暂存, base64 长度=%d", len(image_b64))

    await send_json(websocket, {
        "type": "image_ack",
        "payload": {"status": "ok"},
    })


# 消息类型 → 处理函数 的映射表
_MESSAGE_HANDLERS: dict[str, Any] = {
    "session_start": handle_session_start,
    "audio_start": handle_audio_start,
    "audio_end": handle_audio_end,
    "interrupt": handle_interrupt,
    "tts_audio": handle_tts_audio,
    "image_upload": handle_image_upload,
}


async def receive_handler(websocket: WebSocket, connection_state: dict[str, str]) -> None:
    """
    消息接收与分发协程

    循环接收 WebSocket 消息，根据帧类型和消息中的 type 字段
    分发给对应的异步处理函数。
    """
    while True:
        message = await websocket.receive()

        # 处理连接断开消息
        msg_type_raw = message.get("type", "")
        if msg_type_raw == "websocket.disconnect":
            log.info("收到 WebSocket 断开消息")
            break

        if "text" in message:
            # 文本帧：按 JSON 解析并分发
            try:
                data: dict[str, Any] = json.loads(message["text"])
            except json.JSONDecodeError:
                log.warning("收到无法解析的文本帧: %s", message["text"][:200])
                await send_json(websocket, {"type": "error", "detail": "无效的 JSON 格式"})
                continue

            msg_type: str | None = data.get("type")
            if msg_type is None:
                log.warning("消息缺少 type 字段: %s", data)
                await send_json(websocket, {"type": "error", "detail": "消息缺少 type 字段"})
                continue

            handler = _MESSAGE_HANDLERS.get(msg_type)
            if handler is None:
                log.warning("未知的消息类型: %s", msg_type)
                await send_json(websocket, {"type": "error", "detail": f"未知的消息类型: {msg_type}"})
                continue

            log.debug("分发消息: type=%s", msg_type)
            await handler(data, connection_state, websocket)

        elif "bytes" in message:
            # 二进制帧：音频数据，缓存起来等待音频结束后统一处理
            audio_data: bytes = message["bytes"]
            log.debug("收到音频二进制帧, 长度: %d 字节", len(audio_data))

            audio_chunks_cache.append(audio_data)
            log.debug(f"已缓存 {len(audio_chunks_cache)} 个音频片段")
        else:
            log.warning("收到未知类型的 WebSocket 帧")


async def voice_chat_endpoint(websocket: WebSocket) -> None:
    """
    /ws/voice-chat 的 WebSocket 端点处理函数

    管理连接生命周期：握手、消息分发、异常处理与状态清理。
    """
    global current_asr, current_llm, current_llm_task, current_tts, current_image_base64

    # WebSocket 握手
    await websocket.accept()
    log.info("WebSocket 连接已建立")

    # 每个连接维护独立的状态字典
    connection_state: dict[str, str] = {"status": "idle"}

    try:
        await receive_handler(websocket, connection_state)
    except WebSocketDisconnect:
        log.info("客户端主动断开连接")
    except Exception as exc:
        log.exception("WebSocket 连接异常: %s", exc)
    finally:
        # 取消正在进行的 LLM 流式生成任务
        if current_llm_task is not None and not current_llm_task.done():
            current_llm_task.cancel()
            log.info("LLM 流式生成任务已取消")
        current_llm_task = None

        # 清理 LLM 实例
        current_llm = None
        log.info("LLM 实例已清理")

        # 清理暂存图片
        current_image_base64 = None
        log.info("暂存图片已清理")

        # 清理 TTS 实例
        if current_tts is not None:
            try:
                await current_tts.disconnect()
            except Exception as exc:
                log.warning("清理 TTS 实例时出错: %s", exc)
            current_tts = None
            log.info("TTS 实例已清理")

        # 清理 ASR 实例
        if current_asr is not None:
            try:
                await current_asr.disconnect()
            except Exception as exc:
                log.warning("清理 ASR 实例时出错: %s", exc)
            current_asr = None
            log.info("ASR 实例已清理")

        # 清理连接状态
        connection_state["status"] = "idle"
        log.info("连接状态已清理，WebSocket 连接关闭")
