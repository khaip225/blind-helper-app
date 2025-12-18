import { useFocusEffect, useNavigation, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { RTCView, mediaDevices } from 'react-native-webrtc';
import { useMQTT } from '../../hooks/useMQTT';

// Dynamically load InCallManager to avoid eslint error
let InCallManager: any = null;
(async () => {
    try {
        InCallManager = await import('react-native-incall-manager');
        InCallManager = InCallManager?.default || InCallManager;
    } catch (err) {
        console.warn('[CallScreen] react-native-incall-manager not available:', err);
    }
})();

export default function CallScreen() {
    const { localStream, remoteStream, hangup, callState, answerCall } = useMQTT();
    const router = useRouter();
    const navigation = useNavigation();
    const [isSpeakerOn, setIsSpeakerOn] = useState(true); // Default: loa ngoài ON
    const initialSpeakerSetRef = React.useRef(false); // Track if speaker was set initially

    // Tự động ẩn tab bar khi vào màn hình và hiện lại khi thoát
    useFocusEffect(
        React.useCallback(() => {
            const parentNavigation = navigation.getParent();
            parentNavigation?.setOptions({ tabBarStyle: { display: 'none' } });
            return () => parentNavigation?.setOptions({ tabBarStyle: { display: 'flex' } });
        }, [navigation])
    );

    // Set speaker ONLY once when remoteStream first appears
    useEffect(() => {
        if (remoteStream && !initialSpeakerSetRef.current) {
            console.log("✅ [CallScreen] Remote stream received!", remoteStream.toURL());
            initialSpeakerSetRef.current = true;
            
            // Enable speaker by default on first connection
            // Add small delay to ensure InCallManager session is started (from useWebRTC onTrack)
            const enableSpeaker = () => {
                if (InCallManager) {
                    try {
                        InCallManager.setForceSpeakerphoneOn(true);
                        console.log('🔊 [CallScreen] Initial speaker: ON');
                    } catch (e) {
                        console.warn('⚠️ [CallScreen] InCallManager error:', e);
                    }
                } else if (Platform.OS === 'android') {
                    try {
                        (mediaDevices as any).setSpeakerphoneOn?.(true);
                        console.log('🔊 [CallScreen] Initial speaker: ON');
                    } catch (e) {
                        console.warn('⚠️ [CallScreen] setSpeakerphoneOn not available:', e);
                    }
                }
            };
            
            // Delay 300ms to ensure InCallManager.start() has completed
            setTimeout(enableSpeaker, 300);
            
            // Ensure audio tracks are enabled
            try {
                const audioTracks = remoteStream.getAudioTracks?.() || [];
                const videoTracks = remoteStream.getVideoTracks?.() || [];
                audioTracks.forEach((t) => {
                    if (t.enabled === false) t.enabled = true;
                    console.log('🔈 [CallScreen] Audio track enabled:', t.id);
                });
                videoTracks.forEach((t) => {
                    if (t.enabled === false) t.enabled = true;
                });
                console.log('[CallScreen] Tracks -> video:', videoTracks.length, 'audio:', audioTracks.length);
            } catch (e) {
                console.warn('[CallScreen] Error enabling tracks:', e);
            }
        }
    }, [remoteStream]); // Only depend on remoteStream, NOT isSpeakerOn

    const toggleSpeaker = () => {
        const newSpeakerState = !isSpeakerOn;
        setIsSpeakerOn(newSpeakerState);
        
        if (InCallManager) {
            try {
                InCallManager.setForceSpeakerphoneOn(newSpeakerState);
                console.log(`🔊 [CallScreen] Toggled speaker: ${newSpeakerState ? 'ON' : 'OFF'}`);
            } catch (e) {
                console.warn('[CallScreen] Failed to toggle speaker:', e);
            }
        } else if (Platform.OS === 'android') {
            try {
                (mediaDevices as any).setSpeakerphoneOn?.(newSpeakerState);
                console.log(`🔊 [CallScreen] Toggled speaker: ${newSpeakerState ? 'ON' : 'OFF'}`);
            } catch (e) {
                console.warn('[CallScreen] Failed to toggle speaker:', e);
            }
        }
    };

    // Không tự động trả lời nữa – người dùng phải bấm nút Trả lời

    const handleHangup = () => {
        // Reset speaker setup tracking for next call
        initialSpeakerSetRef.current = false;
        hangup();
        if (router.canGoBack()) {
            router.back();
        } else {
            router.replace('/(tabs)');
        }
    };
    
    return (
        <View style={styles.container}>
            {/* Hiển thị video ngay khi có remoteStream (không chờ callState) */}
            {remoteStream ? (
                <RTCView
                    key={(remoteStream as any)?.id || 'remote'}
                    streamURL={remoteStream.toURL()}
                    style={styles.remoteVideo}
                    objectFit="cover"
                />
            ) : (
                // Hiển thị các trạng thái khác trong khi chờ
                <View style={styles.centerContainer}>
                    {callState === 'receiving' && (
                        <>
                            <Text style={styles.statusText}>Đang nhận cuộc gọi SOS...</Text>
                            <TouchableOpacity style={[styles.button, styles.answerButton]} onPress={answerCall}>
                                <Text style={styles.buttonText}>📞 Trả lời</Text>
                            </TouchableOpacity>
                        </>
                    )}
                    {callState === 'calling' && (
                        <>
                            <Text style={styles.statusText}>Đang thiết lập kết nối...</Text>
                            <ActivityIndicator size="large" color="#fff" style={{ marginTop: 20 }} />
                        </>
                    )}
                    {(callState === 'calling' || callState === 'connected') && (
                        <>
                            <Text style={styles.statusText}>Đang kết nối video...</Text>
                            <ActivityIndicator size="large" color="#fff" style={{ marginTop: 20 }} />
                        </>
                    )}
                </View>
            )}

            {/* Video của bạn (màn hình nhỏ) */}
            {localStream && (
                <RTCView
                    streamURL={localStream.toURL()}
                    style={styles.localVideo}
                    objectFit="cover"
                    mirror={true}
                />
            )}

            {/* Các nút điều khiển */}
            <View style={styles.controls}>
                <TouchableOpacity 
                    style={[styles.button, styles.speakerButton, isSpeakerOn && styles.speakerButtonActive]} 
                    onPress={toggleSpeaker}
                >
                    <Text style={styles.buttonText}>
                        {isSpeakerOn ? '🔊 Loa ngoài' : '🔇 Loa trong'}
                    </Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.button, styles.hangupButton]} onPress={handleHangup}>
                    <Text style={styles.buttonText}>❌ Cúp máy</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: 'black',
        justifyContent: 'center',
        alignItems: 'center',
    },
    remoteVideo: {
        position: 'absolute',
        width: '100%',
        height: '100%',
    },
    localVideo: {
        position: 'absolute',
        top: 40, // Tăng khoảng cách từ cạnh trên
        right: 20,
        width: 100,
        height: 150,
        borderRadius: 8,
        borderColor: 'white',
        borderWidth: 2,
        zIndex: 1, // Đảm bảo video local nằm trên
    },
    controls: {
        position: 'absolute',
        bottom: 40,
        flexDirection: 'row',
        justifyContent: 'center',
        width: '100%',
        zIndex: 1,
    },
    button: {
        padding: 15,
        borderRadius: 30,
        marginHorizontal: 10,
    },
    hangupButton: {
        backgroundColor: 'red',
    },
    speakerButton: {
        backgroundColor: '#555',
    },
    speakerButtonActive: {
        backgroundColor: '#4CAF50',
    },
    answerButton: {
        backgroundColor: 'green',
        marginTop: 20,
    },
    buttonText: {
        color: 'white',
        fontSize: 18,
    },
    centerContainer: {
        justifyContent: 'center',
        alignItems: 'center',
    },
    statusText: {
        color: 'white',
        fontSize: 22,
    },
});

