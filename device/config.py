"""Configuration constants for WebRTC simulator (simplified)."""
import os
import logging
from dotenv import load_dotenv

# Load environment variables
# Ưu tiên nạp .env ở project root cho MQTT, sau đó nạp .env nội bộ (không override)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_simulator")

# MQTT Configuration (đồng bộ với hệ thống)
# Các biến môi trường theo hệ thống: BROKER_HOST, BROKER_PORT, BROKER_TRANSPORT, BROKER_USE_TLS,
# MQTT_USER, MQTT_PASS, BROKER_WS_PATH, DEVICE_ID
# Hardcoded MQTT configuration to match the mobile app and a single known broker.
# If you want to override these, edit this file directly (no environment variables used).
BROKER_HOST = "mqtt.phuocnguyn.id.vn"
BROKER_TRANSPORT = "websockets"
# Port 443 for secure websockets (wss)
BROKER_PORT = 443
# WebSocket path used by mobile client
BROKER_WS_PATH = "/"
# Use TLS for secure connection
BROKER_USE_TLS = True
# Device MQTT credentials (hardcoded for local testing)
MQTT_USER = "device001"
MQTT_PASS = "123456"
# Fixed device id (hardcoded for testing)
DEVICE_ID = "device001"

# Biến tương thích ngược cho phần mobile còn dùng tên cũ
MQTT_BROKER = BROKER_HOST
MQTT_PORT = BROKER_PORT

FORCE_TURN = False
FORCE_IPV4 = False

DEFAULT_TURN_URLS = [
    "stun:stun.relay.metered.ca:80",
    "turn:sg.relay.metered.ca:80",
    "turn:sg.relay.metered.ca:80?transport=tcp",
    "turn:sg.relay.metered.ca:443",
    "turns:sg.relay.metered.ca:443?transport=tcp",
]
TURN_URLS = [u.strip() for u in os.getenv("TURN_URLS", ",".join(DEFAULT_TURN_URLS)).split(",") if u.strip()]
TURN_USERNAME = os.getenv("TURN_USERNAME", "93e17668232018bed69fae39")
TURN_PASSWORD = os.getenv("TURN_PASSWORD", "/NDIlk/I1eVxIjo2")

PLAYBACK_GAIN = 3.0
PLAYBACK_OUTPUT_RATE = 48000
MICROPHONE_GAIN = 1.0          # Start with raw microphone (no boost)
MICROPHONE_NOISE_GATE = 0      # Disable noise gate by default (raw capture)
PLAYBACK_AUTO_GAIN = True
PLAYBACK_TARGET_RMS = 8000
PLAYBACK_MAX_GAIN = 8.0
PLAYBACK_MAX_GAIN_TOTAL = 12.0
PLAYBACK_COMPRESSOR_ENABLED = True
PLAYBACK_COMPRESSOR_DRIVE = 2.0

# Debug / capture configuration
MIC_RECORD_DEBUG = bool(int(os.getenv("MIC_RECORD_DEBUG", "0")))  # 1 to write raw_mic.wav
MIC_FRAMES_PER_BUFFER = int(os.getenv("MIC_FRAMES_PER_BUFFER", "480"))  # Smaller buffer for lower latency
MIC_TARGET_RATE = int(os.getenv("MIC_TARGET_RATE", "48000"))  # Chuẩn hóa sample rate uplink (resample nếu khác)

# Video Configuration
VIDEO_FRAME_LOG_INTERVAL = 120
VIDEO_FIRST_FRAME_TIMEOUT = 3.0

ICE_RESTART_COOLDOWN = 15.0
ICE_CANDIDATE_POOL_SIZE = 10

# Global state variables
class GlobalState:
    def __init__(self):
        self.client = None
        self.pc = None
        self.player = None
        self.audio_player = None
        self.recorder = None
        self.pyaudio_track = None
        self.playback_task = None
        self._pyaudio_out = None
        self._pyaudio_out_stream = None
        self.main_loop = None
        self.pending_ice_candidates = []
        self.last_ice_restart_ts = 0.0
        self.last_remote_answer_sdp = None
        self.video_first_frame_ts = None
        self.video_frame_count = 0
        self.video_monitor_task = None
        self.mic_raw_file = None  # wave file handle for raw mic capture

# Create global state instance
state = GlobalState()
