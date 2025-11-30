"""
GPS service module for handling GPS communication & History Logging
"""
import os
import time
import threading
import json
import csv 
from datetime import datetime, timezone
from pathlib import Path

import pynmea2
from serial.tools import list_ports

# --- XỬ LÝ IMPORT SERIAL AN TOÀN ---
try:
    import serial as _serial_mod
    from serial import Serial
    from serial.serialutil import SerialException
except Exception as _e:
    Serial = None
    SerialException = Exception
    _serial_mod = None

from config import GPS_PORT, BAUD_RATE
from log import setup_logger
from container import container
logger = setup_logger(__name__)

# --- CẤU HÌNH ĐƯỜNG DẪN ---
# File lưu vị trí cuối cùng (để khôi phục nhanh)
GPS_LAST_FIX_FILE = Path(__file__).parent.parent / "gps_lastfix.json"
# Thư mục lưu lịch sử di chuyển (Hộp đen)
GPS_HISTORY_DIR = Path(__file__).parent.parent / "logs" / "gps_history"

class GPSService:
    """Service for handling GPS location data and logging history"""

    def __init__(self):
        self.serial_port = None
        self.current_lat = None
        self.current_lng = None
        self.current_speed_kmh = None
        self.last_fix_time = None
        self.update_thread = None
        self.running = False
        
        # Biến quản lý ghi log lịch sử
        self.last_history_log_time = 0
        self.HISTORY_LOG_INTERVAL = 5.0  # Ghi log mỗi 5 giây

        self._file_lock = threading.Lock()
        
        # Tạo thư mục chứa log nếu chưa có
        GPS_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        
        container.register("gps", self)

        # 1. Khôi phục vị trí cũ
        try:
            self._load_last_fix()
        except Exception:
            pass

        # 2. Khởi động luồng
        self._start_gps_thread()
    # Thêm hàm này vào cuối class GPSService, cùng cấp với các hàm khác
    def mock_gps(self, lat, lng):
        """Dùng để test trong nhà"""
        self.current_lat = lat
        self.current_lng = lng
        self.current_speed_kmh = 5.0
        # Cần import timezone: from datetime import datetime, timezone
        self.last_fix_time = datetime.now(timezone.utc)
        logger.warning(f"⚠️ Đang dùng GPS giả lập: {lat}, {lng}")
        
    def _start_gps_thread(self):
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    # ... (Giữ nguyên hàm _candidate_ports và _open_serial như cũ) ...
    def _candidate_ports(self):
        candidates = []
        if GPS_PORT: candidates.append(GPS_PORT)
        common = ["/dev/ttyTHS1", "/dev/ttyTHS0", "/dev/ttyS0", "/dev/ttyUSB0", "/dev/ttyACM0"]
        for p in common:
            if p not in candidates: candidates.append(p)
        try:
            ports = [p.device for p in list_ports.comports()]
            def priority(dev):
                if "ttyTHS" in dev: return 0
                if "ttyUSB" in dev or "ttyACM" in dev: return 1
                return 2
            for dev in sorted(ports, key=priority):
                if dev not in candidates: candidates.append(dev)
        except Exception: pass
        return [p for p in candidates if os.path.exists(p)] or candidates

    def _open_serial(self):
        for port in self._candidate_ports():
            try:
                if Serial is None: raise RuntimeError("pyserial library not found")
                self.serial_port = Serial(port=port, baudrate=BAUD_RATE, timeout=1)
                logger.info(f"GPS Connected: {port}")
                return True
            except Exception:
                pass
        return False
    # ... (Kết thúc phần giữ nguyên) ...

    def _load_last_fix(self):
        """Đọc file json để lấy lại vị trí khi vừa bật máy"""
        if GPS_LAST_FIX_FILE.exists():
            with open(GPS_LAST_FIX_FILE, 'r') as f:
                data = json.load(f)
            self.current_lat = data.get('lat')
            self.current_lng = data.get('lng')
            self.current_speed_kmh = data.get('speed_kmh')
            # Không quan tâm time cũ, chỉ cần tọa độ để init map
            logger.info(f"📍 Khôi phục vị trí cũ: {self.current_lat}, {self.current_lng}")

    def _save_last_fix(self):
        """Lưu vị trí hiện tại vào json (Ghi đè)"""
        if self.current_lat is None: return
        try:
            data = {
                'lat': self.current_lat,
                'lng': self.current_lng,
                'speed_kmh': self.current_speed_kmh,
                'timestamp': datetime.now().isoformat()
            }
            temp_file = GPS_LAST_FIX_FILE.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f)
            temp_file.replace(GPS_LAST_FIX_FILE)
        except Exception as e:
            logger.error(f"Lỗi lưu last fix: {e}")

    def _log_history_to_csv(self):
        """Ghi thêm một dòng vào file CSV lịch sử (Append)"""
        if self.current_lat is None or self.current_lng is None:
            return

        # Tạo tên file theo ngày: gps_track_2025-11-16.csv
        today_str = datetime.now().strftime("%Y-%m-%d")
        filename = GPS_HISTORY_DIR / f"gps_track_{today_str}.csv"
        
        file_exists = filename.exists()
        
        try:
            with open(filename, 'a', newline='') as f:
                writer = csv.writer(f)
                # Nếu file mới tinh thì ghi tiêu đề cột
                if not file_exists:
                    writer.writerow(['Timestamp', 'Date', 'Time', 'Latitude', 'Longitude', 'Speed_KMH'])
                
                # Ghi dữ liệu
                now = datetime.now()
                writer.writerow([
                    now.isoformat(),
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%H:%M:%S"),
                    self.current_lat,
                    self.current_lng,
                    self.current_speed_kmh if self.current_speed_kmh else 0
                ])
        except Exception as e:
            logger.error(f"Lỗi ghi log lịch sử: {e}")

    def _update_loop(self):
        backoff = 1
        last_json_save_time = 0
        
        while self.running:
            if not self.serial_port or not self.serial_port.is_open:
                if not self._open_serial():
                    time.sleep(min(backoff, 5))
                    backoff *= 2
                    continue
                backoff = 1

            try:
                line_bytes = self.serial_port.readline()
                if not line_bytes: continue
                line = line_bytes.decode('utf-8', errors='ignore').strip()

                if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                    msg = pynmea2.parse(line)
                    if getattr(msg, 'status', None) == 'A':
                        self.current_lat = msg.latitude
                        self.current_lng = msg.longitude
                        
                        sog = getattr(msg, 'spd_over_grnd', None)
                        self.current_speed_kmh = float(sog) * 1.852 if sog else 0.0
                        
                        self.last_fix_time = datetime.now(timezone.utc)

                        # --- 1. LƯU JSON (để restore) - 10s/lần ---
                        if time.time() - last_json_save_time > 10:
                            self._save_last_fix()
                            last_json_save_time = time.time()

                        # --- 2. GHI LOG CSV (để giám sát) - 5s/lần ---
                        # Chỉ ghi khi có tọa độ thực sự
                        if time.time() - self.last_history_log_time > self.HISTORY_LOG_INTERVAL:
                            self._log_history_to_csv()
                            self.last_history_log_time = time.time()

            except Exception:
                pass # Bỏ qua lỗi parse lẻ tẻ

    def get_location(self):
        return self.current_lat, self.current_lng

    def get_speed_kmh(self):
        return self.current_speed_kmh

    def cleanup(self):
        self.running = False
        self._save_last_fix() # Lưu lần cuối
        if self.update_thread: self.update_thread.join(timeout=1.0)
        if self.serial_port: 
            try: self.serial_port.close()
            except: pass

# --- PHẦN MAIN TEST ---
if __name__ == "__main__":
    gps = GPSService()
    
    # Giả lập GPS nếu test trong nhà (bỏ comment dòng dưới nếu cần)
    # gps.current_lat, gps.current_lng = 10.762622, 106.660172
    
    print(f"🚀 GPS Service started. Logs folder: {GPS_HISTORY_DIR}")
    print("Đang ghi log hành trình... (Kiểm tra thư mục logs/gps_history)")
    
    try:
        while True:
            lat, lng = gps.get_location()
            if lat:
                print(f"Tracking: {lat}, {lng} - Logged to CSV")
            else:
                print("Waiting for fix...")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping...")
        gps.cleanup()