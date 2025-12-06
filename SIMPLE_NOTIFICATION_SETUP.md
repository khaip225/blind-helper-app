# Setup Push Notification ĐƠN GIẢN (Không cần Firebase!)

## ✅ Đã hoàn thành:

### 1. Cài đặt package
```bash
npm install @notifee/react-native
```

### 2. Cấu hình app.json
- ✅ Thêm Notifee plugin
- ✅ Thêm permissions (POST_NOTIFICATIONS, USE_FULL_SCREEN_INTENT, VIBRATE, WAKE_LOCK)

### 3. Tạo notification manager
- ✅ File: `utils/simpleNotificationManager.ts`
- Các functions:
  - `initializeNotifications()` - Khởi tạo system
  - `requestNotificationPermission()` - Xin quyền
  - `showIncomingCallNotification(deviceId)` - Hiển thị notification
  - `cancelIncomingCallNotification()` - Hủy notification
  - `setupNotificationHandlers(onAnswer, onReject)` - Xử lý sự kiện

## 📝 Cần làm tiếp:

### Bước 1: Update MQTTContext.tsx

Thêm vào đầu file:
```typescript
import {
  initializeNotifications,
  setupNotificationHandlers,
  showIncomingCallNotification,
  cancelIncomingCallNotification,
} from '../utils/simpleNotificationManager';
```

Thêm useEffect để initialize:
```typescript
// Initialize notifications
useEffect(() => {
  let unsubscribe: (() => void) | undefined;

  const init = async () => {
    // Initialize notification system
    await initializeNotifications();

    // Setup handlers
    unsubscribe = setupNotificationHandlers(
      () => {
        console.log('[Notification] Answer pressed');
        webrtc.answerCall();
      },
      () => {
        console.log('[Notification] Reject pressed');
        webrtc.hangup();
      }
    );
  };

  init();

  return () => {
    unsubscribe?.();
  };
}, []);
```

Update handleMessage để show notification khi nhận offer:
```typescript
// WebRTC signaling: Offer from device
if (endsWith('/webrtc/offer')) {
    // ✅ Show notification
    await showIncomingCallNotification(savedDeviceId.current || 'Device');
    await webrtc.handleOffer(data);
    return;
}
```

Update disconnect để cancel notification:
```typescript
const disconnect = async () => {
    await cancelIncomingCallNotification();
    webrtc.hangup();
    mqtt.disconnect();
};
```

### Bước 2: Build với EAS

```bash
# Prebuild để generate native code
npx expo prebuild --clean

# Build development
eas build --platform android --profile development
```

### Bước 3: Test

1. Install APK trên điện thoại
2. Mở app → Connect device → **Cho phép notification**
3. **Để app ở background** (nhấn Home, không swipe away)
4. Device gọi SOS
5. ✅ Notification xuất hiện + chuông reo
6. Tap "Trả lời" → App mở và answer call

## ⚠️ Lưu ý:

### Hoạt động:
- ✅ App ở foreground (đang mở)
- ✅ App ở background (Home button)

### KHÔNG hoạt động:
- ❌ App bị killed (swipe away từ recent apps)
- ❌ Device restart chưa mở app

### Để hoạt động khi app bị killed:
Cần dùng Firebase Cloud Messaging (phức tạp hơn, xem FIREBASE_SETUP_GUIDE.md)

## 🐛 Troubleshooting:

**Không nhận notification:**
1. Check permission đã granted chưa (Settings → Apps → Blind Helper App → Notifications)
2. Check log: `[Notification] Initialized successfully`
3. Check MQTT đã connected chưa
4. Check app đang ở foreground/background (không phải killed)

**Build failed:**
```bash
# Clear cache
npx expo prebuild --clean
rm -rf node_modules
npm install

# Build lại
eas build --platform android --profile development
```

**Notification không full screen:**
- Android 10+: Cần permission USE_FULL_SCREEN_INTENT
- Settings → Apps → Blind Helper App → Special app access → Display over other apps → Allow

## 📱 Commands tóm tắt:

```bash
# 1. Cài package
npm install @notifee/react-native

# 2. Update code (xem các bước trên)

# 3. Prebuild
npx expo prebuild --clean

# 4. Build
eas build --platform android --profile development

# Hoặc test local:
npx expo run:android
```

## ✨ Kết quả:

Khi có cuộc gọi SOS từ device:
1. 📳 Điện thoại rung
2. 🔔 Chuông reo (default ringtone)
3. 📱 Notification full-screen xuất hiện (ngay cả khi màn hình khóa)
4. 🆘 Title: "Cuộc gọi SOS khẩn cấp"
5. 📞 Button "Trả lời" và "Từ chối"
6. ⏱️ Tự động tắt sau 30 giây nếu không trả lời
