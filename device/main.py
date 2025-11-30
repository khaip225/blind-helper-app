"""
Main MQTT Application
=====================
"""

import time
import sys
import select
import asyncio
from module.camera.camera_direct import CameraDirect
from mqtt import MQTTClient, VoiceMQTT, GPSMQTT
from log import setup_logger
from module.voice_speaker import VoiceSpeaker
from mcp_server.server import mcp
from config import TOPICS
# from module.gps_manager import GPSManager
logger = setup_logger(__name__)
from module.obstacle_detection import ObstacleDetectionSystem
from module.lane_segmentation import LaneSegmentation

def main():
    """Main application loop"""
    # Initialize MQTT client
    mqtt_client = MQTTClient()
    mqtt_client.connect()
    
    # # # --- Chạy hệ thống phát hiện vật cản ---
    # obstacle_system = ObstacleDetectionSystem()
    # obstacle_system.run()
    
    speaker = VoiceSpeaker("USB Audio Device")

    # Initialize services
    voice = VoiceMQTT(mqtt_client)
    voice.start_continuous_listening()
    
    # Link VoiceMQTT với WebRTC Manager để có thể pause/resume khi có cuộc gọi
    mqtt_client.handler.set_voice_mqtt(voice)
    logger.info("✅ VoiceMQTT linked to WebRTC - will pause during calls")
    
    camera = CameraDirect()
    # lane_segmentation = LaneSegmentation()
    # lane_segmentation.run()
    # status = DeviceStatus(mqtt_client)
    
    # gps_system = GPSManager(mqtt_client)
    # gps_system.run()

    # gps = GPSMQTT(mqtt_client)
    # gps.publish_gps(qos=1)
    
    mcp.run(transport='sse')
    
    mqtt_client.publish(TOPICS['device_ping'], {"data": "PING"})
    
    # Publish initial device info
    print("Device started. Press Ctrl+C to exit.")
    print("🆘 Press ENTER to initiate SOS emergency call")
    
    try:
        # Get event loop for async operations
        loop = asyncio.get_event_loop()
        
        while True:
            # Check for keyboard input (non-blocking on Linux/Mac)
            if sys.platform != "win32":
                # Unix-like systems (Linux, Mac)
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1)
                    if key == '\n':  # Enter key
                        logger.info("🆘 ENTER pressed - initiating SOS call...")
                        # Trigger SOS call asynchronously
                        loop.run_until_complete(mqtt_client.handler.initiate_sos_call())
            else:
                # Windows - use msvcrt
                try:
                    import msvcrt
                    if msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key == b'\r':  # Enter key on Windows
                            logger.info("🆘 ENTER pressed - initiating SOS call...")
                            # Trigger SOS call asynchronously
                            loop.run_until_complete(mqtt_client.handler.initiate_sos_call())
                except ImportError:
                    pass  # msvcrt not available
            
            time.sleep(0.1)  # Reduce sleep time to make input more responsive
            
    except KeyboardInterrupt as e:
        logger.error(f"Lỗi: {e}", exc_info=True)
        logger.info("Dừng hệ thống...")
        # obstacle_system.stop()
        camera.stop()
        voice.stop()
        mqtt_client.disconnect()
        # lane_segmentation.stop()

if __name__ == "__main__":
    main()
