# 多模态智能语音助手

基于 FastAPI 的多模态智能语音助手服务，支持实时语音聊天、语音识别（ASR）、语音合成（TTS）和大语言模型（LLM）交互。

## 目录

- [项目介绍](#项目介绍)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [API 接口](#api-接口)
- [本地运行步骤](#本地运行步骤)
- [配置说明](#配置说明)

## 项目介绍

本项目是一个多模态智能语音助手服务，提供以下核心功能：

| 功能模块 | 描述 | 状态 |
|---------|------|------|
| **WebSocket 语音聊天** | 实时双向语音交互，支持流式传输 | ✅ 已实现 |
| **HTTP 语音聊天** | 兼容非 WebSocket 客户端，支持完整对话流程 | ✅ 已实现 |
| **LLM 对话** | 调用阿里云百炼大语言模型进行文本对话 | ✅ 已实现 |
| **TTS 语音合成** | 将文本转换为语音 | ✅ 已实现 |
| **ASR 语音识别** | 将语音转换为文本 | ✅ 已实现 |

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           客户端层                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │ Web 浏览器   │    │ 移动端 App  │    │ 其他客户端   │                │
│  │ (WebSocket) │    │  (HTTP/WS)  │    │  (HTTP)     │                │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                │
└─────────┼──────────────────┼──────────────────┼────────────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼────────────────────────┐
│                           API 网关层                                   │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                    FastAPI Application                        │      │
│  │  /ws/voice-chat        /api/chat        /api/health          │      │
│  │  (WebSocket)           (HTTP)           (HTTP)               │      │
│  └───────────────────────────┬──────────────────────────────────┘      │
└───────────────────────────────┼────────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────────┐
│                           服务层                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │  LLM Service│    │  TTS Service│    │  ASR Service│                │
│  │  (大语言模型)│    │  (语音合成) │    │  (语音识别) │                │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                │
└─────────┼──────────────────┼──────────────────┼────────────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼────────────────────────┐
│                        外部服务层                                       │
│                    阿里云百炼 DashScope API                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 模块结构

```
backend/
├── app/
│   ├── api/              # API 路由层
│   │   ├── chat.py       # HTTP 语音聊天接口
│   │   ├── ws.py         # WebSocket 语音聊天接口
│   │   └── health.py     # 健康检查接口
│   ├── services/         # 业务服务层
│   │   ├── llm_service.py    # LLM 服务
│   │   ├── tts_service.py    # TTS 服务
│   │   └── asr_service.py    # ASR 服务
│   ├── core/             # 核心配置
│   │   └── config.py     # 全局配置管理
│   ├── middleware/       # 中间件
│   │   └── error_handler.py  # 全局异常处理
│   ├── utils/            # 工具函数
│   │   └── audio_converter.py # 音频格式转换
│   └── main.py           # 应用入口
├── static/               # 静态资源
├── ffmpeg_temp/          # FFmpeg 工具
├── .env                  # 环境变量配置
├── requirements          # 依赖列表
└── test_*.py             # 测试脚本
```

## 技术栈

| 分类 | 技术 | 版本要求 |
|------|------|----------|
| 后端框架 | FastAPI | >= 0.100 |
| ASGI 服务器 | Uvicorn | >= 0.20 |
| 实时通信 | WebSockets | >= 12.0 |
| 环境管理 | python-dotenv | >= 1.0 |
| 音频处理 | FFmpeg | - |
| 云服务 | 阿里云百炼 DashScope | - |

## API 接口

### HTTP 接口

| 接口路径 | HTTP 方法 | 描述 |
|---------|----------|------|
| `/api/chat` | POST | 语音聊天（兼容非 WebSocket 客户端） |
| `/api/health` | GET | 健康检查 |

### WebSocket 接口

| 接口路径 | 描述 |
|---------|------|
| `/ws/voice-chat` | 实时语音聊天 WebSocket 端点 |

## 本地运行步骤

### 1. 环境准备

确保已安装 Python 3.10+ 和 FFmpeg。

### 2. 安装依赖

```bash
cd backend
pip install -r requirements
```

### 3. 配置环境变量

编辑 `backend/.env` 文件，配置阿里云百炼 API Key：

```env
DASHSCOPE_API_KEY=your_api_key_here
```

### 4. 启动服务

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 访问服务

- 主页面：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

## 配置说明

配置文件 `.env` 支持以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `DASHSCOPE_API_KEY` | str | - | 阿里云百炼 API Key（必填） |
| `DASHSCOPE_BASE_URL` | str | https://dashscope.aliyuncs.com/compatible-mode/v1 | API 基础地址 |
| `LLM_MODEL` | str | qwen-turbo | LLM 模型名称 |
| `LLM_VL_MODEL` | str | qwen-vl-plus | 多模态模型名称 |
| `LLM_TEMPERATURE` | float | 0.7 | 生成温度 |
| `LLM_MAX_TOKENS` | int | 1024 | 最大生成长度 |
| `TTS_VOICE` | str | xiaoxiao | TTS 语音名称 |
| `ASR_MODEL` | str | qwen3-asr-flash-realtime | ASR 模型名称 |
| `HOST` | str | 0.0.0.0 | 服务绑定地址 |
| `PORT` | int | 8000 | 服务端口 |
| `LOG_LEVEL` | str | INFO | 日志级别 |

## 测试脚本

项目包含以下测试脚本：

| 脚本 | 描述 |
|------|------|
| `test_llm_simple.py` | LLM 文本对话测试 |
| `test_llm_tts_stream.py` | LLM + TTS 流式测试 |
| `test_tts_debug.py` | TTS 语音合成调试 |
| `test_model_switch.py` | 模型切换测试 |
| `list_voices.py` | 列出可用语音列表 |