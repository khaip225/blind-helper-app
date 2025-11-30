import { MQTTProvider } from "@/context/MQTTContext";
import Mapbox from "@rnmapbox/maps";
import { Stack } from "expo-router";
import "react-native-reanimated";
import "../global.css";

Mapbox.setAccessToken("pk.eyJ1Ijoia2hhaTAxMDUiLCJhIjoiY21nMzRodzJ2MTdzYzJqbzlsaWI0MnNmNCJ9.91WY_NHdqYgn5mfII1eeTQ");
export default function RootLayout() {
  return (
    <MQTTProvider>
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="connect" />
      <Stack.Screen name="(tabs)" />
    </Stack>
    </MQTTProvider>
  );
}
