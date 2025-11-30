import Mapbox from '@rnmapbox/maps';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { Alert, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMQTT } from '../../context/MQTTContext';

// TODO: Thay thế bằng Public Token của bạn
Mapbox.setAccessToken('pk.eyJ1Ijoia2hhaTAxMDUiLCJhIjoiY21nMzRodzJ2MTdzYzJqbzlsaWI0MnNmNCJ9.91WY_NHdqYgn5mfII1eeTQ');

export default function HomeScreen() {
    const router = useRouter();
    const { isConnected, deviceInfo, alertHistory, callState, answerCall, startCall, hangup } = useMQTT();

    const mapRef = React.useRef<Mapbox.MapView>(null);
    const cameraRef = React.useRef<Mapbox.Camera>(null);

    // Lấy deviceId từ AsyncStorage khi component mount
    // If you need the deviceId elsewhere, you can fetch it where required.

    // Xử lý khi có cuộc gọi đến (trạng thái 'receiving')
    useEffect(() => {
        if (callState === 'receiving') {
            Alert.alert(
                "Yêu cầu SOS!",
                "Thiết bị đang gửi yêu cầu hỗ trợ khẩn cấp. Bạn có muốn trả lời không?",
                [
                    { text: "Từ chối", style: "cancel", onPress: hangup },
                    { text: "Trả lời", onPress: async () => {
                        await answerCall();
                        router.push('/call');
                    }}
                ]
            );
        }
    }, [callState, answerCall, hangup, router]);
    
    // Tự động di chuyển bản đồ theo GPS
    useEffect(() => {
        if (deviceInfo?.gps && cameraRef.current) {
            cameraRef.current.setCamera({
                centerCoordinate: [deviceInfo.gps.long, deviceInfo.gps.lat],
                zoomLevel: 16,
                animationMode: 'flyTo',
                animationDuration: 1500,
            });
        }
    }, [deviceInfo?.gps]);

    const handleStartCall = async () => {
        if (isConnected) {
            await startCall();
            router.push('/call');
        } else {
            Alert.alert("Lỗi", "Không thể thực hiện cuộc gọi. Vui lòng kiểm tra kết nối MQTT.");
        }
    };


    return (
        <SafeAreaView style={styles.container}>
            <ScrollView style={styles.scrollView}>
                {/* Header */}
                <View style={styles.header}>
                    <View style={styles.userInfo}>
                        <Image
                        source={{ uri: 'https://placehold.co/40x40' }}
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

                {/* Thiết bị của tôi Card */}
                <Text style={styles.sectionTitle}>Thiết Bị Của Tôi</Text>
                <View style={styles.deviceCard}>
                     <Image source={{ uri: 'https://placehold.co/60x60/3b82f6/FFF?text=DEV' }} style={styles.deviceImage} />
                    <View style={styles.deviceInfo}>
                        <Text style={styles.batteryText}>
                            🔋 Pin: {isConnected && deviceInfo ? `${deviceInfo.pin}%` : 'N/A'}
                        </Text>
                        <Text style={styles.connectionText}>
                            🌐 Kết nối: 
                            <Text style={{ fontWeight: 'bold', color: isConnected ? '#16a34a' : '#dc2626' }}>
                                {isConnected ? ' online' : ' offline'}
                            </Text>
                        </Text>
                        <Text style={styles.gpsText}>
                            📍 GPS: {isConnected && deviceInfo?.gps && deviceInfo.gps.lat !== 0 ? `${Number(deviceInfo.gps.lat).toFixed(6)}, ${Number(deviceInfo.gps.long).toFixed(6)}` : 'Không xác định'}
                        </Text>
                    </View>
                </View>

                {/* Map Section */}
                <View style={styles.mapContainer}>
                    <Mapbox.MapView
                        ref={mapRef}
                        style={styles.map}
                        styleURL={Mapbox.StyleURL.Street}
                    >
                        <Mapbox.Camera
                            ref={cameraRef}
                            defaultSettings={{
                                centerCoordinate: [108.22, 16.07], // Vị trí mặc định (Đà Nẵng)
                                zoomLevel: 12,
                            }}
                        />
                        {deviceInfo?.gps && (
                            <Mapbox.PointAnnotation
                                id="deviceMarker"
                                coordinate={[deviceInfo.gps.long, deviceInfo.gps.lat]}
                            >
                                <View style={styles.marker} />
                            </Mapbox.PointAnnotation>
                        )}
                    </Mapbox.MapView>
                </View>

                {/* Contact & Alert Section */}
                <View style={styles.alertSection}>
                    <View style={styles.contactRow}>
                        <Image source={{ uri: 'https://placehold.co/40x40' }} style={styles.contactAvatar} />
                        <TouchableOpacity style={styles.callButton} onPress={handleStartCall}>
                            <Text style={styles.buttonText}>📞 Gọi</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.alertButton}>
                            <Text style={styles.buttonText}>⚠️ Cảnh báo</Text>
                        </TouchableOpacity>
                    </View>

                    <Text style={styles.alertTitle}>Lịch sử cảnh báo</Text>
                    <View style={styles.alertList}>
                        {alertHistory.length > 0 ? (
                            alertHistory.slice(0, 3).map((alert, index) => (
                                <Text key={index} style={styles.alertItem}>
                                    {new Date(alert.timestamp).toLocaleTimeString()} — {alert.message}
                                </Text>
                            ))
                        ) : (
                            <Text style={styles.alertItem}>Chưa có cảnh báo nào.</Text>
                        )}
                    </View>
                    <TouchableOpacity onPress={() => router.push("/alert")}>
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
        color: '#1f2937',
        marginBottom: 4,
    },
    connectionText: {
        color: '#1f2937',
        marginBottom: 4,
    },
    boldText: {
        fontWeight: 'bold',
    },
    gpsText: {
        color: '#1f2937',
    },
    mapContainer: {
        marginBottom: 16,
        height: 250,
        borderRadius: 12,
        overflow: 'hidden',
    },
    map: {
        flex: 1,
    },
    marker: {
        width: 20,
        height: 20,
        borderRadius: 10,
        backgroundColor: 'blue',
        borderColor: 'white',
        borderWidth: 3,
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
        paddingVertical: 6,
        borderRadius: 8,
    },
    alertButton: {
        backgroundColor: '#fff',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 8,
    },
    buttonText: {
        fontSize: 12,
        color: '#000',
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
        color: '#000',
        marginBottom: 2,
        fontSize: 13,
    },
    viewAllText: {
        color: '#3b82f6',
        fontSize: 13,
    },
});

