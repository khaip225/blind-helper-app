import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Mapbox from "@rnmapbox/maps";
import { useRouter } from "expo-router";
import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMQTT } from "../../context/MQTTContext";

export default function MapScreen() {
    const router = useRouter();
    const { deviceInfo, isConnected, startCall } = useMQTT();
    const [deviceId, setDeviceId] = React.useState<string | null>(null);

    React.useEffect(() => {
        const getDeviceId = async () => {
            const id = await AsyncStorage.getItem('deviceId');
            setDeviceId(id);
        };
        getDeviceId();
    }, []);

    const handleVideoCall = async () => {
        if (!isConnected) return;
        // Thực hiện signaling: tạo Offer và gửi qua MQTT, sau đó chuyển sang màn hình call
        await startCall();
        router.push('/call?mode=outgoing');
    };

    // Default location (Đà Nẵng) nếu chưa có GPS
    const defaultCoords = [108.2022, 16.0544]; // [longitude, latitude]
    const hasValidGps = deviceInfo?.gps && deviceInfo.gps.lat !== 0 && deviceInfo.gps.long !== 0;
    const deviceCoords = hasValidGps 
        ? [deviceInfo.gps.long, deviceInfo.gps.lat]
        : defaultCoords;

    return (
        <SafeAreaView style={styles.area}>
            <View style={styles.container}>
                {/* Header */}
                <View style={styles.header}>
                    <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
                        <Ionicons name="chevron-back" size={24} color="#2260ff" />
                    </TouchableOpacity>
                    <Text style={styles.title}>
                        Vị Trí - {deviceId || 'Thiết Bị'}
                    </Text>
                    <View style={styles.headerIcons}>
                        <TouchableOpacity style={styles.iconButton}>
                            <Ionicons name="search" size={20} color="#2260ff" />
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.iconButton}>
                            <Ionicons name="ellipsis-horizontal" size={20} color="#2260ff" />
                        </TouchableOpacity>
                    </View>
                </View>

                {/* Status Banner */}
                {!isConnected && (
                    <View style={styles.statusBanner}>
                        <Ionicons name="warning" size={16} color="#dc2626" />
                        <Text style={styles.statusText}>Thiết bị không kết nối</Text>
                    </View>
                )}

                {/* Mapbox Map */}
                <View style={styles.mapWrapper}>
                    <Mapbox.MapView style={styles.map} styleURL={Mapbox.StyleURL.Street}>
                        <Mapbox.Camera
                            zoomLevel={15}
                            centerCoordinate={deviceCoords}
                            animationMode="flyTo"
                            animationDuration={1000}
                        />
                        <Mapbox.PointAnnotation
                            id="deviceLocation"
                            coordinate={deviceCoords}
                        >
                            <View style={styles.markerContainer}>
                                <View style={styles.markerOuter}>
                                    <View style={styles.markerInner} />
                                </View>
                                <View style={styles.markerLabel}>
                                    <Text style={styles.markerText}>{deviceId || 'Thiết bị'}</Text>
                                </View>
                            </View>
                        </Mapbox.PointAnnotation>
                    </Mapbox.MapView>

                    {/* GPS Coordinates Overlay */}
                    {hasValidGps && (
                        <View style={styles.coordsOverlay}>
                            <Text style={styles.coordsText}>
                                📍 {deviceInfo.gps.lat.toFixed(5)}, {deviceInfo.gps.long.toFixed(5)}
                            </Text>
                        </View>
                    )}
                </View>

                {/* Video Call Button */}
                <View style={styles.buttonContainer}>
                    <TouchableOpacity 
                        style={[styles.videoCallButton, !isConnected && styles.buttonDisabled]}
                        onPress={handleVideoCall}
                        disabled={!isConnected}
                    >
                        <Ionicons name="videocam" size={20} color="#FFFFFF" style={{ marginRight: 8 }} />
                        <Text style={styles.buttonText}>Video Call</Text>
                    </TouchableOpacity>
                </View>
            </View>
        </SafeAreaView>
    );
}
const styles = StyleSheet.create({
    area: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    container: {
        flex: 1,
        backgroundColor: '#FFFFFF',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 12,
        backgroundColor: "#fff",
        borderBottomWidth: 1,
        borderBottomColor: '#f0f0f0',
    },
    backButton: {
        padding: 4,
    },
    title: {
        fontSize: 18,
        fontWeight: "600",
        color: "#2260FF",
        flex: 1,
        textAlign: 'center',
        marginHorizontal: 16,
    },
    headerIcons: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    iconButton: {
        padding: 4,
        marginLeft: 12,
    },
    statusBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#fee2e2',
        paddingVertical: 8,
        gap: 6,
    },
    statusText: {
        color: '#dc2626',
        fontSize: 14,
        fontWeight: '500',
    },
    mapWrapper: {
        flex: 1,
        position: 'relative',
    },
    map: {
        flex: 1,
        width: '100%',
    },
    coordsOverlay: {
        position: 'absolute',
        top: 16,
        left: 16,
        backgroundColor: 'rgba(255,255,255,0.95)',
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: 8,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    coordsText: {
        fontSize: 12,
        color: '#374151',
        fontWeight: '500',
    },
    markerContainer: {
        alignItems: 'center',
    },
    markerOuter: {
        width: 40,
        height: 40,
        backgroundColor: 'rgba(34,96,255,0.2)',
        borderRadius: 20,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 2,
        borderColor: '#2260FF',
    },
    markerInner: {
        width: 14,
        height: 14,
        backgroundColor: '#2260FF',
        borderRadius: 7,
    },
    markerLabel: {
        marginTop: 4,
        backgroundColor: 'white',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#2260FF',
    },
    markerText: {
        fontSize: 11,
        fontWeight: '600',
        color: '#2260FF',
    },
    buttonContainer: {
        paddingHorizontal: 20,
        paddingVertical: 16,
        backgroundColor: '#fff',
    },
    videoCallButton: {
        backgroundColor: '#2260FF',
        paddingVertical: 14,
        paddingHorizontal: 20,
        borderRadius: 25,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        shadowColor: '#000',
        shadowOffset: {
            width: 0,
            height: 2,
        },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    buttonDisabled: {
        backgroundColor: '#9ca3af',
    },
    buttonText: {
        color: "#FFFFFF",
        fontSize: 16,
        fontWeight: "600",
    },
});