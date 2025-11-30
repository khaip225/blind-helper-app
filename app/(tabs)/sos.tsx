// sos.tsx
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Mapbox from "@rnmapbox/maps";
import { useRouter } from "expo-router";
import React from "react";
import { Image, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useMQTT } from "../../context/MQTTContext";

const SosScreen = () => {
  const router = useRouter();
  const { deviceInfo, isConnected } = useMQTT();
  const [deviceId, setDeviceId] = React.useState<string | null>(null);
  // const navigatedRef = React.useRef(false);

  React.useEffect(() => {
    const getDeviceId = async () => {
      const id = await AsyncStorage.getItem('deviceId');
      setDeviceId(id);
    };
    getDeviceId();
  }, []);

  // Chỉ điều hướng khi người dùng bấm "Gọi ngay/Video Call" như trước

  // Default location (Đà Nẵng)
  const defaultCoords = [108.2022, 16.0544]; // [longitude, latitude]
  const deviceCoords = deviceInfo?.gps 
    ? [deviceInfo.gps.long, deviceInfo.gps.lat]
    : defaultCoords;

  const handleCall = () => {
    // Trong SOS, thiết bị gửi offer, app trả lời (incoming mode - default)
    router.push('/call?mode=incoming');
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={24} color="#dc2626" />
        </TouchableOpacity>
        <Text style={styles.title}>🆘 SOS</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* SOS Status Banner */}
      <View style={styles.sosBanner}>
        <View style={styles.pulseContainer}>
          <View style={styles.pulseOuter} />
          <View style={styles.pulseMiddle} />
          <View style={styles.pulseInner}>
            <Ionicons name="warning" size={20} color="white" />
          </View>
        </View>
        <Text style={styles.sosText}>Tín hiệu khẩn cấp đang được phát</Text>
      </View>

      {/* Card thông tin */}
      <View style={styles.card}>
        <Image
          source={{ uri: "https://i.pravatar.cc/100" }}
          style={styles.avatar}
        />
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>
            {deviceId || 'Thiết bị'} đang phát tín hiệu
          </Text>
          <Text style={styles.cardSubtitle}>
            {deviceInfo?.gps 
              ? `📍 ${deviceInfo.gps.lat.toFixed(5)}, ${deviceInfo.gps.long.toFixed(5)}`
              : 'Chờ vị trí GPS...'}
          </Text>
          {!isConnected && (
            <Text style={styles.offlineText}>⚠️ Thiết bị không kết nối</Text>
          )}
        </View>
      </View>

      {/* Mapbox Map */}
      <View style={styles.mapContainer}>
        <Mapbox.MapView style={styles.map} styleURL={Mapbox.StyleURL.Street}>
          <Mapbox.Camera
            zoomLevel={16}
            centerCoordinate={deviceCoords}
            animationMode="flyTo"
            animationDuration={1000}
          />
          
          {/* SOS Marker với hiệu ứng nổi bật */}
          <Mapbox.PointAnnotation
            id="sosLocation"
            coordinate={deviceCoords}
          >
            <View style={styles.sosMarkerContainer}>
              <View style={styles.sosMarkerPulse} />
              <View style={styles.sosMarker}>
                <Ionicons name="warning" size={24} color="white" />
              </View>
            </View>
          </Mapbox.PointAnnotation>
        </Mapbox.MapView>

        {/* Battery indicator overlay */}
        {deviceInfo?.pin !== undefined && (
          <View style={styles.batteryOverlay}>
            <Ionicons 
              name={deviceInfo.pin > 20 ? "battery-half" : "battery-dead"} 
              size={16} 
              color={deviceInfo.pin > 20 ? "#16a34a" : "#dc2626"} 
            />
            <Text style={[
              styles.batteryText,
              { color: deviceInfo.pin > 20 ? "#16a34a" : "#dc2626" }
            ]}>
              {deviceInfo.pin}%
            </Text>
          </View>
        )}
      </View>

      {/* Action Buttons */}
      <View style={styles.actionContainer}>
        <TouchableOpacity 
          style={[styles.actionButton, styles.callButton]}
          onPress={handleCall}
          disabled={!isConnected}
        >
          <Ionicons name="call" size={24} color="white" />
          <Text style={styles.actionButtonText}>Gọi ngay</Text>
        </TouchableOpacity>
        
        <TouchableOpacity 
          style={[styles.actionButton, styles.videoButton]}
          onPress={handleCall}
          disabled={!isConnected}
        >
          <Ionicons name="videocam" size={24} color="white" />
          <Text style={styles.actionButtonText}>Video Call</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
};

export default SosScreen;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#fee2e2',
  },
  title: {
    flex: 1,
    textAlign: "center",
    fontSize: 20,
    fontWeight: "bold",
    color: "#dc2626",
  },
  sosBanner: {
    backgroundColor: '#fee2e2',
    paddingVertical: 16,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: '#dc2626',
  },
  pulseContainer: {
    width: 60,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  pulseOuter: {
    position: 'absolute',
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(220, 38, 38, 0.1)',
  },
  pulseMiddle: {
    position: 'absolute',
    width: 45,
    height: 45,
    borderRadius: 22.5,
    backgroundColor: 'rgba(220, 38, 38, 0.2)',
  },
  pulseInner: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#dc2626',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sosText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#dc2626',
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fef3c7",
    marginHorizontal: 16,
    marginTop: 16,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#fbbf24',
  },
  avatar: {
    width: 50,
    height: 50,
    borderRadius: 25,
    marginRight: 12,
    borderWidth: 2,
    borderColor: '#dc2626',
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: "600",
    color: "#92400e",
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 13,
    color: "#78350f",
  },
  offlineText: {
    fontSize: 12,
    color: '#dc2626',
    marginTop: 4,
    fontWeight: '500',
  },
  mapContainer: {
    flex: 1,
    marginTop: 16,
    marginHorizontal: 16,
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 2,
    borderColor: '#dc2626',
    position: 'relative',
  },
  map: {
    flex: 1,
  },
  batteryOverlay: {
    position: 'absolute',
    top: 12,
    right: 12,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.95)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    gap: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  batteryText: {
    fontSize: 13,
    fontWeight: '600',
  },
  sosMarkerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 60,
    height: 60,
  },
  sosMarkerPulse: {
    position: 'absolute',
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(220, 38, 38, 0.2)',
  },
  sosMarker: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#dc2626',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: 'white',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 5,
  },
  actionContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 12,
    backgroundColor: '#fff',
  },
  actionButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  callButton: {
    backgroundColor: '#16a34a',
  },
  videoButton: {
    backgroundColor: '#dc2626',
  },
  actionButtonText: {
    color: 'white',
    fontSize: 15,
    fontWeight: '600',
  },
});
