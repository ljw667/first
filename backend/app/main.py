"""
FastAPI 应用入口

注册所有路由（HTTP + WebSocket），配置 CORS 中间件、
全局异常处理中间件，管理应用生命周期。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.api.ws import voice_chat_endpoint
from app.core.config import get_settings
from app.middleware.error_handler import ErrorHandlerMiddleware

# 加载 .env 文件（项目根目录/backend/.env），如果存在的话
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


# ---- 日志配置 ----
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


# ---- 生命周期管理 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    startup: 初始化资源、打印配置摘要
    shutdown: 清理资源
    """
    log.info("应用启动完成")
    log.info("配置摘要: host=%s, port=%d, llm_model=%s, tts_voice=%s",
             settings.host, settings.port, settings.llm_model, settings.tts_voice)
    yield
    log.info("应用正在关闭")


# ---- 创建 FastAPI 实例 ----
app = FastAPI(
    title="多模态智能语音助手",
    version="0.2.0",
    lifespan=lifespan,
)


# ---- 注册中间件（顺序：后注册先执行） ----

# 全局异常处理中间件（最外层，捕获所有异常）
app.add_middleware(ErrorHandlerMiddleware)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# ---- 注册路由 ----

# HTTP API 路由（/api 前缀）
app.include_router(api_router, prefix="/api")

# WebSocket 路由
app.websocket_route("/ws/voice-chat")(voice_chat_endpoint)


# ---- 静态文件与默认页面 ----

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def read_root():
    """默认路由返回前端页面"""
    return FileResponse("static/index.html")
