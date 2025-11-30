import threading
import zmq
import pickle
import time
from log import setup_logger

logger = setup_logger(__name__)

class Camera: 
    def __init__(self):
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)
        self.socket.connect("tcp://localhost:5555")
        self.socket.setsockopt(zmq.SUBSCRIBE, b"")
        self.latest_frame = [None]
        self._stop_event = threading.Event()
        self._thread = None
    def run(self):
        def _run():
            while not self._stop_event.is_set():
                try:
                    data = self.socket.recv()
                    frame = pickle.loads(data)
                    self.latest_frame[0] = frame  # cập nhật frame mới nhất
                except Exception as e:
                    logger.error(f"[Camera ZMQ] Lỗi nhận frame: {e}", exc_info=True)
                    time.sleep(0.1)
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
    
    def get_latest_frame(self):
        return self.latest_frame[0]

    def stop(self):
        logger.info("[Camera] Dừng camera")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
        if not self._thread:
            self.socket.close()
            self.latest_frame = [None]
    
    def cleanup(self):
        self.socket.close()
        self.latest_frame = [None]
    
    def __del__(self):
        self.stop()

    def __enter__(self):
        logger.info("[Camera] Khởi động camera")
        self.run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger.info("[Camera] Dừng camera")
        self.stop()