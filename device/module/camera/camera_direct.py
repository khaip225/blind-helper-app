import time
import threading
from typing import Optional
import numpy as np
import cv2

from log import setup_logger
from .camera_base import Camera
from container import container
logger = setup_logger(__name__)

class CameraDirect(Camera):
    """
    Lớp camera sử dụng OpenCV trực tiếp thay vì qua GStreamer.
    Hỗ trợ reconnection tự động và FPS control.
    """
    def __init__(self, camera_id=0, width=1920, height=1080, fps=30, 
                 auto_reconnect=True, reconnect_delay=5.0):
        """
        Khởi tạo camera với OpenCV.
        
        Args:
            camera_id: ID của camera (thường là 0, 1, 2,... hoặc đường dẫn video)
            width: Chiều rộng mong muốn
            height: Chiều cao mong muốn
            fps: Frames per second mục tiêu
            auto_reconnect: Tự động kết nối lại khi mất kết nối
            reconnect_delay: Thời gian chờ giữa các lần thử kết nối lại (giây)
        """
        # Khởi tạo các biến thành viên
        self._latest_frame = [None]
        self._stop_event = threading.Event()
        self._thread = None
        self._is_running = False
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.target_fps = fps
        self.frame_delay = 1.0 / fps if fps > 0 else 0
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self._last_frame_time = 0
        self._frame_count = 0
        self._error_count = 0
        
        # Mở camera
        self._open_camera()
        
        # Chạy thread đọc camera
        self.run()
    
    def _open_camera(self):
        """Mở camera và thiết lập các thông số."""
        logger.info(f"[Camera Direct] Đang mở camera {self.camera_id}...")
        self.cap = cv2.VideoCapture(self.camera_id)
        
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open camera {self.camera_id}")
        
        # Thiết lập độ phân giải
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        
        # Lấy độ phân giải thực tế
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        logger.info(f"[Camera Direct] Camera đã mở: {actual_width}x{actual_height} @ {actual_fps} FPS")
        
        # Thiết lập các thông số khác nếu cần
        # self.cap.set(cv2.CAP_PROP_BRIGHTNESS, 150)
        # self.cap.set(cv2.CAP_PROP_CONTRAST, 40)
        # self.cap.set(cv2.CAP_PROP_SATURATION, 50)
        # self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Giảm buffer để giảm độ trễ
        container.register("camera", self)
    
    def _reconnect(self):
        """Thử kết nối lại camera."""
        logger.warning("[Camera Direct] Đang thử kết nối lại camera...")
        try:
            if self.cap:
                self.cap.release()
            time.sleep(self.reconnect_delay)
            self._open_camera()
            self._error_count = 0
            logger.info("[Camera Direct] Kết nối lại camera thành công")
            return True
        except Exception as e:
            logger.error(f"[Camera Direct] Lỗi khi kết nối lại: {e}")
            return False
    
    def run(self):
        """Bắt đầu thread đọc frame từ camera."""
        if self._is_running:
            logger.warning("[Camera Direct] Camera đã đang chạy")
            return
            
        def _run():
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while not self._stop_event.is_set():
                try:
                    # FPS control
                    current_time = time.time()
                    elapsed = current_time - self._last_frame_time
                    if elapsed < self.frame_delay:
                        time.sleep(self.frame_delay - elapsed)
                    
                    ret, frame = self.cap.read()
                    if not ret:
                        consecutive_errors += 1
                        logger.warning(f"[Camera Direct] Không đọc được frame (lỗi liên tiếp: {consecutive_errors})")
                        
                        # Nếu lỗi quá nhiều, thử reconnect
                        if consecutive_errors >= max_consecutive_errors and self.auto_reconnect:
                            if self._reconnect():
                                consecutive_errors = 0
                            else:
                                time.sleep(1.0)
                        else:
                            time.sleep(0.1)
                        continue
                    
                    # Reset error counter khi đọc thành công
                    consecutive_errors = 0
                    self._latest_frame[0] = frame
                    self._frame_count += 1
                    self._last_frame_time = time.time()
                    
                except Exception as e:
                    self._error_count += 1
                    logger.error(f"[Camera Direct] Lỗi nhận frame: {e}", exc_info=True)
                    time.sleep(0.1)
        
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        self._is_running = True
        logger.info("[Camera Direct] Đã khởi động camera thread")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Lấy frame mới nhất từ camera.
        
        Returns:
            Frame dưới dạng numpy array hoặc None nếu chưa có frame
        """
        return self._latest_frame[0]
    
    def get_stats(self) -> dict:
        """
        Lấy thống kê về camera.
        
        Returns:
            Dictionary chứa các thông tin thống kê
        """
        return {
            'frame_count': self._frame_count,
            'error_count': self._error_count,
            'is_running': self.is_running(),
            'target_fps': self.target_fps,
            'camera_id': self.camera_id
        }
    
    def is_running(self) -> bool:
        """Kiểm tra xem camera có đang chạy không."""
        return self._is_running and self._thread and self._thread.is_alive()
    
    def stop(self):
        """Dừng camera và giải phóng tài nguyên."""
        if not self._is_running:
            return
            
        logger.info("[Camera Direct] Đang dừng camera...")
        self._stop_event.set()
        self._is_running = False
        
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
                if self._thread.is_alive():
                    logger.warning("[Camera Direct] Thread không dừng sau 2 giây")
            except Exception as e:
                logger.error(f"[Camera Direct] Lỗi khi join thread: {e}")
        
        if self.cap:
            self.cap.release()
            logger.info(f"[Camera Direct] Đã giải phóng camera. Stats: {self.get_stats()}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
    
    def __del__(self):
        self.stop()


if __name__ == "__main__":
    # Test camera với context manager
    print("Nhấn 'q' để thoát, 's' để xem stats")
    
    with CameraDirect(fps=30) as camera:
        try:
            while True:
                frame = camera.get_latest_frame()
                if frame is not None:
                    cv2.imshow("Camera Direct Test", frame)
                    
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    stats = camera.get_stats()
                    print(f"\n=== Camera Stats ===")
                    print(f"Frames: {stats['frame_count']}")
                    print(f"Errors: {stats['error_count']}")
                    print(f"Running: {stats['is_running']}")
                    print(f"Target FPS: {stats['target_fps']}")
                    print(f"Camera ID: {stats['camera_id']}")
                    
        finally:
            cv2.destroyAllWindows()
