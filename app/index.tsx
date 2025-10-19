import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";

export default function IndexScreen() {
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const checkDevice = async () => {
      console.log("🔄 Đang kiểm tra AsyncStorage...");
      const id = await AsyncStorage.getItem("deviceId");
      console.log("📦 deviceId:", id);

      if (id) {
        console.log("➡️ Điều hướng vào /(tabs)");
        router.replace("/(tabs)");
      } else {
        console.log("➡️ Điều hướng vào /connect");
        router.replace("/connect");
      }
      setLoading(false);
    };

    checkDevice();
  }, []);

  if (loading) {
    return (
      <View className="flex-1 items-center justify-center bg-white">
        <Text className="text-lg">⏳ Đang tải...</Text>
      </View>
    );
  }

  return null;
}
