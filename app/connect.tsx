import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMQTT } from "../context/MQTTContext"; // Import hook useMQTT

export default function ConnectScreen() {
    const [deviceId, setDeviceId] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const router = useRouter();
    // Lấy hàm connect và disconnect từ context mới
    const { connect, disconnect } = useMQTT();

    // Đảm bảo ngắt kết nối cũ khi vào màn hình này để reset
    useEffect(() => {
        disconnect();
    }, [disconnect]);

    const handleConnect = async () => {
        const trimmedDeviceId = deviceId.trim();
        if (trimmedDeviceId === "") {
            Alert.alert("Lỗi", "Vui lòng nhập ID thiết bị.");
            return;
        }

        setIsLoading(true);

        try {
            // Bước 1: Gọi hàm connect từ context. 
            // Hàm này sẽ resolve (thành công) ngay khi kết nối đến broker xong.
            await connect(trimmedDeviceId);

            // Bước 2: Nếu kết nối thành công, lưu ID và chuyển màn hình ngay lập tức.
            await AsyncStorage.setItem("deviceId", trimmedDeviceId);
            
            setIsLoading(false);
            router.replace("/(tabs)");

        } catch (error: any) {
            // Nếu có lỗi trong quá trình kết nối đến broker, hiển thị lỗi
            setIsLoading(false);
            Alert.alert(
                "Kết nối thất bại", 
                error.message || "Không thể kết nối đến MQTT broker. Vui lòng kiểm tra lại ID và kết nối mạng."
            );
        }
    };

    return (
        <SafeAreaView style={styles.container}>
            {/* Header */}
            <View style={styles.header}>
                <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
                    <Ionicons name="chevron-back" size={24} color="#4169E1" />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Kết Nối Thiết Bị</Text>
                <View style={styles.placeholder} />
            </View>

            {/* Content */}
            <View style={styles.content}>
                <Text style={styles.welcomeText}>Welcome</Text>
                
                <View style={styles.inputSection}>
                    <Text style={styles.inputLabel}>Device ID</Text>
                    <TextInput
                        value={deviceId}
                        onChangeText={setDeviceId}
                        style={styles.textInput}
                        placeholderTextColor="#999"
                        placeholder="Nhập ID của thiết bị..."
                        autoCapitalize="none"
                    />
                </View>

                <TouchableOpacity
                    onPress={handleConnect}
                    style={styles.connectButton}
                    disabled={isLoading}
                >
                    {isLoading ? (
                        <ActivityIndicator color="#fff" />
                    ) : (
                        <Text style={styles.buttonText}>Kết Nối</Text>
                    )}
                </TouchableOpacity>
            </View>
        </SafeAreaView>
    );
}

// Giữ nguyên toàn bộ phần styles của bạn
const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#fff',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#f0f0f0',
    },
    backButton: {
        padding: 4,
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '600',
        color: '#4169E1',
        flex: 1,
        textAlign: 'center',
        marginHorizontal: 16,
    },
    placeholder: {
        width: 32, 
    },
    content: {
        flex: 1,
        paddingHorizontal: 24,
        paddingTop: 40,
    },
    welcomeText: {
        fontSize: 32,
        fontWeight: 'bold',
        color: '#4169E1',
        marginBottom: 60,
    },
    inputSection: {
        marginBottom: 40,
    },
    inputLabel: {
        fontSize: 16,
        fontWeight: '600',
        color: '#333',
        marginBottom: 12,
    },
    textInput: {
        backgroundColor: '#f8f9ff',
        borderRadius: 12,
        paddingHorizontal: 16,
        paddingVertical: 16,
        fontSize: 16,
        color: '#333',
        borderWidth: 1,
        borderColor: '#e8f0ff',
    },
    connectButton: {
        backgroundColor: '#4169E1',
        borderRadius: 25,
        paddingVertical: 16,
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: {
            width: 0,
            height: 2,
        },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    buttonText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '600',
    },
});

