import asyncio
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from app.services.llm_service import QwenLLMService
from app.services.tts_service import BailianTTSService
import websockets
import json
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

async def main():
    try:
        print("Connecting to backend WebSocket...")
        async with websockets.connect("ws://localhost:8000/ws/voice-chat") as ws:
            print("WebSocket connected")
            
            print("Sending session_start...")
            await ws.send(json.dumps({"type": "session_start", "payload": {}}))
            print("session_start sent")
            
            llm = QwenLLMService(api_key=API_KEY)
            tts = BailianTTSService(voice="xiaoxiao")
            await tts.connect()
            print("LLM and TTS initialized")
            
            print("LLM generating...")
            full = ""
            async for chunk in llm.chat_stream("你好，介绍一下你自己"):
                full += chunk
                print(chunk, end="", flush=True)
            print("\nLLM complete")
            
            print("TTS synthesizing...")
            audio = await tts.send_text(full)
            
            if audio:
                await ws.send(audio)
                print("Pushed " + str(len(audio)) + " bytes audio")
            else:
                print("TTS returned empty audio")
            
            await tts.disconnect()
            print("Test complete")
            
    except Exception as e:
        print("Test failed: " + str(e))
        import traceback
        traceback.print_exc()

asyncio.run(main())