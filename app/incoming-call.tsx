import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useMQTT } from '../hooks/useMQTT';
import { cancelIncomingCallNotification } from '../utils/expoNotificationManager';

export default function IncomingCallScreen() {
  const router = useRouter();
  const { answerCall, hangup, callState } = useMQTT();

  useEffect(() => {
    console.log('[IncomingCall] 📊 Current callState:', callState);
    // Cleanup khi component unmount
    return () => {
      console.log('[IncomingCall] Screen unmounted');
    };
  }, [callState]);

  const handleAnswer = async () => {
    console.log('[IncomingCall] 📞 User pressed ANSWER button (foreground)');
    console.log('[IncomingCall] 📊 Current callState before answer:', callState);
    
    try {
      // Stop ringtone and cancel notification
      console.log('[IncomingCall] 🔕 Stopping ringtone...');
      await cancelIncomingCallNotification();
      
      // Answer the call
      console.log('[IncomingCall] 📞 Calling answerCall()...');
      await answerCall();
      console.log('[IncomingCall] ✅ answerCall() completed');
      
      // Navigate to call screen
      console.log('[IncomingCall] 🚀 Navigating to call screen...');
      router.replace('/(tabs)/call');
      console.log('[IncomingCall] ✅ Navigation completed');
    } catch (error) {
      console.error('[IncomingCall] ❌ Error in handleAnswer:', error);
    }
  };

  const handleReject = async () => {
    console.log('[IncomingCall] ❌ User rejected call (foreground)');
    
    // Stop ringtone and cancel notification
    await cancelIncomingCallNotification();
    
    // Hangup the call
    hangup();
    
    // Go back to home screen
    console.log('[IncomingCall] 🚀 Navigating back to home...');
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/(tabs)');
    }
  };

  return (
    <View style={styles.container}>
      {/* Device Icon */}
      <View style={styles.iconContainer}>
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>📱</Text>
        </View>
      </View>

      {/* Caller Info */}
      <Text style={styles.title}>Cuộc gọi SOS khẩn cấp</Text>
      <Text style={styles.subtitle}>Thiết bị đang gọi đến</Text>

      {/* Pulsing Animation */}
      <View style={styles.pulseContainer}>
        <View style={[styles.pulse, styles.pulse1]} />
        <View style={[styles.pulse, styles.pulse2]} />
        <View style={[styles.pulse, styles.pulse3]} />
      </View>

      {/* Action Buttons */}
      <View style={styles.buttonContainer}>
        {/* Reject Button */}
        <TouchableOpacity
          style={[styles.button, styles.rejectButton]}
          onPress={handleReject}
          activeOpacity={0.8}
        >
          <View style={styles.buttonInner}>
            <Text style={styles.buttonIcon}>✖️</Text>
            <Text style={styles.buttonText}>Từ chối</Text>
          </View>
        </TouchableOpacity>

        {/* Answer Button */}
        <TouchableOpacity
          style={[styles.button, styles.answerButton]}
          onPress={handleAnswer}
          activeOpacity={0.8}
        >
          <View style={styles.buttonInner}>
            <Text style={styles.buttonIcon}>📞</Text>
            <Text style={styles.buttonText}>Trả lời</Text>
          </View>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  iconContainer: {
    marginBottom: 30,
  },
  iconCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#16213e',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 3,
    borderColor: '#0f3460',
  },
  iconText: {
    fontSize: 60,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#ffffff',
    marginBottom: 10,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 18,
    color: '#94a3b8',
    marginBottom: 60,
    textAlign: 'center',
  },
  pulseContainer: {
    position: 'absolute',
    top: '35%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pulse: {
    position: 'absolute',
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 2,
    borderColor: '#3b82f6',
    opacity: 0.6,
  },
  pulse1: {
    width: 140,
    height: 140,
    borderRadius: 70,
  },
  pulse2: {
    width: 160,
    height: 160,
    borderRadius: 80,
    opacity: 0.4,
  },
  pulse3: {
    width: 180,
    height: 180,
    borderRadius: 90,
    opacity: 0.2,
  },
  buttonContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    width: '100%',
    paddingHorizontal: 20,
    position: 'absolute',
    bottom: 80,
  },
  button: {
    width: 140,
    height: 140,
    borderRadius: 70,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  rejectButton: {
    backgroundColor: '#ef4444',
  },
  answerButton: {
    backgroundColor: '#22c55e',
  },
  buttonInner: {
    alignItems: 'center',
  },
  buttonIcon: {
    fontSize: 40,
    marginBottom: 8,
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
});
