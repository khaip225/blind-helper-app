/**
 * Expo Notifications Manager
 * Sử dụng expo-notifications thay vì @notifee/react-native
 * Hoạt động tốt với Expo managed workflow
 */

import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { AppState, Platform } from 'react-native';
import { startRingtone, stopRingtone } from './audioManager';

// Configure how notifications are handled when app is in foreground
// Don't show notification banner when app is active - only use incoming-call screen
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: false,
    shouldPlaySound: false,
    shouldSetBadge: false,
    shouldShowBanner: false,
    shouldShowList: false,
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

// Show incoming SOS call notification with full-screen intent
export const showIncomingCallNotification = async (deviceId: string) => {
  try {
    // 🔔 Start ringtone using InCallManager (works in both foreground and background)
    console.log('[Notification] 🔔 Starting ringtone...');
    startRingtone('_BUNDLE_');
    
    // Note: Navigation to incoming-call screen is handled by index.tsx useEffect
    // when callState changes to 'receiving'. Don't navigate here to avoid duplicate navigation.
    
    // Only show notification if app is in background
    const appState = AppState.currentState;
    console.log('[Notification] App state:', appState);
    
    if (appState !== 'active') {
      // Show full-screen notification for background/locked screen
      console.log('[Notification] 🔔 Scheduling full-screen notification (app in background)');
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
    } else {
      console.log('[Notification] ℹ️ App is active - skipping notification (incoming-call screen shown)');
      return null;
    }
  } catch (error) {
    console.error('[Notification] ❌ Failed to show notification:', error);
    return null;
  }
};

// Cancel incoming call notification
export const cancelIncomingCallNotification = async () => {
  try {
    // 🔕 Stop ringtone
    console.log('[Notification] 🔕 Stopping ringtone...');
    stopRingtone();
    
    await Notifications.dismissAllNotificationsAsync();
    console.log('[Notification] ✅ All notifications cancelled');
  } catch (error) {
    console.error('[Notification] ❌ Failed to cancel notifications:', error);
  }
};

// Cancel all notifications
export const cancelAllNotifications = async () => {
  try {
    // 🔕 Stop ringtone
    stopRingtone();
    
    await Notifications.dismissAllNotificationsAsync();
    console.log('[Notification] ✅ All notifications cancelled');
  } catch (error) {
    console.error('[Notification] Failed to cancel all notifications:', error);
  }
};

// Setup notification categories with actions (iOS and Android)
const setupNotificationCategories = async () => {
  // Setup for both iOS and Android
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
  
  if (Platform.OS === 'ios') {
    console.log('[Notification] ✅ iOS categories set');
  } else if (Platform.OS === 'android') {
    console.log('[Notification] ✅ Android categories set');
  }
};

// Setup notification event handlers
export const setupNotificationHandlers = (
  onAnswer: () => Promise<void>,
  onReject: () => void
) => {
  // Handle notification tap or actions
  const notificationSubscription = Notifications.addNotificationResponseReceivedListener(
    async (response) => {
      console.log('[Notification] 🔔 Response received:', response.actionIdentifier);
      console.log('[Notification] 📋 Response data:', response.notification.request.content.data);
      
      const data = response.notification.request.content.data;
      const actionIdentifier = response.actionIdentifier;
      
      // Check if it's an incoming call notification
      if (data?.type === 'incoming_call') {
        console.log('[Notification] ✅ Incoming call notification detected');
        
        // Stop ringtone and cancel notification
        console.log('[Notification] 🔕 Stopping ringtone...');
        stopRingtone();
        await cancelIncomingCallNotification();
        
        if (actionIdentifier === 'answer') {
          // User pressed "Trả lời" button from notification (app in background)
          console.log('[Notification] 📞 Answer button pressed from notification (background)');
          try {
            console.log('[Notification] ⏳ Answering call...');
            await onAnswer(); // Answer the call
            console.log('[Notification] ✅ Call answered successfully');
            
            // Navigate directly to call screen (skip incoming-call screen)
            console.log('[Notification] 🚀 Navigating to call screen...');
            router.replace('/(tabs)/call');
            console.log('[Notification] ✅ Navigation completed');
          } catch (error) {
            console.error('[Notification] ❌ Error in answer flow:', error);
          }
        } else if (actionIdentifier === 'reject') {
          // User pressed "Từ chối" button from notification
          console.log('[Notification] ❌ Reject button pressed from notification');
          onReject();
          // Navigate back to home after rejecting
          router.replace('/(tabs)');
        } else {
          // User tapped notification body (not a button) - also answer and go to call
          console.log('[Notification] 📱 Notification body tapped - answering call (background)');
          try {
            console.log('[Notification] ⏳ Answering call...');
            await onAnswer(); // Answer the call
            console.log('[Notification] ✅ Call answered successfully');
            
            // Navigate directly to call screen (skip incoming-call screen)
            console.log('[Notification] 🚀 Navigating to call screen...');
            router.replace('/(tabs)/call');
            console.log('[Notification] ✅ Navigation completed');
          } catch (error) {
            console.error('[Notification] ❌ Error in answer flow:', error);
          }
        }
      } else {
        console.log('[Notification] ⚠️ Not an incoming call notification, ignoring');
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
