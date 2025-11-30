# MQTT Topic Architecture - CORRECT IMPLEMENTATION ✅

## 🎯 Kiến trúc Topic đúng

### Mobile → Device (Mobile initiates call)

```
Mobile publishes:
  - mobile/<mobileId>/webrtc/offer       (QoS 1)
  - mobile/<mobileId>/webrtc/answer      (QoS 1)  
  - mobile/<mobileId>/webrtc/candidate   (QoS 0)

Device subscribes:
  - mobile/+/webrtc/offer       (wildcard, QoS 1)
  - mobile/+/webrtc/answer      (wildcard, QoS 1)
  - mobile/+/webrtc/candidate   (wildcard, QoS 0)

Mobile subscribes (to receive device response):
  - device/<deviceId>/webrtc/offer      (QoS 1)
  - device/<deviceId>/webrtc/answer     (QoS 1)
  - device/<deviceId>/webrtc/candidate  (QoS 0)
  - device/<deviceId>/gps               (QoS 1)
  - device/<deviceId>/alert             (QoS 1)

Device publishes (response to mobile):
  - device/<deviceId>/webrtc/offer      (QoS 1)
  - device/<deviceId>/webrtc/answer     (QoS 1)
  - device/<deviceId>/webrtc/candidate  (QoS 0)
  - device/<deviceId>/gps               (QoS 1)
  - device/<deviceId>/alert             (QoS 1)
  - device/<deviceId>/log               (QoS 0)
  - device/<deviceId>/mic               (QoS 0)
```

## ❌ LỖI THƯỜNG GẶP (ĐÃ FIX)

### Lỗi trước đây:
```javascript
// ❌ SAI: Mobile dùng deviceId để publish
savedDeviceId.current = "device001";
publish(`mobile/${savedDeviceId.current}/webrtc/offer`, ...);
// Kết quả: mobile/device001/webrtc/offer ← WRONG!
```

### Code đúng hiện tại:
```javascript
// ✅ ĐÚNG: Mobile dùng mobileId riêng
mobileId.current = "mobile001"; 
publish(`mobile/${mobileId.current}/webrtc/offer`, ...);
// Kết quả: mobile/mobile001/webrtc/offer ← CORRECT!
```

## 🔍 Debug Checklist

Khi test video call, kiểm tra logs:

### Mobile logs phải thấy:
```
[MQTT] 📤 Published to mobile/mobile001/webrtc/offer
[MQTT] 📤 Published to mobile/mobile001/webrtc/candidate
```

### Device logs phải thấy:
```
MQTT message received -> topic=mobile/mobile001/webrtc/offer
Received on mobile/mobile001/webrtc/offer
Offer received (mobile -> device)
📤 Published ICE candidate to device/device001/webrtc/candidate
📤 Answer published to device/device001/webrtc/answer
```

### Nếu KHÔNG thấy device nhận message:
1. ✅ Check mobile publish topic: `mobile/<mobileId>/...`
2. ✅ Check device subscribe: `mobile/+/webrtc/*`
3. ⚠️ Check broker ACL (quyền publish/subscribe)
4. ⚠️ Check broker logs for disconnects
5. ⚠️ Test websocket path (`/` vs `/mqtt`)

## 📝 Ví dụ flow hoàn chỉnh

### 1. Mobile khởi tạo call:
```
Mobile: createOffer() → setLocalDescription()
Mobile: publish("mobile/mobile001/webrtc/offer", offerSDP)
↓
Device: receives on "mobile/mobile001/webrtc/offer"
Device: setRemoteDescription(offerSDP)
Device: createAnswer() → setLocalDescription()
Device: publish("device/device001/webrtc/answer", answerSDP)
↓
Mobile: receives on "device/device001/webrtc/answer"
Mobile: setRemoteDescription(answerSDP)
```

### 2. ICE candidate exchange:
```
Mobile: onicecandidate → publish("mobile/mobile001/webrtc/candidate", cand)
Device: receives → addIceCandidate(cand)

Device: onicecandidate → publish("device/device001/webrtc/candidate", cand)
Mobile: receives → addIceCandidate(cand)
```

### 3. Connection established:
```
Both: ICE state changes to "connected"
Both: Remote tracks received via ontrack event
✅ Video call active!
```

## 🎯 ID Conventions

- **mobileId**: Fixed per mobile client (e.g., `mobile001`, `mobile002`)
- **deviceId**: Fixed per device (e.g., `device001`, `device002`)
- **clientId**: Unique per MQTT session (e.g., `mobile_device001_abc123`)

Note: 
- `deviceId` variable trong mobile code là "device mà mobile muốn kết nối tới"
- `mobileId` là "mobile's own identity để publish signaling"
- Hai giá trị này KHÁC NHAU!
