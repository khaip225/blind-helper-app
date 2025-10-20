// app/setting.tsx
import { useMQTT } from "@/context/MQTTContext";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import React from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function SettingScreen() {
  const router = useRouter();
  const { disconnect } = useMQTT();

  const handleLogout = () => {
    Alert.alert(
      "Xác nhận",
      "Bạn có muốn nhập mã thiết bị khác (đăng xuất)?",
      [
        { text: "Hủy", style: "cancel" },
        {
          text: "Đồng ý",
          onPress: async () => {
            try {
              // 1. Disconnect MQTT
              disconnect();
              console.log("🔌 Đã ngắt kết nối MQTT");
              
              // 2. Xóa deviceId khỏi AsyncStorage
              await AsyncStorage.removeItem("deviceId");
              console.log("🗑️ Đã xóa deviceId khỏi AsyncStorage");
              
              // 3. Small delay để đảm bảo cleanup hoàn tất
              await new Promise(resolve => setTimeout(resolve, 100));
              
              // 4. Navigate về connect screen
              router.replace("/connect");
              console.log("➡️ Đã chuyển về /connect");
            } catch (error) {
              console.error("❌ Lỗi khi đăng xuất:", error);
              Alert.alert("Lỗi", "Không thể đăng xuất. Vui lòng thử lại.");
            }
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Ionicons
          name="chevron-back"
          size={24}
          color="#007AFF"
          onPress={() => router.back()}
        />
        <Text style={styles.title}>Cài Đặt</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* Option 1: Cài đặt thông báo */}
      <TouchableOpacity
        style={styles.option}
        onPress={() => router.push("/notificationSetting")}
      >
        <Text style={styles.optionText}>Cài đặt thông báo</Text>
        <Ionicons name="chevron-forward" size={20} color="#999" />
      </TouchableOpacity>

      {/* Option 2: Nhập mã thiết bị khác */}
      <TouchableOpacity style={styles.option} onPress={handleLogout}>
        <Text style={styles.optionText}>Nhập mã thiết bị khác</Text>
        <Ionicons name="log-out-outline" size={20} color="#999" />
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    marginBottom: 20,
  },
  title: {
    flex: 1,
    textAlign: "center",
    fontSize: 20,
    fontWeight: "bold",
    color: "#007AFF",
    marginRight: 24,
  },
  option: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 16,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: "#eee",
  },
  optionText: {
    fontSize: 16,
    color: "#000",
  },
});
