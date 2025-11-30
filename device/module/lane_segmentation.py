import os
import cv2
import zmq
import pickle
import requests
import time
import threading
import numpy as np
from config import BASE_DIR, SERVER_HTTP_BASE, DIFF_THRESHOLD, SEND_INTERVAL_MIN, SEND_INTERVAL_MAX
from container import container
from module.camera.camera_base import Camera
from module.voice_speaker import VoiceSpeaker

from log import setup_logger
logger = setup_logger(__name__)
class LaneSegmentation:
    def __init__(self):
        self.running = False
        self.thread = None
        self._stop_event = None
        self.adaptive_interval = SEND_INTERVAL_MIN    
        container.register("lane_segmentation", self)
        logger.info("[LaneSegmentation] Đã khởi động")
        
    def frames_are_different(self, frame1, frame2, threshold):
        if frame1 is None or frame2 is None:
            return True
        # Resize nhỏ lại để so sánh nhanh hơn, giảm nhiễu
        small1 = cv2.resize(frame1, (64, 64))
        small2 = cv2.resize(frame2, (64, 64))
        diff = cv2.absdiff(small1, small2)
        mean_diff = np.mean(diff)
        return mean_diff > threshold

    def send_image_to_api(self, frame):
        try:
            success, buffer = cv2.imencode('.jpg', frame)
            if not success:
                logger.error("[API] Lỗi mã hóa ảnh.")
                return
            files = {
                'image': ('obstacle.jpg', buffer.tobytes(), 'image/jpeg')
            }
            
            # Gửi request với timeout
            response = requests.post(
                f"{SERVER_HTTP_BASE}/segment", 
                files=files,
                timeout=10
            )
            
            # Kiểm tra HTTP status
            if response.status_code != 200:
                logger.error(f"[API] HTTP {response.status_code}: {response.text[:200]}")
                return
            
            # Parse JSON response
            data = response.json()
            logger.info(f"[API] Phản hồi: {data}")
            
            # Lấy audio_file từ response
            audio_file = None
            is_safe = True  # Mặc định là an toàn
            if isinstance(data, dict):
                # Kiểm tra có key "data" không
                if "data" in data and isinstance(data["data"], dict):
                    audio_file = data["data"].get("audio_file")
                    is_safe = data["data"].get("is_safe", True)  # Lấy is_safe, mặc định True

            # Chỉ phát audio nếu KHÔNG an toàn
            speaker: VoiceSpeaker = container.get("speaker")
            if not is_safe:  # Nếu is_safe = False
                if audio_file:
                    # Đường dẫn đến file audio trong thư mục warning
                    audio_path = os.path.join(BASE_DIR, "audio", "warning", f"{audio_file}.wav")
                    
                    # Kiểm tra file tồn tại
                    if os.path.exists(audio_path):
                        logger.info(f"[API] Phát cảnh báo: {audio_path}")
                        speaker.play_file(audio_path)
                    else:
                        logger.warning(f"[API] Không tìm thấy file audio: {audio_path}")
                else:
                    # Không có audio_file nhưng không an toàn
                    logger.warning("[API] Không an toàn nhưng không có audio_file")
            else:
                # An toàn, không cần phát audio
                logger.info("[API] Vị trí an toàn, không cần cảnh báo")
                
        except requests.exceptions.Timeout:
            logger.error("[API] Request timeout sau 10s")
        except requests.exceptions.ConnectionError:
            logger.error(f"[API] Không thể kết nối đến {SERVER_HTTP_BASE}/segment")
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"[API] Response không phải JSON: {e}")
        except Exception as e:
            logger.error(f"[API] Lỗi gửi ảnh: {e}", exc_info=True)

    def api_sender_thread(self):
        last_sent_time = 0
        while not self._stop_event.is_set():
            now = time.time()
            camera: Camera = container.get("camera")
            prev_frame = camera.get_latest_frame()
            time.sleep(1)
            latest_frame = camera.get_latest_frame()
            if prev_frame is not None and latest_frame is not None and (now - last_sent_time >= self.adaptive_interval):
                if self.frames_are_different(latest_frame, prev_frame, DIFF_THRESHOLD):  # nếu khác biệt lớn
                    self.adaptive_interval = max(SEND_INTERVAL_MIN, self.adaptive_interval * 0.8)
                    self.send_image_to_api(latest_frame)
                    last_sent_time = now
                else:  
                    self.adaptive_interval = min(SEND_INTERVAL_MAX, self.adaptive_interval * 1.2)
    def run(self):
        if self.running:
            logger.warning("[LaneSegmentation] Đã đang chạy rồi!")
            return False
        self.running = True
        self._stop_event = threading.Event()
        self.thread = threading.Thread(target=self.api_sender_thread, daemon=True)
        self.thread.start()
        logger.info("[LaneSegmentation] Đã khởi động")
        return True
        
    def stop(self):
        if not self.running:
            logger.warning("[LaneSegmentation] Chưa chạy!")
            return False
        logger.info("[LaneSegmentation] Đang dừng...")
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.info("[LaneSegmentation] Đã dừng")
        return True
    
    def is_running(self) -> bool:
        """Kiểm tra trạng thái hoạt động"""
        return self.running and self.thread and self.thread.is_alive()
        
    def __del__(self):
        if self.running:
            self.stop()
        
    def __enter__(self):
        self.run()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
