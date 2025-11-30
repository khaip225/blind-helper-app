# Hướng dẫn sử dụng WebRTC trong MQTT Module

## 📋 Tổng quan

Module này cung cấp khả năng kết nối WebRTC giữa thiết bị IoT (Jetson Nano) và mobile app thông qua MQTT signaling.

## 🏗️ Kiến trúc

```
Mobile App <--MQTT Signaling--> MQTT Broker <--MQTT--> Jetson Nano
           <----WebRTC P2P Connection (Audio/Video)---->
```

## 📁 Cấu trúc file

- `webrtc_manager.py`: Quản lý WebRTC peer connection, ICE, media tracks
- `handlers.py`: Xử lý MQTT messages bao gồm WebRTC signaling
- `client.py`: MQTT client với subscribe topics WebRTC

## 🚀 Cách sử dụng

### 1. Cài đặt dependencies

```bash
pip install aiortc pyav numpy
```

### 2. Khởi động MQTT client

```python
from mqtt.client import MQTTClient

# Khởi tạo MQTT client
mqtt_client = MQTTClient()

# Kết nối đến broker
mqtt_client.connect()
```

### 3. Flow kết nối WebRTC

#### Từ phía Mobile:
1. Mobile gửi **Offer** qua MQTT topic: `mobile/{MOBILE_ID}/webrtc/offer`
2. Mobile gửi **ICE Candidates** qua: `mobile/{MOBILE_ID}/webrtc/candidate`

#### Từ phía Device (Jetson):
1. Device nhận Offer → Khởi tạo PeerConnection
2. Device tạo **Answer** → Gửi qua: `device/{DEVICE_ID}/webrtc/answer`
3. Device gửi **ICE Candidates** qua: `device/{DEVICE_ID}/webrtc/candidate`

### 4. Topics MQTT

| Topic | Direction | Payload | QoS |
|-------|-----------|---------|-----|
| `mobile/{MOBILE_ID}/webrtc/offer` | Mobile → Device | `{type, sdp}` | 1 |
| `mobile/{MOBILE_ID}/webrtc/candidate` | Mobile → Device | `{candidate, sdpMid, sdpMLineIndex}` | 0 |
| `device/{DEVICE_ID}/webrtc/answer` | Device → Mobile | `{type, sdp}` | 1 |
| `device/{DEVICE_ID}/webrtc/candidate` | Device → Mobile | `{candidate, sdpMid, sdpMLineIndex}` | 0 |

## 🎥 Media Tracks

### Video Track
- Nguồn: `/dev/video0` hoặc `/dev/video1` (V4L2)
- Resolution: 640x480
- FPS: 30

### Audio Track
- Nguồn: ALSA devices (hw:3,0 cho USB Audio)
- Sample rate: 48000 Hz
- Channels: Mono

## 🔧 Cấu hình

Trong `config.py`:

```python
DEVICE_ID = "device001"
MOBILE_ID = "mobile001"

TOPICS = {
    'mobile_offer': f"mobile/{MOBILE_ID}/webrtc/offer",
    'mobile_answer': f"mobile/{MOBILE_ID}/webrtc/answer",
    'mobile_candidate': f"mobile/{MOBILE_ID}/webrtc/candidate",
}
```

## 🐛 Debug

### Kiểm tra WebRTC Manager có khả dụng không:

```python
from mqtt.handlers import WEBRTC_AVAILABLE

if WEBRTC_AVAILABLE:
    print("✅ WebRTC available")
else:
    print("❌ WebRTC not available")
```

### Xem logs:

```bash
# Logs sẽ hiển thị các sự kiện WebRTC:
# 📞 Offer received
# ✅ Remote description set
# 📤 Answer published
# 🔄 RELAY/SRFLX/HOST candidates
# ✅ Connection state: connected
# 🎉 WebRTC connection established!
```

## 📊 Trạng thái kết nối

### Connection States:
- `new` 🆕: Mới tạo
- `connecting` 🔄: Đang kết nối
- `connected` ✅: Đã kết nối
- `disconnected` ⚠️: Mất kết nối
- `failed` ❌: Kết nối thất bại
- `closed` 🔒: Đã đóng

### ICE Connection States:
- `new` 🆕: Mới bắt đầu
- `checking` 🔍: Đang kiểm tra candidates
- `connected` ✅: ICE đã kết nối
- `completed` 🏁: Hoàn tất
- `failed` ❌: Thất bại
- `disconnected` ⚠️: Mất kết nối
- `closed` 🔒: Đã đóng

## 🔐 STUN/TURN Servers

Mặc định sử dụng Google STUN:
```python
ice_servers = [
    RTCIceServer(urls=[
        "stun:stun.l.google.com:19302",
        "stun:stun1.l.google.com:19302",
    ])
]
```

Để thêm TURN server (khuyến nghị cho production):
```python
ice_servers.append(
    RTCIceServer(
        urls=["turn:your-turn-server.com:3478"],
        username="username",
        credential="password"
    )
)
```

## ⚠️ Lưu ý

1. **Async handling**: WebRTC handlers chạy trong threads riêng để không block MQTT
2. **Echo cancellation**: Đã được bật bằng PulseAudio (xem hướng dẫn trước)
3. **Mic Playback**: Đã tắt để tránh vọng tiếng
4. **Camera/Mic permission**: Đảm bảo `/dev/video*` và audio devices có quyền truy cập

## 🧪 Testing

### Test từ command line:

```python
# Gửi fake offer để test
import json
from mqtt.client import MQTTClient

client = MQTTClient()
client.connect()

# Fake offer (thay thế bằng offer thật từ mobile)
offer = {
    "type": "offer",
    "sdp": "v=0\r\n..."  # SDP string từ mobile
}

client.publish("mobile/mobile001/webrtc/offer", offer)
```

## 📚 API Reference

### WebRTCManager

```python
class WebRTCManager:
    def __init__(self, device_id: str, mqtt_client=None)
    
    async def initialize_peer_connection() -> bool
    async def handle_offer(sdp: str, offer_type: str = "offer") -> bool
    async def handle_ice_candidate(candidate_data: dict)
    async def close()
    
    # Callbacks
    on_audio_track: Callable
    on_video_track: Callable
    on_connection_state_change: Callable
```

### MessageHandler

```python
class MessageHandler:
    def __init__(self, mqtt_client=None)
    
    def handle_webrtc_offer(payload: dict)
    def handle_webrtc_candidate(payload: dict)
    
    # Callbacks
    async def _handle_incoming_audio(track)
    def _on_webrtc_state_change(state: str)
```

## 🎯 Next Steps

Sau khi nhận được offer từ mobile, bạn cần:

1. ✅ Khởi tạo Peer Connection
2. ✅ Set Remote Description (Offer)
3. ✅ Tạo và gửi Answer
4. ✅ Xử lý ICE Candidates
5. 🔜 Implement audio playback từ mobile
6. 🔜 Thêm video recording/streaming nếu cần

## 📞 Liên hệ

Nếu gặp vấn đề, kiểm tra logs và đảm bảo:
- MQTT broker đang chạy
- Topics đã subscribe đúng
- Camera và microphone hoạt động
- Network cho phép WebRTC traffic

