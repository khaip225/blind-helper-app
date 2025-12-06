# Hướng dẫn Setup Firebase Cloud Messaging với EAS Build

## Bước 1: Cài đặt Firebase packages

```bash
npm install @react-native-firebase/app @react-native-firebase/messaging @notifee/react-native
```

## ⚠️ GIẢI PHÁP ĐỌN GIẢN HƠN - KHÔNG CẦN FIREBASE!

**Thay vì dùng Firebase (phức tạp), dùng Notifee + Background Service:**

### Ưu điểm:
- ✅ Không cần setup Firebase Console
- ✅ Không cần Server Key
- ✅ Không cần google-services.json
- ✅ Chỉ cần cài 1 package
- ✅ Hoạt động khi app ở background (không killed)

### Nhược điểm:
- ❌ Không hoạt động khi app bị kill hoàn toàn (swipe away)
- ✅ Nhưng có thể giữ MQTT connection ở background với Background Service

---

## OPTION A: Giải pháp đơn giản (KHUYẾN NGHỊ) ⭐

Dùng **Notifee + MQTT Background Service**

### Bước 1: Cài package
```bash
npm install @notifee/react-native react-native-background-actions
```

### Bước 2: Thêm vào app.json
```json
{
  "expo": {
    "plugins": [
      [
        "@notifee/react-native",
        {
          "android": {
            "largeIcons": ["ic_launcher"],
            "smallIcons": ["ic_notification"]
          }
        }
      ]
    ],
    "android": {
      "permissions": [
        "CAMERA",
        "RECORD_AUDIO",
        "ACCESS_FINE_LOCATION",
        "MODIFY_AUDIO_SETTINGS",
        "POST_NOTIFICATIONS",
        "USE_FULL_SCREEN_INTENT",
        "VIBRATE",
        "WAKE_LOCK",
        "FOREGROUND_SERVICE"
      ]
    }
  }
}
```

### Bước 3: Build với EAS
```bash
# Prebuild
npx expo prebuild --clean

# Build
eas build --platform android --profile development
```

**Xong! Không cần Firebase Console!** 🎉

---

## OPTION B: Nếu BẮT BUỘC phải dùng Firebase (cho full background)

### Bước 2A: Setup Firebase Console (Cập nhật 2025)

**2.1 Tạo Project:**
1. Vào: https://console.firebase.google.com/
2. Click nút **"Create a project"** (hoặc "Add project")
3. Nhập tên: `blind-helper-app`
4. Click **Continue**
5. Tắt Google Analytics → Click **Continue**
6. Đợi 30 giây → Click **Continue**

**2.2 Thêm Android App:**
1. Tại trang chủ project, click biểu tượng **Android** (</> hoặc robot Android)
2. Nếu không thấy, click **Project Overview** (góc trái) → Dấu ⚙️ → **Project settings** → Tab **General** → Scroll xuống → Click **Add app** → Chọn Android

**2.3 Điền thông tin:**
1. **Android package name:** 
   ```bash
   # Kiểm tra package name trong app.json
   # Hoặc chạy lệnh:
   grep -A 5 '"android"' app.json
   ```
   Copy package name (VD: `com.anonymous.blindhelperapp`)

2. **App nickname:** `Blind Helper App` (tùy chọn, có thể bỏ qua)

3. **Debug signing certificate SHA-1:** Để trống (không cần)

4. Click **Register app**

**2.4 Download google-services.json:**
1. Click **Download google-services.json**
2. Lưu file
3. Copy vào project:
   ```bash
   # Windows
   copy %USERPROFILE%\Downloads\google-services.json android\app\

   # Hoặc kéo thả file vào VS Code tại thư mục android/app/
   ```

**2.5 Bỏ qua các bước tiếp theo trong Firebase Console:**
- Click **Next** → **Next** → **Continue to console**
- Đã xong phần Firebase Console!

**2.6 Lấy Server Key (cho device gửi push):**
1. Trong Firebase Console, click **⚙️** (góc trái) → **Project settings**
2. Tab **Cloud Messaging**
3. Scroll xuống phần **Cloud Messaging API (Legacy)**
4. Copy **Server key** (nếu không thấy, click **⋮** → **Manage API in Google Cloud Console** → Enable API)
5. Lưu lại Server Key này

---

## Bước 3: Cấu hình Android (cho cả 2 options)

