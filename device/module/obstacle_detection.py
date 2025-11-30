import cv2
import zmq
import pickle
import threading
import time
import board
import busio
import requests
import adafruit_vl53l1x
import time
from config import SERVER_HTTP_BASE, BASE_DIR
from container import container
from module.voice_speaker import VoiceSpeaker
import os
from log import setup_logger
from module.camera.camera_base import Camera
logger = setup_logger(__name__)

WARNING_SOUND_FILE = os.path.join(BASE_DIR, "audio", "stop.wav")

BASE_AUDIO_PATH = os.path.join(BASE_DIR, "audio", "warning")

class ToFSensor:
    def __init__(self, i2c, name):
        self.name = name
        try:
            self.tof = adafruit_vl53l1x.VL53L1X(i2c)
            self.tof.distance_mode = 2
            self.tof.timing_budget = 200
            self.tof.start_ranging()
           
            print(f"[Cảm biến {self.name}] Khởi tạo thành công.")
        except Exception as e:
            print(f"[Cảm biến {self.name}] Lỗi khởi tạo: {e}")
            self.tof = None

    def read_distance(self):
        if self.tof and self.tof.data_ready:
            try:
                distance = self.tof.distance
                self.tof.clear_interrupt()
                return distance
            except OSError as e:
                print(f"[Cảm biến {self.name}] Lỗi đọc dữ liệu: {e}")
                self.stop()
                self.tof = None
        return None

    def stop(self):
        if self.tof:
            try:
                self.tof.stop_ranging()
            except Exception as e:
                print(f"[Cảm biến {self.name}] Lỗi khi dừng: {e}")

    def __del__(self):
        self.stop()


class ObstacleDetectionSystem:
    def __init__(self):
        self.sensors = []
        self.last_alert_time = 0
        self.alert_interval = 5
        self._stop_event = threading.Event()
        self._thread = None
        self.setup_sensors()
        container.register("obstacle_detection_system", self)

    def setup_sensors(self):
        try:
            i2c_buses = [
                (busio.I2C(board.SCL_1, board.SDA_1), "cảm biến ngang"),
            ]
            self.sensors = [ToFSensor(i2c, name)
                            for i2c, name in i2c_buses]
        except Exception as e:
            print(f"Lỗi khi khởi tạo các cảm biến: {e}")
            self.sensors = []

    def send_image_to_api_async(self, frame):
        try:
            success, buffer = cv2.imencode('.jpg', frame)
            if not success:
                print("[API] Lỗi mã hóa ảnh.")
                return
            files = {
                'image': ('obstacle.jpg', buffer.tobytes(), 'image/jpeg')
            }
            response = requests.post(f"{SERVER_HTTP_BASE}/detect", files=files)
            data = response.json()
            print(f"[API] Phản hồi: {data}")
            message = data.get("data", {}).get(
                "data", "Không phát hiện vật cản")
            speaker: VoiceSpeaker = container.get("speaker")
            speaker.play_file(WARNING_SOUND_FILE)
        except Exception as e:
            print(f"[API] Lỗi gửi ảnh: {e}")

    def detect_obstacles(self):
        distances = []
        for sensor in self.sensors:
            distance = sensor.read_distance()
            if distance:
                logger.debug(f"[ObstacleDetection] [Cảm biến {sensor.name}] Khoảng cách: {distance} cm")
                distances.append(distance)

        now = time.time()
        if any(100 <= d <= 150 for d in distances):
            if now - self.last_alert_time >= self.alert_interval:
                self.last_alert_time = now
                logger.info("[ObstacleDetection] Phát hiện vật cản trong phạm vi 1–1.5m!")
                
                speaker: VoiceSpeaker = container.get("speaker")
                speaker.play_file(WARNING_SOUND_FILE)
                
                # Lấy ảnh từ camera
                camera: Camera = container.get("camera")
                frame = camera.get_latest_frame()
                
                if frame is not None:
                    logger.info(f"[ObstacleDetection] Ảnh đã chụp thành công")
                    try:
                        # Mã hóa ảnh
                        success, buffer = cv2.imencode('.jpg', frame)
                        if not success:
                            logger.error("[ObstacleDetection] Lỗi mã hóa ảnh.")
                            return
                        
                        # Gửi ảnh đến API
                        files = {
                            'image': ('obstacle.jpg', buffer.tobytes(), 'image/jpeg')
                        }
                        response = requests.post(f"{SERVER_HTTP_BASE}/detect", files=files, timeout=10)
                        data = response.json()
                        
                        if data.get("success"):
                            audio_file = data.get("data", {}).get("audio_file")
                            if audio_file:
                                audio_file_path = os.path.join(BASE_AUDIO_PATH, f'{audio_file}.wav')
                                logger.info(f"[ObstacleDetection] Phát âm thanh: {audio_file_path}")
                                speaker.play_file(audio_file_path)
                            else:
                                logger.warning("[ObstacleDetection] Không có file audio trong response")
                        else:
                            logger.warning(f"[ObstacleDetection] API trả về lỗi: {data.get('message')}")
                            
                    except requests.exceptions.RequestException as e:
                        logger.error(f"[ObstacleDetection] Lỗi kết nối API: {e}")
                    except Exception as e:
                        logger.error(f"[ObstacleDetection] Lỗi xử lý: {e}")
                else:
                    logger.info("[ObstacleDetection] Không có ảnh mới.")
                    
    def run(self):
        if self._thread and self._thread.is_alive():
            logger.warning("[ObstacleDetection] Đã đang chạy rồi!")
            return False
            
        def _run():
            try:
                while not self._stop_event.is_set():
                    self.detect_obstacles()
                    time.sleep(0.5)
            except KeyboardInterrupt:
                logger.info("[ObstacleDetection] Dừng hệ thống.")
            finally:
                self.cleanup()
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        logger.info("[ObstacleDetection] Đã khởi động")
        return True
    
    def stop(self):
        if not self._thread or not self._thread.is_alive():
            logger.warning("[ObstacleDetection] Chưa chạy!")
            return False
        logger.info("[ObstacleDetection] Đang dừng")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
        logger.info("[ObstacleDetection] Đã dừng")
        return True
    
    def is_running(self) -> bool:
        """Kiểm tra trạng thái hoạt động"""
        return self._thread is not None and self._thread.is_alive()
      
    def cleanup(self):
        for sensor in self.sensors:
            sensor.stop()

    def __del__(self):
        self.cleanup()

if __name__ == "__main__":
    obstacle_detection_system = ObstacleDetectionSystem()
    obstacle_detection_system.run()
    



