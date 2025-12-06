# Hướng dẫn thiết lập Push Notification cho cuộc gọi SOS

## Vấn đề hiện tại:
- Khi app ở background/bị đóng, không nhận được cuộc gọi SOS từ thiết bị
- MQTT chỉ hoạt động khi app ở foreground
- Chuông không reo khi app không mở

## Giải pháp: 

### Option 1: Firebase Cloud Messaging (FCM) - **Khuyến nghị**

**Ưu điểm:**
- ✅ Hoạt động khi app ở background/killed
- ✅ Miễn phí, ổn định
- ✅ Hỗ trợ both Android & iOS

**Cài đặt:**

```bash
# 1. Cài đặt Firebase packages
npm install @react-native-firebase/app @react-native-firebase/messaging

# 2. Rebuild app
cd android && ./gradlew clean
cd .. && npx react-native run-android
```

**Cấu hình Firebase:**
1. Tạo project tại: https://console.firebase.google.com/
2. Thêm Android app với package name: `com.blindhelperapp` (xem trong android/app/build.gradle)
3. Download `google-services.json` → đặt vào `android/app/`
4. Cập nhật `android/build.gradle`:
```gradle
buildscript {
    dependencies {
        classpath 'com.google.gms:google-services:4.4.0'
    }
}
```

5. Cập nhật `android/app/build.gradle`:
```gradle
apply plugin: 'com.google.gms.google-services'
```

**Code implementation:**
- Tạo file `utils/notificationManager.ts` để xử lý push notification
- Gửi FCM token từ mobile app lên MQTT broker
- Device sẽ gửi notification qua Firebase khi có SOS call

---

### Option 2: Notifee (Local Notification Only) - **Đơn giản hơn nhưng hạn chế**

**Ưu điểm:**
- ✅ Không cần Firebase
- ✅ Đơn giản, nhanh

**Nhược điểm:**
- ❌ Chỉ hoạt động khi app ở background (không hoạt động khi killed)
- ❌ Cần app đã mở ít nhất 1 lần

**Cài đặt:**

```bash
npm install @notifee/react-native
cd android && ./gradlew clean
cd .. && npx react-native run-android
```

---

### Option 3: Kết hợp MQTT Background Service + Notifee

**Cách hoạt động:**
- Chạy MQTT service ở background (Android native service)
- Khi nhận offer → hiển thị notification + reo chuông
- Tap notification → mở app và answer call

**Cài đặt:**

```bash
npm install react-native-background-actions @notifee/react-native
```

---

## Khuyến nghị:

**Nếu muốn giải pháp hoàn chỉnh:** Dùng **FCM** (Option 1)

**Nếu muốn nhanh và đơn giản:** Dùng **MQTT Background + Notifee** (Option 3)

---

## Implementation Steps (Chọn Option 1 - FCM):

### 1. Cài đặt packages
```bash
npm install @react-native-firebase/app @react-native-firebase/messaging @notifee/react-native
```

### 2. Setup Firebase Console
- Tạo project
- Download google-services.json
- Enable Cloud Messaging

### 3. Tạo notification manager
```typescript
// utils/notificationManager.ts
import messaging from '@react-native-firebase/messaging';
import notifee from '@notifee/react-native';

export const requestNotificationPermission = async () => {
  const authStatus = await messaging().requestPermission();
  return authStatus === messaging.AuthorizationStatus.AUTHORIZED;
};

export const getFCMToken = async () => {
  const token = await messaging().getToken();
  return token;
};

export const showIncomingCallNotification = async () => {
  const channelId = await notifee.createChannel({
    id: 'sos-call',
    name: 'SOS Calls',
    importance: AndroidImportance.HIGH,
    sound: 'ringtone',
  });

  await notifee.displayNotification({
    title: '🆘 Cuộc gọi SOS',
    body: 'Thiết bị đang gọi khẩn cấp',
    android: {
      channelId,
      category: AndroidCategory.CALL,
      fullScreenAction: {
        id: 'answer_call',
      },
      actions: [
        { title: 'Trả lời', pressAction: { id: 'answer' } },
        { title: 'Từ chối', pressAction: { id: 'reject' } },
      ],
    },
  });
};
```

### 4. Update MQTTContext để gửi FCM token
```typescript
// Gửi token lên broker để device có thể gửi push notification
mqtt.publish(`mobile/${mobileId}/fcm_token`, { token: fcmToken });
```

### 5. Update device code để gửi push qua FCM
```python
# device/mqtt/handlers.py
import requests

def send_push_notification(fcm_token, title, body):
    url = 'https://fcm.googleapis.com/fcm/send'
    headers = {
        'Authorization': 'key=YOUR_SERVER_KEY',
        'Content-Type': 'application/json'
    }
    payload = {
        'to': fcm_token,
        'notification': {
            'title': title,
            'body': body,
            'sound': 'default'
        },
        'data': {
            'type': 'sos_call',
            'device_id': DEVICE_ID
        }
    }
    requests.post(url, headers=headers, json=payload)
```

---

Bạn muốn tôi implement option nào? Tôi khuyến nghị **Option 1 (FCM)** cho giải pháp hoàn chỉnh!
