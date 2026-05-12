import asyncio
import edge_tts

async def list_voices():
    """列出所有可用的中文发音人"""
    voices = await edge_tts.list_voices()
    print("可用的中文发音人:")
    for voice in voices:
        if voice["Locale"].startswith("zh"):
            print(f"  {voice['Locale']} - {voice['Name']} ({voice['Gender']})")

asyncio.run(list_voices())