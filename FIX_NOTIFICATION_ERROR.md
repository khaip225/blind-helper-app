# ✅ GIẢI PHÁP ĐÚNG - Dùng expo-notifications

## Vấn đề:
- ❌ @notifee/react-native KHÔNG hỗ trợ Expo managed workflow
- ❌ Gây lỗi khi `expo prebuild`

## Giải pháp:
- ✅ Dùng `expo-notifications` (official Expo package)
- ✅ Hoạt động hoàn hảo với Expo

---

## Các bước thực hiện:

### 1. Uninstall @notifee/react-native
```bash
npm uninstall @notifee/react-native
```

### 2. Cài expo-notifications
```bash
npx expo install expo-notifications
```

### 3. Prebuild
```bash
npx expo prebuild --clean
```

### 4. Build với EAS
```bash
eas build --platform android --profile development
```

---

## ✅ Đã làm:
1. ✅ Xóa @notifee/react-native plugin khỏi app.json
2. ✅ Tạo `utils/expoNotificationManager.ts` - dùng expo-notifications
3. ✅ Update `context/MQTTContext.tsx` - import từ expoNotificationManager

---

## Bạn chỉ cần chạy:

```bash
# 1. Uninstall notifee
npm uninstall @notifee/react-native

# 2. Cài expo-notifications
npx expo install expo-notifications

# 3. Prebuild
npx expo prebuild --clean

# 4. Build
eas build --platform android --profile development
```

---

## Test:
1. Install APK
2. Mở app → Connect device → Cho phép notification
3. Nhấn Home (app ở background)
4. Device gọi SOS
5. ✅ Notification xuất hiện + chuông reo!

---

## Tính năng:
- 🔔 Notification khi nhận cuộc gọi SOS (dù app ở background)
- 📳 Rung + chuông
- 📱 Hiển thị ngay cả khi màn hình khóa
- 👆 Tap notification → Mở app và answer call
- ⏱️ Tự động dismiss sau 30 giây

**Xong! Không cần Firebase, không cần config phức tạp!** 🎉
