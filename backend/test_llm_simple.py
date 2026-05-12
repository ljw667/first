import asyncio
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

async def main():
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        print("API Key loaded: " + (api_key[:10] + "..." if api_key else "NOT FOUND"))
        
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        print("Calling LLM with Chinese...")
        response = await client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": "你好，介绍一下你自己"}],
            stream=False,
        )
        
        print("Response: " + response.choices[0].message.content)
        
    except Exception as e:
        print("Error: " + str(e))
        import traceback
        traceback.print_exc()

asyncio.run(main())