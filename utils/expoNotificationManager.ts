/**
 * Expo Notifications Manager
 * Sử dụng expo-notifications thay vì @notifee/react-native
 * Hoạt động tốt với Expo managed workflow
 */

import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

// Configure how notifications are handled when app is in foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

// Request notification permission
export const requestNotificationPermission = async (): Promise<boolean> => {
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    
    if (finalStatus !== 'granted') {
      console.warn('[Notification] ⚠️ Permission not granted');
      return false;
    }
    
    console.log('[Notification] ✅ Permission granted');
    
    // Setup notification channel for Android
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('sos-calls', {
        name: 'SOS Calls',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#FF0000',
        sound: 'default',
        lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
        bypassDnd: true,
      });
      console.log('[Notification] ✅ Android channel created');
    }
    
    return true;
  } catch (error) {
    console.error('[Notification] ❌ Permission request failed:', error);
    return false;
  }
};

// Show incoming SOS call notification
export const showIncomingCallNotification = async (deviceId: string) => {
  try {
    const notificationId = await Notifications.scheduleNotificationAsync({
      content: {
        title: '🆘 Cuộc gọi SOS khẩn cấp',
        body: `Thiết bị ${deviceId} đang gọi`,
        sound: 'default',
        priority: Notifications.AndroidNotificationPriority.MAX,
        vibrate: [0, 250, 250, 250],
        data: {
          type: 'incoming_call',
          deviceId,
        },
        categoryIdentifier: 'incoming_call',
        ...(Platform.OS === 'android' && {
          channelId: 'sos-calls',
        }),
      },
      trigger: null, // Show immediately
    });

    console.log('[Notification] ✅ Incoming call notification displayed:', notificationId);
    return notificationId;
  } catch (error) {
    console.error('[Notification] ❌ Failed to show notification:', error);
    return null;
  }
};

// Cancel incoming call notification
export const cancelIncomingCallNotification = async () => {
  try {
    await Notifications.dismissAllNotificationsAsync();
    console.log('[Notification] ✅ All notifications cancelled');
  } catch (error) {
    console.error('[Notification] ❌ Failed to cancel notifications:', error);
  }
};

// Cancel all notifications
export const cancelAllNotifications = async () => {
  try {
    await Notifications.dismissAllNotificationsAsync();
    console.log('[Notification] ✅ All notifications cancelled');
  } catch (error) {
    console.error('[Notification] Failed to cancel all notifications:', error);
  }
};

// Setup notification categories with actions (iOS style)
const setupNotificationCategories = async () => {
  if (Platform.OS === 'ios') {
    await Notifications.setNotificationCategoryAsync('incoming_call', [
      {
        identifier: 'answer',
        buttonTitle: '📞 Trả lời',
        options: {
          opensAppToForeground: true,
        },
      },
      {
        identifier: 'reject',
        buttonTitle: '❌ Từ chối',
        options: {
          opensAppToForeground: false,
        },
      },
    ]);
    console.log('[Notification] ✅ iOS categories set');
  }
};

// Setup notification event handlers
export const setupNotificationHandlers = (
  onAnswer: () => void,
  onReject: () => void
) => {
  // Handle notification tap (when user taps on notification)
  const notificationSubscription = Notifications.addNotificationResponseReceivedListener(
    (response) => {
      console.log('[Notification] Response received:', response);
      
      const data = response.notification.request.content.data;
      
      // Check if it's an incoming call notification
      if (data?.type === 'incoming_call') {
        const actionIdentifier = response.actionIdentifier;
        
        if (actionIdentifier === 'answer' || actionIdentifier === Notifications.DEFAULT_ACTION_IDENTIFIER) {
          console.log('[Notification] 📞 Answer action');
          cancelIncomingCallNotification();
          onAnswer();
        } else if (actionIdentifier === 'reject') {
          console.log('[Notification] ❌ Reject action');
          cancelIncomingCallNotification();
          onReject();
        }
      }
    }
  );

  // Handle notification received while app is in foreground
  const receivedSubscription = Notifications.addNotificationReceivedListener((notification) => {
    console.log('[Notification] Received in foreground:', notification);
  });

  // Return cleanup function
  return () => {
    notificationSubscription.remove();
    receivedSubscription.remove();
  };
};

// Initialize notification system
export const initializeNotifications = async () => {
  try {
    console.log('[Notification] Initializing...');
    
    // Request permission
    const hasPermission = await requestNotificationPermission();
    if (!hasPermission) {
      console.warn('[Notification] ⚠️ Permission not granted');
      return false;
    }

    // Setup categories (for iOS action buttons)
    await setupNotificationCategories();
    
    console.log('[Notification] ✅ Initialized successfully');
    return true;
  } catch (error) {
    console.error('[Notification] ❌ Initialization failed:', error);
    return false;
  }
};
