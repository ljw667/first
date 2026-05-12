import asyncio
import traceback
from app.services.tts_service import BailianTTSService

async def main():
    try:
        print("开始测试 TTS...")
        
        tts = BailianTTSService(voice="xiaoxiao")
        print("TTS 实例创建成功，voice=" + tts.voice)
        
        print("连接 TTS 服务...")
        await tts.connect()
        print("TTS 连接状态: " + str(tts.connected))
        
        text = "你好，我是智能语音助手"
        print("合成语音: '" + text + "'")
        
        audio = await tts.send_text(text)
        
        if audio:
            print("成功！音频长度: " + str(len(audio)) + " 字节")
            with open("test_output.wav", "wb") as f:
                f.write(audio)
            print("文件已保存: test_output.wav")
        else:
            print("失败：返回空音频")
        
        await tts.disconnect()
        print("测试完成")
        
    except Exception as e:
        print("测试失败: " + str(e))
        traceback.print_exc()

asyncio.run(main())