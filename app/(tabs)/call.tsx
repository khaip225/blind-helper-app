import { useFocusEffect, useNavigation, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { RTCView } from 'react-native-webrtc';
import { useMQTT } from '../../context/MQTTContext';

export default function CallScreen() {
    const { localStream, remoteStream, hangup, callState, answerCall } = useMQTT();
    const router = useRouter();
    const navigation = useNavigation();

    // Tự động ẩn tab bar khi vào màn hình và hiện lại khi thoát
    useFocusEffect(
        React.useCallback(() => {
            const parentNavigation = navigation.getParent();
            parentNavigation?.setOptions({ tabBarStyle: { display: 'none' } });
            return () => parentNavigation?.setOptions({ tabBarStyle: { display: 'flex' } });
        }, [navigation])
    );

    useEffect(() => {
        if (remoteStream) {
            console.log("✅ [CallScreen] Đã nhận được remoteStream!", remoteStream.toURL());
        } else {
            console.log("🟡 [CallScreen] remoteStream hiện đang là null.");
        }
    }, [remoteStream]);

    const handleHangup = () => {
        hangup();
        if (router.canGoBack()) {
            router.back();
        } else {
            router.replace('/(tabs)');
        }
    };
    
    return (
        <View style={styles.container}>
            {/* Logic render chính: Chỉ hiển thị RTCView khi đã kết nối và có remoteStream */}
            {callState === 'connected' && remoteStream ? (
                <RTCView
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
                    {(callState === 'calling' || (callState === 'connected' && !remoteStream)) && (
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

