# MQTT & WebRTC Architecture - Refactored

## 📁 Cấu trúc mới (Đã tái cấu trúc)

```
├── context/
│   └── MQTTContext.tsx          (~118 lines) - Provider chính, kết hợp hooks
├── hooks/
│   ├── useMQTT.ts              (~15 lines) - Export hook cho components
│   ├── useMQTTConnection.ts    (~200 lines) - Logic MQTT connection
│   └── useWebRTC.ts            (~440 lines) - Logic WebRTC signaling
├── config/
│   └── webrtc.config.ts        (~95 lines) - TURN credentials & config
├── utils/
│   └── audioManager.ts         (~145 lines) - Audio control (InCallManager)
└── types/
    └── mqtt.types.ts           (~45 lines) - TypeScript type definitions
```

## 🎯 Chức năng từng file

### 1. **types/mqtt.types.ts**
Định nghĩa tất cả TypeScript types:
- `DeviceInfo` - Thông tin thiết bị (pin, GPS)
- `AlertMessage` - Thông báo cảnh báo
- `CallState` - Trạng thái cuộc gọi ('idle' | 'calling' | 'receiving' | 'connected')
- `MQTTContextType` - Interface cho context

### 2. **config/webrtc.config.ts**
Quản lý cấu hình WebRTC:
- `fetchTurnCredentials()` - Lấy TURN credentials từ Metered.ca (có cache)
- `getConfiguration()` - Trả về cấu hình RTCPeerConnection
- Fallback về Google STUN nếu Metered.ca fail

### 3. **utils/audioManager.ts**
Quản lý audio routing và ringtone:
- `startAudioSession()` - Khởi tạo audio session
- `stopAudioSession()` - Dừng audio session
- `enableSpeaker()` / `disableSpeaker()` - Điều khiển loa
- `startRingtone()` / `stopRingtone()` - Quản lý nhạc chuông
- `cleanupAudio()` - Cleanup khi hangup

### 4. **hooks/useWebRTC.ts**
Custom hook chứa toàn bộ WebRTC logic:
- **States**: `localStream`, `remoteStream`, `callState`
- **Actions**: 
  - `initializePeerConnection()` - Khởi tạo peer connection
  - `startCall()` - Bắt đầu cuộc gọi (tạo offer)
  - `answerCall()` - Trả lời cuộc gọi (tạo answer)
  - `hangup()` - Kết thúc cuộc gọi
- **Signal Handlers**:
  - `handleOffer()` - Xử lý offer từ device
  - `handleAnswer()` - Xử lý answer từ device
  - `handleCandidate()` - Xử lý ICE candidate từ device
- **Tính năng**:
  - ICE candidate buffering
  - Auto audio constraints (volume: 30%, echo cancellation)
  - TURN/STUN support
  - Connection state tracking

### 5. **hooks/useMQTTConnection.ts**
Custom hook quản lý MQTT connection:
- **States**: `client`, `isConnected`
- **Actions**:
  - `connect()` - Kết nối tới broker (mqtt.phuocnguyn.id.vn)
  - `disconnect()` - Ngắt kết nối
  - `publish()` - Publish message
- **Tính năng**:
  - Auto-reconnect với exponential backoff (2s → 60s)
  - Auto-subscribe topics khi connected
  - Auto-connect từ AsyncStorage
  - Callback `onMessage` và `onConnectionLost`

### 6. **context/MQTTContext.tsx**
Provider chính - Kết hợp các hooks:
- Sử dụng `useMQTTConnection` cho MQTT
- Sử dụng `useWebRTC` cho WebRTC
- **Message Routing**: 
  - `/gps` → Update deviceInfo
  - `/alert` → Update alertHistory
  - `/webrtc/offer` → webrtc.handleOffer()
  - `/webrtc/answer` → webrtc.handleAnswer()
  - `/webrtc/candidate` → webrtc.handleCandidate()
- **Enhanced Actions**:
  - `connect()` - Lưu deviceId vào AsyncStorage
  - `disconnect()` - Cleanup cả MQTT & WebRTC
  - `startCall()` - Ensure MQTT connected trước khi gọi

### 7. **hooks/useMQTT.ts**
Export hook đơn giản cho components:
```typescript
const { 
    isConnected, 
    deviceInfo, 
    alertHistory,
    localStream, 
    remoteStream, 
    callState,
    connect, 
    disconnect, 
    publish,
    startCall, 
    answerCall, 
    hangup 
} = useMQTT();
```

## 🔄 Luồng hoạt động

### Kết nối MQTT
```
1. Component gọi connect(deviceId)
2. MQTTContext lưu deviceId → AsyncStorage
3. useMQTTConnection.connect() → Kết nối broker
4. Auto-subscribe topics: alert, gps, webrtc/*
5. Set isConnected = true
```

### Bắt đầu cuộc gọi (Outgoing)
```
1. Component gọi startCall()
2. Ensure MQTT connected
3. useWebRTC.startCall()
   → initializePeerConnection()
   → Get local media (camera + mic)
   → Create offer
   → Publish offer to mobile/{mobileId}/webrtc/offer
4. Device nhận offer → Publish answer
5. handleAnswer() → Set remote description
6. ICE candidates exchange
7. Connection established → callState = 'connected'
```

### Nhận cuộc gọi (Incoming)
```
1. Device publish offer → device/{deviceId}/webrtc/offer
2. handleMessage() → webrtc.handleOffer()
3. Set remote description → callState = 'receiving'
4. startRingtone() - Phát nhạc chuông
5. User bấm Answer → answerCall()
6. Create answer → Publish to mobile/{mobileId}/webrtc/answer
7. ICE candidates exchange
8. Connection established → callState = 'connected'
9. stopRingtone()
```

### Kết thúc cuộc gọi
```
1. Component gọi hangup()
2. cleanupAudio() - Tắt speaker, dừng ringtone
3. Close peer connection
4. Stop tất cả media tracks
5. callState = 'idle'
```

## ✅ Ưu điểm của kiến trúc mới

1. **Separation of Concerns**: Mỗi file có trách nhiệm rõ ràng
2. **Reusability**: Hooks có thể tái sử dụng ở nhiều nơi
3. **Testability**: Dễ test từng hook riêng biệt
4. **Maintainability**: Dễ tìm và sửa lỗi
5. **Readability**: Code gọn gàng, dễ đọc (từ 850 lines → ~100-400 lines/file)
6. **Type Safety**: Tất cả types được định nghĩa rõ ràng
7. **Single Responsibility**: Mỗi file chỉ làm 1 việc

## 🔧 Migration Guide (Nếu cần)

Không cần thay đổi code trong components, vì interface `useMQTT()` giữ nguyên:

```typescript
// ✅ Code components không đổi
const { 
    isConnected, 
    startCall, 
    answerCall, 
    hangup,
    localStream,
    remoteStream,
    callState
} = useMQTT();
```

## 📝 Notes

- **TURN Server**: Sử dụng Metered.ca với API key
- **MQTT Broker**: mqtt.phuocnguyn.id.vn (ports: 443 TLS, 8000 fallback)
- **Mobile ID**: mobile001 (hardcoded trong mobileId.current)
- **QoS**: QoS=1 cho offer/answer/gps, QoS=0 cho candidates
- **Auto-reconnect**: Exponential backoff 2s → 60s (max 6 attempts)
