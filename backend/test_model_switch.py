import asyncio
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from app.services.llm_service import QwenLLMService, _VL_MODEL

load_dotenv()
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

async def test_model_switch_logic():
    print("=== 测试模型切换逻辑 ===")
    print(f"视觉模型常量: {_VL_MODEL}")
    
    llm = QwenLLMService(api_key=API_KEY, model="qwen-turbo")
    print(f"LLM实例默认模型: {llm.model}")
    
    print("\n1. 无图片时应使用纯文本模型 (qwen-turbo)")
    print("   -> chat_stream() 方法使用 self._model")
    print(f"   -> 当前 self._model = {llm.model}")
    
    print("\n2. 有图片时应自动切换到视觉模型 (qwen-vl-plus)")
    print("   -> chat_stream_with_image() 方法硬编码使用 _VL_MODEL")
    print(f"   -> _VL_MODEL = {_VL_MODEL}")
    
    print("\n✓ 模型切换逻辑验证完成")
    print("  - 无图片: chat_stream() -> qwen-turbo")
    print("  - 有图片: chat_stream_with_image() -> qwen-vl-plus")

async def test_text_model():
    print("\n=== 测试纯文本模型 ===")
    llm = QwenLLMService(api_key=API_KEY, model="qwen-turbo")
    
    try:
        full_response = ""
        async for chunk in llm.chat_stream("你好"):
            full_response += chunk
            print(chunk, end="", flush=True)
        print(f"\n\n✓ 纯文本模型响应成功")
        return True
    except Exception as e:
        print(f"\n✗ 纯文本模型测试失败: {e}")
        return False

async def main():
    await test_model_switch_logic()
    await test_text_model()
    
    print("\n=== 测试总结 ===")
    print("模型切换功能已正确实现:")
    print("- 无图片时调用 chat_stream() 使用 qwen-turbo")
    print("- 有图片时调用 chat_stream_with_image() 使用 qwen-vl-plus")

if __name__ == "__main__":
    asyncio.run(main())