### 3.1 Update app.json - Option A (Notifee only)
```json
{
  "expo": {
    "plugins": [
      [
        "@notifee/react-native",
        {
          "android": {
            "largeIcons": ["ic_launcher"],
            "smallIcons": ["ic_notification"]
          }
        }
      ]
    ]
  }
}
```

### 3.2 Update app.json - Option B (Firebase + Notifee)
```json
{
  "expo": {
    "plugins": [
      "@react-native-firebase/app",
      "@react-native-firebase/messaging",
      [
        "@notifee/react-native",
        {
          "android": {
            "largeIcons": ["ic_launcher"],
            "smallIcons": ["ic_notification"]
          }
        }
      ]
    ],
    "android": {
      "googleServicesFile": "./google-services.json"
    }
  }
}
```

### 3.3 Thêm permissions
```json
{
  "expo": {
    "android": {
      "permissions": [
        "CAMERA",
        "RECORD_AUDIO",
        "ACCESS_FINE_LOCATION",
        "MODIFY_AUDIO_SETTINGS",
        "POST_NOTIFICATIONS",
        "USE_FULL_SCREEN_INTENT",
        "VIBRATE",
        "WAKE_LOCK",
        "FOREGROUND_SERVICE"
      ]
    }
  }
}

## Bước 3: Cấu hình Android

### 3.1 Update app.json
Thêm Firebase plugin:

```json
{
  "expo": {
    "plugins": [
      "@react-native-firebase/app",
      "@react-native-firebase/messaging",
      [
        "@notifee/react-native",
        {
          "android": {
            "largeIcons": ["ic_launcher"],
            "smallIcons": ["ic_notification"]
          }
        }
      ]
    ],
    "android": {
      "googleServicesFile": "./google-services.json"
    }
  }
}
```

### 3.2 Update app.json - Thêm permissions
```json
{
  "expo": {
    "android": {
      "permissions": [
        "CAMERA",
        "RECORD_AUDIO",
        "ACCESS_FINE_LOCATION",
        "MODIFY_AUDIO_SETTINGS",
        "POST_NOTIFICATIONS",
        "USE_FULL_SCREEN_INTENT",
        "VIBRATE",
        "WAKE_LOCK"
      ]
    }
  }
}
```

## Bước 4: Tạo notification utilities

Tạo file: `utils/notificationManager.ts`

```typescript
import messaging from '@react-native-firebase/messaging';
import notifee, { AndroidImportance, AndroidCategory } from '@notifee/react-native';
import { Alert } from 'react-native';

// Request notification permission
export const requestNotificationPermission = async (): Promise<boolean> => {
  try {
    const authStatus = await messaging().requestPermission();
    const enabled =
      authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
      authStatus === messaging.AuthorizationStatus.PROVISIONAL;

    if (enabled) {
      console.log('[Notification] Permission granted:', authStatus);
    } else {
      console.log('[Notification] Permission denied');
    }
    
    return enabled;
  } catch (error) {
    console.error('[Notification] Permission request failed:', error);
    return false;
  }
};

// Get FCM token
export const getFCMToken = async (): Promise<string | null> => {
  try {
    const token = await messaging().getToken();
    console.log('[FCM] Token:', token);
    return token;
  } catch (error) {
    console.error('[FCM] Failed to get token:', error);
    return null;
  }
};

// Show incoming SOS call notification
export const showIncomingCallNotification = async (deviceId: string) => {
  try {
    // Create channel for high priority notifications
    const channelId = await notifee.createChannel({
      id: 'sos-calls',
      name: 'SOS Calls',
      importance: AndroidImportance.HIGH,
      sound: 'default',
      vibration: true,
    });

    // Display full-screen notification
    await notifee.displayNotification({
      title: '🆘 Cuộc gọi SOS khẩn cấp',
      body: `Thiết bị ${deviceId} đang gọi`,
      android: {
        channelId,
        importance: AndroidImportance.HIGH,
        category: AndroidCategory.CALL,
        fullScreenAction: {
          id: 'incoming_call',
        },
        pressAction: {
          id: 'answer_call',
        },
        actions: [
          {
            title: '📞 Trả lời',
            pressAction: {
              id: 'answer',
            },
          },
          {
            title: '❌ Từ chối',
            pressAction: {
              id: 'reject',
            },
          },
        ],
        ongoing: true, // Cannot be dismissed
        autoCancel: false,
        showTimestamp: true,
        timeoutAfter: 30000, // 30 seconds
      },
    });

    console.log('[Notification] Incoming call notification displayed');
  } catch (error) {
    console.error('[Notification] Failed to show notification:', error);
  }
};

