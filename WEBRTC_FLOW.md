# WebRTC Call Flow - Blind Helper App

## 📞 Hai chế độ gọi

### 1. **OUTGOING Mode** (App gọi thiết bị)
**Khi nào:** Người dùng chủ động gọi từ màn Home hoặc Map
- **Caller (người gọi):** App 📱
- **Answerer (người nhận):** Thiết bị 🤖

**Luồng hoạt động:**
```
1. User nhấn button "📹 Video Call" ở màn Home/Map
2. Navigate: /call?mode=outgoing
3. App tạo WebRTC offer
4. App publish offer → device/{deviceId}/webrtc/offer
5. Thiết bị nhận offer và tạo answer
6. Thiết bị publish answer → device/{deviceId}/webrtc/answer
7. Trao đổi ICE candidates
8. Kết nối WebRTC được thiết lập ✅
```

### 2. **INCOMING Mode** (Thiết bị gọi app - SOS)
**Khi nào:** Thiết bị gặp tình huống khẩn cấp và gửi SOS
- **Caller (người gọi):** Thiết bị 🤖  
- **Answerer (người nhận):** App 📱

**Luồng hoạt động:**
```
1. Thiết bị phát hiện tình huống khẩn cấp
2. Thiết bị tạo WebRTC offer
3. Thiết bị publish offer → device/{deviceId}/webrtc/offer
4. App nhận offer qua MQTTContext (rtcOffer state)
5. App hiển thị alert "Yêu cầu SOS!"
6. User chọn "Trả lời"
7. Navigate: /call?mode=incoming (hoặc mặc định)
8. App set remote description (offer)
9. App tạo answer
10. App publish answer → device/{deviceId}/webrtc/answer
11. Trao đổi ICE candidates
12. Kết nối WebRTC được thiết lập ✅
```

## 🎯 Navigation với mode parameter

### From Home Screen (`app/(tabs)/index.tsx`)
```typescript
// Button "📹 Video Call" 
const handleVideoCall = () => {
  router.push('/call?mode=outgoing'); // App gọi thiết bị
};
```

### From Map Screen (`app/(tabs)/map.tsx`)
```typescript
// Button "Gọi Video"
const handleVideoCall = () => {
  router.push('/call?mode=outgoing'); // App gọi thiết bị
};
```

### From SOS Screen (`app/(tabs)/sos.tsx`)
```typescript
// Button trong SOS (thiết bị đã gửi tín hiệu)
const handleCall = () => {
  router.push('/call?mode=incoming'); // Trả lời cuộc gọi SOS
};
```

### Auto-navigation when SOS received (`index.tsx`)
```typescript
// Khi nhận rtcOffer từ MQTT
const handleAnswerSos = () => {
  router.push('/call?mode=incoming'); // Trả lời SOS tự động
};
```

## 📡 MQTT Topics

### Topics app SUBSCRIBE:
- `device/{deviceId}/info` - Thông tin thiết bị (pin, GPS)
- `device/{deviceId}/alert` - Cảnh báo từ thiết bị
- `device/{deviceId}/webrtc/offer` - Offer từ thiết bị (SOS)
- `device/{deviceId}/webrtc/candidate` - ICE candidates từ thiết bị

### Topics app PUBLISH:
- `device/{deviceId}/webrtc/offer` - Offer khi app gọi thiết bị (outgoing)
- `device/{deviceId}/webrtc/answer` - Answer khi app trả lời (incoming)
- `device/{deviceId}/webrtc/candidate` - ICE candidates của app

## 🔧 Call Screen Logic (`app/(tabs)/call.tsx`)

```typescript
// Nhận mode từ params
const params = useLocalSearchParams();
const callMode = (params.mode as CallMode) || 'incoming';

// useEffect cho INCOMING mode
useEffect(() => {
  if (callMode !== 'incoming' || !rtcOffer) return;
  // App nhận offer, tạo answer, gửi cho thiết bị
}, [callMode, rtcOffer, deviceOnline]);

// useEffect cho OUTGOING mode  
useEffect(() => {
  if (callMode !== 'outgoing' || !deviceOnline) return;
  // App tạo offer, gửi cho thiết bị, chờ answer
}, [callMode, deviceOnline]);
```

## 🧪 Test với Simulator

### Simulator hỗ trợ cả 2 mode:

**Test OUTGOING (App gọi thiết bị):**
```bash
# Chạy simulator ở chế độ "answerer" (nhận offer từ app)
python webrtc_device_simulator.py --answer-mode

# Simulator sẽ:
# 1. Subscribe topic device/device/webrtc/offer
# 2. Chờ nhận offer từ app
# 3. Tạo answer và gửi về
```

**Test INCOMING (Thiết bị gọi app - hiện tại):**
```bash
# Chạy simulator bình thường (tự động gửi offer)
python webrtc_device_simulator.py

# Simulator sẽ:
# 1. Sau 30 giây, tạo offer
# 2. Publish offer → device/device/webrtc/offer
# 3. Chờ nhận answer từ app
```

## 📝 Code Summary

### Files Modified:
1. **app/(tabs)/call.tsx**
   - Added `callMode` param support
   - Separate useEffect for `incoming` and `outgoing` modes
   - Updated UI text based on mode

2. **app/(tabs)/index.tsx**
   - Added `handleVideoCall` for outgoing calls
   - Updated button to "📹 Video Call" with disabled state
   - Navigate with `?mode=outgoing`

3. **app/(tabs)/map.tsx**
   - Updated `handleVideoCall` to use `?mode=outgoing`

4. **app/(tabs)/sos.tsx**
   - Navigate with `?mode=incoming` (explicit)

### Key Differences:

| Aspect | INCOMING Mode | OUTGOING Mode |
|--------|--------------|---------------|
| **Initiator** | Thiết bị → App | App → Thiết bị |
| **App role** | Answerer | Caller |
| **Trigger** | rtcOffer from MQTT | User button press |
| **App creates** | Answer | Offer |
| **App waits for** | Offer | Answer |
| **Status text** | "Chờ cuộc gọi từ thiết bị" | "Đang gọi thiết bị..." |

## 🚀 Usage

1. **Normal video call (Index/Map screens):**
   - Tap "📹 Video Call" button
   - App sends offer to device
   - Device answers
   - Connection established

2. **Emergency SOS:**
   - Device detects emergency
   - Device sends offer to app
   - App shows alert "Yêu cầu SOS!"
   - User taps "Trả lời"
   - App sends answer
   - Connection established

## ✅ Completed Features

- ✅ Dual-mode WebRTC (incoming/outgoing)
- ✅ Navigation with mode parameter
- ✅ Separate logic for caller/answerer
- ✅ MQTT signaling for both modes
- ✅ UI updates based on call mode
- ✅ Device connection status check
- ✅ ICE candidate exchange
- ✅ Video/audio controls (mute, camera toggle)
