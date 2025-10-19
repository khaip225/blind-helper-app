import AsyncStorage from '@react-native-async-storage/async-storage';
import Mapbox from '@rnmapbox/maps';
import { useRouter } from 'expo-router';
import React from 'react';
import { Alert, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMQTT } from '../../context/MQTTContext';

interface AlertMessage {
    type: 'obstacle' | 'low_battery' | 'sos';
    message: string;
    timestamp: number;
}

export default function HomeScreen() {
    const router = useRouter();
    const { isConnected, deviceInfo, alert, rtcOffer, publish } = useMQTT();

    const [deviceId, setDeviceId] = React.useState<string | null>(null);
    const [alertHistory, setAlertHistory] = React.useState<AlertMessage[]>([]);

    React.useEffect(() => {
        const getDeviceId = async () => {
            const id = await AsyncStorage.getItem('deviceId');
            setDeviceId(id);
        };
        getDeviceId();
    }, []);

    React.useEffect(() => {
        if (alert) {
            Alert.alert(
                `Cảnh báo mới: ${alert.type}`,
                `${alert.message}\nLúc: ${new Date(alert.timestamp).toLocaleTimeString()}`
            );
            setAlertHistory(prev => [alert, ...prev].slice(0, 10));
        }
    }, [alert]);

    const handleAnswerSos = React.useCallback(() => {
        if (deviceId) {
            const myAnswer = { type: 'answer', sdp: '...' };
            publish(`mobile/${deviceId}/webrtc/answer`, JSON.stringify(myAnswer));
            console.log('Đã gửi answer cho cuộc gọi SOS.');
            router.push('/call' as any);
        }
    }, [deviceId, publish, router]);

    React.useEffect(() => {
        if (rtcOffer) {
            Alert.alert(
                'Yêu cầu SOS!',
                'Thiết bị đang gửi yêu cầu hỗ trợ khẩn cấp. Bạn có muốn trả lời không?',
                [
                    { text: 'Từ chối', style: 'cancel' },
                    { text: 'Trả lời', onPress: handleAnswerSos },
                ]
            );
        }
    }, [rtcOffer, handleAnswerSos]);

    const handleManualAlert = () => {
        if (deviceId) {
            Alert.alert('Thông báo', 'Chức năng này sẽ gửi cảnh báo đến thiết bị.');
        }
    };

    return (
        <SafeAreaView style={styles.container}>
            <ScrollView style={styles.scrollView}>
                <View style={styles.header}>
                    <View style={styles.userInfo}>
                        <Image
                            source={{ uri: 'https://placehold.co/40x40/e0e7ff/3b82f6?text=JD' }}
                            style={styles.avatar}
                        />
                        <View style={styles.welcomeText}>
                            <Text style={styles.welcomeSubtext}>Hi, Welcome Back</Text>
                            <Text style={styles.userName}>John Doe</Text>
                        </View>
                    </View>
                    <View style={styles.headerIcons}>
                        <TouchableOpacity style={styles.iconButton} onPress={() => router.push('/alert')}>
                            <Text style={styles.iconText}>🔔</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.iconButton} onPress={() => router.push('/setting')}>
                            <Text style={styles.iconText}>⚙️</Text>
                        </TouchableOpacity>
                    </View>
                </View>

                <Text style={styles.sectionTitle}>Thiết Bị Của Tôi ({deviceId || '...'})</Text>
                <View style={styles.deviceCard}>
                    <Image
                        source={{ uri: 'https://placehold.co/60x60/9ca3af/ffffff?text=Thiết+bị' }}
                        style={styles.deviceImage}
                    />
                    <View style={styles.deviceInfo}>
                        <Text style={styles.batteryText}>
                            🔋 Pin: {isConnected && deviceInfo ? `${deviceInfo.pin}%` : 'N/A'}
                        </Text>
                        <Text style={styles.connectionText}>
                            🌐 Kết nối:
                            <Text style={[styles.boldText, { color: isConnected ? '#16a34a' : '#dc2626' }]}>
                                {isConnected ? ' online' : ' offline'}
                            </Text>
                        </Text>
                        <Text style={styles.gpsText}>
                            📍 GPS: {isConnected && deviceInfo ? `${deviceInfo.gps.lat.toFixed(4)}, ${deviceInfo.gps.long.toFixed(4)}` : 'Không xác định'}
                        </Text>
                    </View>
                </View>

                <TouchableOpacity onPress={() => router.push('/map')}>
                    <View style={styles.mapContainer}>
                        <View style={styles.mapWrapper}>
                            <Mapbox.MapView style={styles.map} styleURL={Mapbox.StyleURL.Street}>
                                {deviceInfo?.gps && (
                                    <Mapbox.Camera
                                        zoomLevel={15}
                                        centerCoordinate={[deviceInfo.gps.long, deviceInfo.gps.lat]}
                                        animationMode="flyTo"
                                        animationDuration={800}
                                    />
                                )}
                                {deviceInfo?.gps && (
                                    <Mapbox.PointAnnotation
                                        id="deviceMarker"
                                        coordinate={[deviceInfo.gps.long, deviceInfo.gps.lat]}
                                    >
                                        <View style={styles.markerOuter}>
                                            <View style={styles.markerInner} />
                                        </View>
                                    </Mapbox.PointAnnotation>
                                )}
                            </Mapbox.MapView>
                            {!deviceInfo?.gps && (
                                <View style={styles.mapEmptyOverlay}>
                                    <Text style={styles.mapText}>Chưa có vị trí từ thiết bị</Text>
                                </View>
                            )}
                        </View>
                    </View>
                </TouchableOpacity>

                <View style={styles.alertSection}>
                    <View style={styles.contactRow}>
                        <Image
                            source={{ uri: 'https://placehold.co/40x40' }}
                            style={styles.contactAvatar}
                        />
                        <TouchableOpacity style={styles.callButton} onPress={handleAnswerSos}>
                            <Text style={styles.buttonText}>📞 Gọi SOS</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.alertButton} onPress={handleManualAlert}>
                            <Text style={styles.buttonText}>⚠️ Cảnh báo</Text>
                        </TouchableOpacity>
                    </View>

                    <Text style={styles.alertTitle}>Lịch sử cảnh báo</Text>
                    <View style={styles.alertList}>
                        {alertHistory.length > 0 ? (
                            alertHistory.slice(0, 3).map((item, index) => (
                                <Text key={index} style={styles.alertItem}>
                                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} — {item.message}
                                </Text>
                            ))
                        ) : (
                            <Text style={styles.alertItem}>Chưa có cảnh báo nào.</Text>
                        )}
                    </View>
                    <TouchableOpacity onPress={() => router.push('/alert')}>
                        <Text style={styles.viewAllText}>[Xem tất cả →]</Text>
                    </TouchableOpacity>
                </View>
            </ScrollView>
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scrollView: {
        flex: 1,
        paddingHorizontal: 16,
        paddingTop: 16,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 20,
    },
    userInfo: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    avatar: {
        width: 40,
        height: 40,
        borderRadius: 20,
    },
    welcomeText: {
        marginLeft: 12,
    },
    welcomeSubtext: {
        color: '#3b82f6',
        fontSize: 12,
    },
    userName: {
        color: '#000',
        fontSize: 14,
        fontWeight: '600',
    },
    headerIcons: {
        flexDirection: 'row',
        gap: 8,
    },
    iconButton: {
        width: 32,
        height: 32,
        backgroundColor: '#e5e7eb',
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    iconText: {
        fontSize: 14,
    },
    sectionTitle: {
        fontSize: 16,
        fontWeight: 'bold',
        textAlign: 'center',
        marginBottom: 12,
        color: '#000',
    },
    deviceCard: {
        backgroundColor: '#dbeafe',
        borderRadius: 12,
        padding: 16,
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 16,
    },
    deviceImage: {
        width: 60,
        height: 60,
        backgroundColor: '#9ca3af',
        borderRadius: 8,
        marginRight: 16,
    },
    deviceInfo: {
        flex: 1,
    },
    batteryText: {
        color: '#3f3f46',
        marginBottom: 4,
        fontWeight: '500',
    },
    connectionText: {
        color: '#3f3f46',
        marginBottom: 4,
        fontWeight: '500',
    },
    boldText: {
        fontWeight: 'bold',
    },
    gpsText: {
        color: '#3f3f46',
        fontWeight: '500',
    },
    mapContainer: {
        marginBottom: 16,
    },
    mapWrapper: {
        height: 200,
        borderRadius: 12,
        overflow: 'hidden',
        backgroundColor: '#e5e7eb',
    },
    map: {
        flex: 1,
    },
    mapPlaceholder: {
        height: 200,
        backgroundColor: '#e5e7eb',
        borderRadius: 12,
        justifyContent: 'center',
        alignItems: 'center',
    },
    mapEmptyOverlay: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        justifyContent: 'center',
        alignItems: 'center',
    },
    mapText: {
        color: '#6b7280',
        fontSize: 14,
    },
    markerOuter: {
        width: 28,
        height: 28,
        backgroundColor: 'rgba(59,130,246,0.25)',
        borderRadius: 14,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: 'rgba(59,130,246,0.6)',
    },
    markerInner: {
        width: 10,
        height: 10,
        backgroundColor: '#2563eb',
        borderRadius: 5,
    },
    alertSection: {
        backgroundColor: '#dbeafe',
        borderRadius: 12,
        padding: 16,
        marginBottom: 20,
    },
    contactRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 16,
        gap: 12,
    },
    contactAvatar: {
        width: 40,
        height: 40,
        borderRadius: 20,
    },
    callButton: {
        backgroundColor: '#fff',
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 8,
        flex: 1,
        alignItems: 'center',
    },
    alertButton: {
        backgroundColor: '#fff',
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 8,
        flex: 1,
        alignItems: 'center',
    },
    buttonText: {
        fontSize: 12,
        color: '#000',
        fontWeight: '600',
    },
    alertTitle: {
        fontWeight: '600',
        marginBottom: 8,
        color: '#000',
    },
    alertList: {
        marginBottom: 8,
    },
    alertItem: {
        color: '#3f3f46',
        marginBottom: 4,
        fontSize: 13,
    },
    viewAllText: {
        color: '#3b82f6',
        fontSize: 13,
        fontWeight: '500',
    },
});