// Cancel incoming call notification
export const cancelIncomingCallNotification = async () => {
  try {
    await notifee.cancelAllNotifications();
    console.log('[Notification] All notifications cancelled');
  } catch (error) {
    console.error('[Notification] Failed to cancel notifications:', error);
  }
};

// Setup background message handler
export const setupBackgroundMessageHandler = () => {
  messaging().setBackgroundMessageHandler(async (remoteMessage) => {
    console.log('[FCM] Background message received:', remoteMessage);
    
    // Check if it's a SOS call
    if (remoteMessage.data?.type === 'sos_call') {
      const deviceId = remoteMessage.data?.deviceId || 'Unknown';
      await showIncomingCallNotification(deviceId);
    }
  });
};

// Setup foreground message handler
export const setupForegroundMessageHandler = (
  onMessage: (message: any) => void
) => {
  return messaging().onMessage(async (remoteMessage) => {
    console.log('[FCM] Foreground message received:', remoteMessage);
    
    // Handle SOS call
    if (remoteMessage.data?.type === 'sos_call') {
      const deviceId = remoteMessage.data?.deviceId || 'Unknown';
      await showIncomingCallNotification(deviceId);
    }
    
    // Call custom handler
    onMessage(remoteMessage);
  });
};

// Setup notification action handler
export const setupNotificationActionHandler = (
  onAnswer: () => void,
  onReject: () => void
) => {
  return notifee.onBackgroundEvent(async ({ type, detail }) => {
    console.log('[Notification] Background event:', type, detail);

    if (detail?.pressAction?.id === 'answer') {
      await cancelIncomingCallNotification();
      onAnswer();
    } else if (detail?.pressAction?.id === 'reject') {
      await cancelIncomingCallNotification();
      onReject();
    }
  });
};
```

## Bước 5: Update MQTTContext.tsx

Thêm FCM initialization và gửi token:

```typescript
import { useEffect } from 'react';
import {
  requestNotificationPermission,
  getFCMToken,
  setupBackgroundMessageHandler,
  setupForegroundMessageHandler,
  showIncomingCallNotification,
  cancelIncomingCallNotification,
  setupNotificationActionHandler,
} from '../utils/notificationManager';

export const MQTTProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // ... existing code ...

  // Initialize FCM
  useEffect(() => {
    let unsubscribeForeground: (() => void) | undefined;
    let unsubscribeAction: (() => void) | undefined;

    const initializeFCM = async () => {
      // Request permission
      const hasPermission = await requestNotificationPermission();
      if (!hasPermission) {
        console.warn('[FCM] Notification permission not granted');
        return;
      }

      // Get FCM token
      const token = await getFCMToken();
      if (token) {
        // Save token to send via MQTT later
        await AsyncStorage.setItem('fcm_token', token);
        console.log('[FCM] Token saved');
      }

      // Setup background handler
      setupBackgroundMessageHandler();

      // Setup foreground handler
      unsubscribeForeground = setupForegroundMessageHandler((message) => {
        console.log('[FCM] Custom foreground handler:', message);
      });

      // Setup notification action handler
      unsubscribeAction = setupNotificationActionHandler(
        () => {
          console.log('[Notification] Answer pressed');
          // Answer call via WebRTC
          webrtc.answerCall();
        },
        () => {
          console.log('[Notification] Reject pressed');
          // Hangup call
          webrtc.hangup();
        }
      );
    };

    initializeFCM();

    return () => {
      unsubscribeForeground?.();
      unsubscribeAction?.();
    };
  }, []);

  // Send FCM token after connecting to device
  const connect = async (deviceId: string) => {
    savedDeviceId.current = deviceId;
    await AsyncStorage.setItem('deviceId', deviceId);
    await mqtt.connect(deviceId);

    // Send FCM token to device via MQTT
    const fcmToken = await AsyncStorage.getItem('fcm_token');
    if (fcmToken) {
      mqtt.publish(`mobile/${mobileId.current}/fcm_token`, {
        token: fcmToken,
        deviceId,
      });
      console.log('[FCM] Token sent to device');
    }
  };

  // Update handleMessage to show notification
  const handleMessage = async (topic: string, payload: string) => {
    // ... existing code ...

    // WebRTC signaling: Offer from device
    if (endsWith('/webrtc/offer')) {
      // Show notification
      await showIncomingCallNotification(savedDeviceId.current || 'Device');
      await webrtc.handleOffer(data);
      return;
    }
  };

  // Cancel notification on hangup
  const disconnect = async () => {
    await cancelIncomingCallNotification();
    webrtc.hangup();
    mqtt.disconnect();
  };

  // ... rest of code ...
};
```

## Bước 6: Update device code (Python)

Tạo file: `device/mqtt/fcm_sender.py`

```python
import requests
import json
from log import setup_logger

