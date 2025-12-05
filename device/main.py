"""
Main MQTT Application
=====================
"""
from module.camera.camera_direct import CameraDirect
from mqtt import MQTTClient, VoiceMQTT, GPSMQTT
from log import setup_logger
from module.voice_speaker import VoiceSpeaker
from mcp_server.server import mcp
from config import TOPICS
from module.gps_manager import GPSManager
from module.gps import GPSService
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
    
    mcp.run(transport='sse')
    #gps_service = GPSService()
    # gps_service.run()
    
    # # MQTT GPS publisher
    # gps = GPSMQTT(mqtt_client)
    # gps.publish_gps(qos=1)
    
    
    mqtt_client.publish(TOPICS['device_ping'], {"data": "PING"})
    
    # # Publish initial device info
    # logger.info("=" * 60)
    # logger.info("Device started successfully!")
    # logger.info("SOS FEATURE: Type 'sos' and press ENTER to initiate emergency call")
    # logger.info("=" * 60)
    # sys.stdout.flush()
    
    # # Set stdin to non-blocking mode for SSH compatibility
    # old_settings = termios.tcgetattr(sys.stdin)
    # input_buffer = ""
    
    # try:
    #     # Set terminal to cbreak mode for immediate key detection
    #     tty.setcbreak(sys.stdin.fileno())
    #     logger.info("Keyboard listener active - type 'sos' to trigger emergency call...")
        
    #     while True:
    #         # Check for keyboard input (non-blocking)
    #         if select.select([sys.stdin], [], [], 0)[0]:
    #             key = sys.stdin.read(1)
                
    #             if key == '\n' or key == '\r':  # Enter key
    #                 if input_buffer.lower().strip() == 'sos':
    #                     logger.info("=" * 60)
    #                     logger.info(">>> SOS COMMAND DETECTED - INITIATING EMERGENCY CALL <<<")
    #                     logger.info("=" * 60)
    #                     # Trigger SOS call using WebRTC's own event loop
    #                     mqtt_client.handler.webrtc.run_async(
    #                         mqtt_client.handler.initiate_sos_call()
    #                     )
    #                 input_buffer = ""  # Clear buffer after Enter
    #             elif key == '\x7f' or key == '\x08':  # Backspace
    #                 input_buffer = input_buffer[:-1]
    #             elif len(key) == 1 and key.isprintable():
    #                 input_buffer += key
    #                 # Show feedback
    #                 if len(input_buffer) <= 10:  # Limit buffer display
    #                     sys.stdout.write(key)
    #                     sys.stdout.flush()
            
    #         time.sleep(0.05)  # Check every 50ms for better responsiveness
    try:
        pass
        
    except KeyboardInterrupt as e:
        logger.error(f"Lỗi: {e}", exc_info=True)
        logger.info("Dừng hệ thống...")
    finally:
        # Restore terminal settings
        # try:
        #     termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        # except:
        #     pass
        # obstacle_system.stop()
        camera.stop()
        voice.stop()
        mqtt_client.disconnect()
        # lane_segmentation.stop()

if __name__ == "__main__":
    main()
