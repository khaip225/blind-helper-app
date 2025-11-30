"""
GPS Manager System
Location: module/gps_manager.py
Nhiệm vụ: Quản lý GPSService và tự động gửi dữ liệu qua MQTT định kỳ
"""
import time
import threading
from module.gps import GPSService
from config import DEVICE_ID, TOPICS
from log import setup_logger

logger = setup_logger("gps_manager")

class GPSManager:
    def __init__(self, mqtt_client):
        """
        :param mqtt_client: Client MQTT đã kết nối
        """
        # 1. Khởi tạo phần cứng (GPSService đã có sẵn logic khôi phục & log CSV)
        self.gps_service = GPSService()
        
        self.gps_service.mock_gps(10.772109, 106.698298)
        # 2. Lưu mqtt_client để publish
        self.mqtt_client = mqtt_client
        
        # 3. Cờ kiểm soát luồng
        self.running = False
        self.thread = None
        self.publish_interval = 5.0 # Gửi 5 giây/lần

    def run(self):
        """Bắt đầu chạy hệ thống GPS trong luồng riêng"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        logger.info("✅ GPS System Started (Background Thread)")

    def _process_loop(self):
        """Vòng lặp chạy ngầm"""
        while self.running:
            try:
                # A. Lấy dữ liệu từ phần cứng
                lat, lng = self.gps_service.get_location()
                speed = self.gps_service.get_speed_kmh()

                # B. Kiểm tra và đóng gói
                if lat is not None:
                    # 🔥 FIX: Mobile expects {latitude, longitude} format
                    payload = {
                        "latitude": lat,
                        "longitude": lng,
                        "speed_kmh": speed if speed else 0.0,
                        "pin": 85  # Mock battery level
                    }
                    
                    # C. Gửi đi qua MQTT
                    topic = TOPICS.get("device_gps")
                    self.mqtt_client.publish(topic, payload, qos=0, retain=False)
                    logger.debug(f"📍 GPS published: {lat:.6f}, {lng:.6f}")
                
                # D. Nghỉ
                time.sleep(self.publish_interval)

            except Exception as e:
                logger.error(f"Lỗi trong vòng lặp GPS Manager: {e}")
                time.sleep(1)

    def stop(self):
        """Dừng hệ thống an toàn"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        
        # Gọi cleanup của phần cứng để lưu file json lần cuối
        self.gps_service.cleanup()
        logger.info("🛑 GPS System Stopped")