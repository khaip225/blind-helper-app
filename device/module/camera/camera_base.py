from abc import ABC, abstractmethod
import threading
import time
from typing import Optional
import numpy as np

import cv2
from log import setup_logger

logger = setup_logger(__name__)

class Camera(ABC):
    """
    Lớp trừu tượng cho camera với khả năng đọc frame liên tục trong background thread.
    """
    
    def __init__(self, pipeline: str):
        """
        Khởi tạo camera với GStreamer pipeline.
        
        Args:
            pipeline: GStreamer pipeline string
            
        Raises:
            ValueError: Nếu không thể mở camera
        """
        self._latest_frame = [None]
        self._stop_event = threading.Event()
        self._thread = None
        self._is_running = False
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            raise ValueError("Failed to open camera")
        
    def run(self):
        """Bắt đầu thread đọc frame từ camera."""
        if self._is_running:
            logger.warning("[Camera] Camera đã đang chạy")
            return
            
        def _run():
            while not self._stop_event.is_set():
                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        logger.warning("[Camera] Không đọc được frame")
                        time.sleep(0.1)
                        continue    
                    self._latest_frame[0] = frame  
                    
                except Exception as e:
                    logger.error(f"[Camera] Lỗi nhận frame: {e}", exc_info=True)
                    time.sleep(0.1)
                    
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        self._is_running = True
        logger.info("[Camera] Đã khởi động camera")
   
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Lấy frame mới nhất từ camera.
        
        Returns:
            Frame dưới dạng numpy array hoặc None nếu chưa có frame
        """
        return self._latest_frame[0] 
    
    def is_running(self) -> bool:
        """Kiểm tra xem camera có đang chạy không."""
        return self._is_running and self._thread and self._thread.is_alive()
    
    def stop(self):
        """Dừng camera và giải phóng tài nguyên."""
        if not self._is_running:
            return
            
        logger.info("[Camera] Đang dừng camera...")
        self._stop_event.set()
        self._is_running = False
        
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
                if self._thread.is_alive():
                    logger.warning("[Camera] Thread không dừng sau 2 giây")
            except Exception as e:
                logger.error(f"[Camera] Lỗi khi join thread: {e}")
                
        if self.cap:
            self.cap.release()
            logger.info("[Camera] Đã giải phóng camera")

    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False

    def __del__(self):
        self.stop()
    
