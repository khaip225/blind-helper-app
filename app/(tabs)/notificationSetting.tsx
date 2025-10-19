// app/notificationSetting.tsx
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import {
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function NotificationSetting() {
  const router = useRouter();
  const [generalNotification, setGeneralNotification] = useState(true);
  const [bellNotification, setBellNotification] = useState(true);

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={24} color="#007AFF" />
        </TouchableOpacity>
        <Text style={styles.title}>Cài Đặt Thông Báo</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* Option 1 */}
      <View style={styles.option}>
        <Text style={styles.optionText}>Thông Báo Chung</Text>
        <Switch
          value={generalNotification}
          onValueChange={setGeneralNotification}
          trackColor={{ false: "#ccc", true: "#007AFF" }}
          thumbColor={generalNotification ? "#fff" : "#f4f3f4"}
        />
      </View>

      {/* Option 2 */}
      <View style={styles.option}>
        <Text style={styles.optionText}>Chuông</Text>
        <Switch
          value={bellNotification}
          onValueChange={setBellNotification}
          trackColor={{ false: "#ccc", true: "#007AFF" }}
          thumbColor={bellNotification ? "#fff" : "#f4f3f4"}
        />
      </View>
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
    paddingVertical: 12,
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
