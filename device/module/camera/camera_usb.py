import time
import cv2

from log import setup_logger
from .camera_base import Camera

logger = setup_logger(__name__)

class CameraUSB(Camera):
    def __init__(self):
        try:
            pipeline = (
                "v4l2src device=/dev/video0 ! "
                "image/jpeg,width=1280,height=720,framerate=30/1 ! "
                "jpegdec ! videoconvert ! video/x-raw,format=BGR ! "
                "appsink drop=true max-buffers=1 sync=false"
            )
            super().__init__(pipeline)
            self.run()
        except Exception as e:
            logger.warning(f"[Camera USB] Lỗi khởi tạo camera với GStreamer: {e}", exc_info=True)
        
if __name__ == "__main__":
    camera = CameraUSB()
    while True:
        frame = camera.get_latest_frame()
        if frame is not None:
            cv2.imshow("Frame", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        time.sleep(1)
    camera.stop()
    cv2.destroyAllWindows()