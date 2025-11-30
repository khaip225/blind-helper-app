import time
import serial
import threading
from log import setup_logger

logger = setup_logger(__name__)

class GPRSConnection:
    """Quản lý kết nối GPRS qua module SIM800A"""
    
    def __init__(self, port='/dev/ttyTHS1', baud=9600):
        self.port = port
        self.baud = baud
        self.ser = None
        self.connected = False
        self.lock = threading.Lock()
        self.initialize()
        
    def initialize(self):
        """Khởi tạo kết nối với module SIM800A"""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            logger.info(f"Kết nối serial với module SIM800A thành công trên {self.port}")
            
            # Chờ module khởi động
            logger.info("Chờ module SIM800A khởi động...")
            time.sleep(3)
            
            # Bỏ qua bước reset, kiểm tra kết nối trực tiếp
            for attempt in range(3):
                logger.info(f"Đang thử kết nối với module SIM800A (lần {attempt+1})...")
                if self._send_at("AT", "OK", timeout=5):
                    logger.info("Kết nối với module thành công!")
                    break
                time.sleep(2)
            else:
                logger.error("Không thể kết nối với module SIM800A sau nhiều lần thử")
                return False
                
            # Kiểm tra cường độ tín hiệu
            signal = self._check_signal()
            if signal < 10:
                logger.warning(f"Cường độ tín hiệu thấp: {signal}/31")
            else:
                logger.info(f"Cường độ tín hiệu: {signal}/31 - Đủ mạnh để kết nối dữ liệu")
                
            logger.info("Khởi tạo module SIM800A thành công")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo kết nối với module SIM800A: {e}")
            return False
            
    def connect_gprs(self):
        """Thiết lập kết nối GPRS"""
        with self.lock:
            if self.connected:
                logger.info("Kết nối GPRS đã được thiết lập")
                return True
                
            logger.info("Đang thiết lập kết nối GPRS...")
            
            # Thiết lập thông số GPRS
            if not self._send_at("AT+SAPBR=3,1,\"CONTYPE\",\"GPRS\"", "OK"):
                logger.error("Không thể thiết lập kiểu kết nối GPRS")
                return False
                
            # Thiết lập APN cho nhà mạng Mobifone
            if not self._send_at("AT+SAPBR=3,1,\"APN\",\"m-wap\"", "OK"):
                logger.error("Không thể thiết lập APN")
                return False
                
            # Kích hoạt kết nối GPRS
            if not self._send_at("AT+SAPBR=1,1", "OK", timeout=10):
                logger.error("Không thể kích hoạt kết nối GPRS")
                return False
                
            # Kiểm tra IP được cấp
            response = self._send_at_with_response("AT+SAPBR=2,1")
            if "+SAPBR: 1,1," in response:
                ip = response.split("+SAPBR: 1,1,\"")[1].split("\"")[0]
                logger.info(f"Kết nối GPRS thành công với IP: {ip}")
                self.connected = True
                return True
            else:
                logger.error("Không thể lấy IP từ kết nối GPRS")
                return False
                
    def disconnect_gprs(self):
        """Ngắt kết nối GPRS"""
        with self.lock:
            if not self.connected:
                return True
                
            logger.info("Đang ngắt kết nối GPRS...")
            if self._send_at("AT+SAPBR=0,1", "OK", timeout=5):
                self.connected = False
                logger.info("Đã ngắt kết nối GPRS")
                return True
            else:
                logger.error("Không thể ngắt kết nối GPRS")
                return False
                
    def is_connected(self):
        """Kiểm tra xem kết nối GPRS có hoạt động không"""
        with self.lock:
            if not self.connected:
                return False
                
            response = self._send_at_with_response("AT+SAPBR=2,1")
            if "+SAPBR: 1,1," in response:
                return True
            else:
                self.connected = False
                return False
            
    def _send_at(self, command, expected_response="OK", timeout=2):
        """Gửi AT command và kiểm tra phản hồi"""
        with self.lock:
            if not self.ser or not self.ser.is_open:
                return False
                
            # Xóa bộ đệm đầu vào
            self.ser.reset_input_buffer()
            
            # Gửi lệnh AT
            self.ser.write((command + "\r\n").encode())
            self.ser.flush()
            
            # Đọc phản hồi
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < timeout:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    response += data.decode('utf-8', errors='replace')
                    logger.info(f"Raw response: {repr(data)}")
                    
                    if expected_response in response:
                        return True
                time.sleep(0.1)
                
            logger.error(f"Lệnh: {command}, Phản hồi: {repr(response)}")
            return False
            
    def _send_at_with_response(self, command, timeout=2):
        """Gửi AT command và trả về toàn bộ phản hồi"""
        with self.lock:
            if not self.ser or not self.ser.is_open:
                return ""
                
            # Xóa bộ đệm đầu vào
            self.ser.reset_input_buffer()
            
            # Gửi lệnh AT
            self.ser.write((command + "\r\n").encode())
            
            # Đọc phản hồi
            time.sleep(timeout)
            response = ""
            
            while self.ser.in_waiting > 0:
                # Sửa dòng này để xử lý các byte không hợp lệ
                response += self.ser.read(self.ser.in_waiting).decode('utf-8', errors='replace')
                time.sleep(0.1)
                
            return response
            
    def _read_response(self, timeout=5):
        """Đọc phản hồi từ module trong khoảng thời gian timeout"""
        with self.lock:
            response = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.ser.in_waiting > 0:
                    # Sửa dòng này để xử lý các byte không hợp lệ
                    response += self.ser.read(self.ser.in_waiting).decode('utf-8', errors='replace')
                time.sleep(0.2)
                
            return response
            
    def _check_signal(self):
        """Kiểm tra cường độ tín hiệu và trả về giá trị số"""
        response = self._send_at_with_response("AT+CSQ")
        
        try:
            # Tách giá trị từ phản hồi "+CSQ: xx,yy"
            signal_str = response.split("+CSQ: ")[1].split(",")[0]
            signal = int(signal_str)
            return signal
        except (IndexError, ValueError):
            logger.error(f"Không thể đọc cường độ tín hiệu: {response}")
            return 0
            
    def _check_network(self):
        """Kiểm tra trạng thái đăng ký mạng"""
        try:
            response = self._send_at_with_response("AT+CREG?")
            
            # Tìm kiếm "+CREG: 0,1" hoặc "+CREG: 0,5"
            # 1 = Đã đăng ký, mạng nội địa
            # 5 = Đã đăng ký, chuyển vùng
            if "+CREG: 0,1" in response or "+CREG: 0,5" in response:
                try:
                    operator = self._send_at_with_response("AT+COPS?")
                    logger.info(f"Đã đăng ký vào mạng: {operator.strip()}")
                except Exception as e:
                    logger.warning(f"Không thể đọc thông tin nhà mạng: {e}")
                return True
            else:
                logger.error(f"Chưa đăng ký mạng: {response.strip()}")
                return False
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra đăng ký mạng: {e}")
            return False
        
    def send_sms(self, phone_number, message):
        """Gửi SMS đến số điện thoại"""
        try:
            logger.info(f"Đang gửi SMS đến {phone_number}...")
            
            # Thiết lập chế độ text mode
            if not self._send_at("AT+CMGF=1", "OK"):
                logger.error("Không thể thiết lập chế độ text mode")
                return False
                
            # Thiết lập encoding UTF-8 (hỗ trợ tiếng Việt)
            if not self._send_at("AT+CSCS=\"UTF8\"", "OK"):
                logger.warning("Không thể thiết lập UTF-8 encoding, sử dụng GSM encoding")
                
            # Thiết lập số điện thoại nhận
            if not self._send_at(f"AT+CMGS=\"{phone_number}\"", ">"):
                logger.error("Không thể thiết lập số điện thoại nhận")
                return False
                
            # Gửi nội dung tin nhắn
            self.ser.write(message.encode('utf-8'))
            self.ser.write(b'\x1A')  # Ctrl+Z để kết thúc
            self.ser.flush()
            
            # Chờ phản hồi
            time.sleep(3)
            response = self._read_response(timeout=10)
            
            if "+CMGS:" in response:
                logger.info(f"✅ SMS đã được gửi thành công đến {phone_number}")
                return True
            else:
                logger.error(f"❌ Gửi SMS thất bại: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Lỗi khi gửi SMS: {e}")
            return False

    def send_test_sms(self, phone_number, message):
        logger.info('phone: ', phone_number)
        logger.info('message: ', message)
        return True

    def send_sms_unicode_pdu(self, phone_number, message):
        """Gửi SMS Unicode sử dụng PDU Mode"""
        try:
            # Thiết lập PDU mode
            if not self._send_at("AT+CMGF=0", "OK"):
                return False
                
            # Tạo PDU data
            pdu_data = self._create_ucs2_pdu(phone_number, message)
            if not pdu_data:
                return False
                
            # Gửi PDU
            if not self._send_at(f"AT+CMGS={len(message)}", ">"):
                return False
                
            self.ser.write(pdu_data.encode())
            self.ser.write(b'\x1A')
            self.ser.flush()
            
            time.sleep(5)
            response = self._read_response(timeout=15)
            
            return "+CMGS:" in response
            
        except Exception as e:
            logger.error(f"Lỗi: {e}")
            return False

    def _create_ucs2_pdu(self, phone_number, message):
        """Tạo PDU UCS2 đúng chuẩn"""
        try:
            # Làm sạch số điện thoại
            clean_phone = ''.join(filter(str.isdigit, phone_number))
            if not clean_phone.startswith('84'):
                clean_phone = '84' + clean_phone.lstrip('0')
                
            # Tạo phone PDU
            phone_pdu = self._phone_to_pdu_simple(clean_phone)
            
            # Chuyển message sang UCS2
            ucs2_bytes = message.encode('utf-16be')
            message_hex = ucs2_bytes.hex().upper()
            
            # Tạo PDU header theo chuẩn 3GPP
            pdu_header = "00"        # SCA
            pdu_header += "11"       # PDU Type (SMS-SUBMIT)
            pdu_header += "00"       # MR
            pdu_header += phone_pdu  # DA
            pdu_header += "00"       # PID
            pdu_header += "08"       # DCS (UCS2)
            pdu_header += "00"       # VP
            pdu_header += f"{len(message):02X}"  # UDL
            
            return pdu_header + message_hex
            
        except Exception as e:
            logger.error(f"Lỗi tạo PDU: {e}")
            return None

    def _phone_to_pdu_simple(self, phone_number):
        """Chuyển đổi số điện thoại sang PDU format (đơn giản)"""
        try:
            # Đảo ngược từng cặp số
            pdu_phone = ""
            for i in range(0, len(phone_number), 2):
                if i + 1 < len(phone_number):
                    pdu_phone += phone_number[i+1] + phone_number[i]
                else:
                    pdu_phone += 'F' + phone_number[i]
                    
            # Thêm độ dài và type
            length = len(phone_number)
            return f"{length:02X}91{pdu_phone}"
            
        except Exception as e:
            logger.error(f"Lỗi chuyển đổi số điện thoại: {e}")
            return None


if __name__ == "__main__":
    # Script test kết nối GPRS
    gprs = GPRSConnection()
    
    print("Đang khởi tạo module SIM800A...")
    if gprs.initialize():
        print("✅ Khởi tạo module thành công")
        
        # Test gửi SMS
        phone_number = "0393453221" 
        message = "Xin chao! Day la tin nhan test tu module SIM800A."
        
        print(f"Đang gửi SMS đến {phone_number}...")
        if gprs.send_sms(phone_number, message):
            print("✅ Gửi SMS thành công!")
        else:
            print("❌ Gửi SMS thất bại")
            
        # # Test gửi SMS Unicode (tiếng Việt có dấu)
        # unicode_message = "Xin chào! Đây là tin nhắn test có dấu tiếng Việt."
        # print(f"Đang gửi SMS Unicode đến {phone_number}...")
        # if gprs.send_sms_unicode_pdu(phone_number, unicode_message):
        #     print("✅ Gửi SMS Unicode thành công!")
        # else:
        #     print("❌ Gửi SMS Unicode thất bại")
            
    else:
        print("❌ Không thể khởi tạo module SIM800A")
        
    gprs.close()