import sys
import json
from pathlib import Path
import time

from mqtt.client import MQTTClient

# Import config từ root
sys.path.append(str(Path(__file__).parent.parent))
from config import TOPICS
from log import setup_logger
from module.gps import GPSService

logger = setup_logger(__name__)

class GPSMQTT:
    def __init__(self, mqtt_client : MQTTClient):
        """
        :param mqtt_client: Instance của class MQTTClient
        """
        self.mqtt = mqtt_client
        self.gps_service = GPSService()
        self.gps_service.mock_gps(10.772109, 106.698298)

    def publish_gps(self, qos=1): 
        topic = TOPICS.get("device_gps")
        
        try:
            while True:
                lat, lng = self.gps_service.get_location()
                if lat:
                    logger.info(f"Tracking: {lat}, {lng} - Logged to CSV")
                else:
                    logger.info("Waiting for fix...")
                
                self.mqtt.publish(topic, {"latitude": lat, "longitude": lng}, qos=qos, retain=True)
                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Stopping...")
            self.gps_service.cleanup()
    
        