logger = setup_logger(__name__)

class FCMSender:
    def __init__(self, server_key: str):
        """
        server_key: Lấy từ Firebase Console > Project Settings > Cloud Messaging > Server Key
        """
        self.server_key = server_key
        self.fcm_url = 'https://fcm.googleapis.com/fcm/send'
        self.mobile_tokens = {}  # {mobile_id: fcm_token}
    
    def register_mobile_token(self, mobile_id: str, token: str):
        """Lưu FCM token của mobile"""
        self.mobile_tokens[mobile_id] = token
        logger.info(f"✅ Registered FCM token for {mobile_id}")
    
    def send_sos_notification(self, mobile_id: str, device_id: str):
        """Gửi push notification khi có SOS call"""
        token = self.mobile_tokens.get(mobile_id)
        if not token:
            logger.warning(f"⚠️ No FCM token for {mobile_id}")
            return False
        
        headers = {
            'Authorization': f'key={self.server_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'to': token,
            'priority': 'high',
            'notification': {
                'title': '🆘 Cuộc gọi SOS khẩn cấp',
                'body': f'Thiết bị {device_id} đang gọi',
                'sound': 'default',
                'android_channel_id': 'sos-calls'
            },
            'data': {
                'type': 'sos_call',
                'deviceId': device_id,
                'timestamp': str(int(time.time()))
            }
        }
        
        try:
            response = requests.post(self.fcm_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ Push notification sent to {mobile_id}")
                return True
            else:
                logger.error(f"❌ FCM error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send push: {e}")
            return False
```

Update `device/mqtt/handlers.py`:

```python
from mqtt.fcm_sender import FCMSender

class MessageHandler:
    def __init__(self, mqtt_client=None):
        # ... existing code ...
        
        # FCM Sender (lấy server key từ Firebase Console)
        FCM_SERVER_KEY = "YOUR_FIREBASE_SERVER_KEY_HERE"
        self.fcm = FCMSender(FCM_SERVER_KEY)
    
    def handle_message(self, topic: str, payload: dict):
        # Handle FCM token registration
        if topic.endswith("/fcm_token"):
            token = payload.get("token")
            mobile_id = topic.split("/")[1]
            if token:
                self.fcm.register_mobile_token(mobile_id, token)
            return
        
        # ... existing code ...
    
    async def initiate_sos_call(self):
        """Initiate SOS call và gửi push notification"""
        logger.info("🆘 Initiating SOS call...")
        
        # Gửi push notification trước
        mobile_id = "mobile001"  # Hoặc lấy từ config
        self.fcm.send_sos_notification(mobile_id, DEVICE_ID)
        
        # Tiếp tục với WebRTC offer
        return await self.webrtc.initiate_sos_call()
```

## Bước 7: EAS Build

```bash
# 1. Prebuild để generate native code
npx expo prebuild --clean

# 2. Build với EAS
eas build --platform android --profile development

# Hoặc build APK để test
eas build --platform android --profile preview

# Production build
eas build --platform android --profile production
```

## Bước 8: Test

### Test local (không cần EAS):
```bash
# Prebuild
npx expo prebuild

# Run development build
npx expo run:android
```

### Test notification:
1. Mở app → Connect device
2. Close app (swipe away)
3. Device gọi SOS
4. Kiểm tra notification xuất hiện + chuông reo
5. Tap "Trả lời" → App mở và answer call

## Lưu ý quan trọng:

1. **google-services.json** phải đặt đúng vị trí: `android/app/google-services.json`
2. **Server Key** trong Firebase Console → Paste vào device code
3. Rebuild app sau khi cài Firebase packages
4. Test trên thiết bị thật, emulator có thể không nhận push notification

## Troubleshooting:

**Không nhận push notification:**
- Check Firebase Server Key đúng chưa
- Check google-services.json đã copy đúng vị trí
- Check app đã request notification permission
- Check FCM token đã gửi lên device
- Check device đã gửi push notification (xem log)

**Build failed:**
- Run `npx expo prebuild --clean`
- Xóa `android/` và `ios/` folder, build lại
- Check eas.json config
