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
    const { connect, deviceOnline } = useMQTT();

    // Lắng nghe tin nhắn từ thiết bị để xác nhận kết nối
    useEffect(() => {
        if (deviceOnline) {
            console.log(`✅ Thiết bị ${deviceId} đã xác nhận online!`);
            AsyncStorage.setItem("deviceId", deviceId).then(() => {
                setIsLoading(false);
                router.replace("/(tabs)");
            });
        }
    }, [deviceOnline, deviceId, router]);


    const handleConnect = async () => {
        if (deviceId.trim() === "") {
            Alert.alert("Lỗi", "Vui lòng nhập ID thiết bị.");
            return;
        }

        setIsLoading(true);

        try {
            // Gọi hàm connect từ context
            await connect(deviceId.trim());

            // Sau khi `connect` thành công, app sẽ lắng nghe tin nhắn "presence"
            // Thiết lập một timeout để tránh chờ đợi vô hạn
            setTimeout(() => {
                // Nếu sau 10s vẫn chưa thấy thiết bị online, báo lỗi
                if (!deviceOnline) {
                    setIsLoading(false);
                    Alert.alert("Lỗi", "Không nhận được phản hồi từ thiết bị. Vui lòng kiểm tra lại ID và đảm bảo thiết bị đang online.");
                }
            }, 10000); // Chờ 10 giây

        } catch (error: any) {
            setIsLoading(false);
            Alert.alert("Kết nối thất bại", error.message || "Không thể kết nối đến MQTT broker. Vui lòng thử lại.");
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
                        placeholder="Nhập ID của Jetson Nano..."
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
