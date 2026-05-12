"""
统一配置管理模块

使用 pydantic-settings 的 BaseSettings 从环境变量和 .env 文件读取所有配置，
实现单例模式，全局共享一份配置实例。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用全局配置

    所有字段均从 .env 文件或环境变量读取，优先使用环境变量。
    通过 get_settings() 获取全局单例。
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env") if (Path(__file__).resolve().parent.parent.parent / ".env").exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 阿里云百炼 API ----
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ---- LLM 模型配置 ----
    llm_model: str = "qwen-turbo"
    llm_vl_model: str = "qwen-vl-plus"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1024

    # ---- TTS 配置 ----
    tts_voice: str = "xiaoxiao"

    # ---- ASR 配置 ----
    asr_model: str = "qwen3-asr-flash-realtime"
    asr_ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    asr_language: str = "zh"
    asr_sample_rate: int = 16000

    # ---- 服务运行配置 ----
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    debug: bool = False

    # ---- CORS 配置 ----
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """
    获取全局配置单例

    使用 lru_cache 确保整个应用生命周期内只创建一次 Settings 实例。
    """
    return Settings()
