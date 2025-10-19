import { Buffer } from 'buffer';
import Paho from 'paho-mqtt';
import React, { createContext, useContext, useState } from 'react';

// Polyfill Buffer for paho-mqtt library
global.Buffer = Buffer;

// --- Định nghĩa các kiểu dữ liệu cho state ---
interface DeviceInfo {
    pin: number;
    gps: { lat: number; long: number };
    // Thêm các thông tin khác nếu cần
}

interface AlertMessage {
    type: 'obstacle' | 'low_battery' | 'sos';
    message: string;
    timestamp: number;
    // Thêm các thông tin khác nếu cần
}

// --- Định nghĩa kiểu dữ liệu cho Context ---
interface MQTTContextType {
    client: Paho.Client | null;
    isConnected: boolean;
    deviceOnline: boolean;
    deviceInfo: DeviceInfo | null;
    alert: AlertMessage | null;
    rtcOffer: RTCSessionDescriptionInit | null;
    iceCandidates: RTCIceCandidateInit[];
    connect: (deviceId: string) => Promise<void>;
    disconnect: () => void;
    publish: (topic: string, message: string, qos?: 0 | 1 | 2) => void;
    clearWebRTCState: () => void;
}

const MQTTContext = createContext<MQTTContextType | null>(null);

export const MQTTProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [client, setClient] = useState<Paho.Client | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [deviceOnline, setDeviceOnline] = useState(false);

    // --- State quản lý dữ liệu từ MQTT ---
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
    const [alert, setAlert] = useState<AlertMessage | null>(null);
    const [rtcOffer, setRtcOffer] = useState<RTCSessionDescriptionInit | null>(null);
    const [iceCandidates, setIceCandidates] = useState<RTCIceCandidateInit[]>([]);

    const mqttHost = 'broker.hivemq.com';
    const mqttPort = 8000; // ws (non-SSL). For wss use 8884 with useSSL: true
    const clientId = `react-native-mobile-${new Date().getTime()}`;

    const connect = (deviceId: string): Promise<void> => {
        return new Promise((resolve, reject) => {
            console.log(`Đang kết nối đến ${mqttHost}:${mqttPort} (WebSocket /mqtt)`);
            // Sử dụng URL WebSocket rõ ràng để đảm bảo path "/mqtt" của HiveMQ public broker
            const wsUrl = `ws://${mqttHost}:${mqttPort}/mqtt`;
            const newClient = new Paho.Client(wsUrl, clientId);

            // Xử lý tin nhắn đến
            newClient.onMessageArrived = (message: Paho.Message) => {
                const topic = message.destinationName;
                const payload = message.payloadString;
                console.log(`Nhận tin nhắn từ topic: ${topic}`);

                // Xử lý riêng cho presence: không bắt buộc payload là JSON
                if (topic.endsWith('/presence')) {
                    console.log('📶 Nhận thông báo presence từ thiết bị');
                    setDeviceOnline(true);
                    return;
                }

                // Các topic còn lại kỳ vọng payload là JSON
                try {
                    const data = JSON.parse(payload);
                    // Bộ điều phối: phân loại tin nhắn dựa trên topic
                    if (topic.endsWith('/info')) {
                        setDeviceOnline(true);
                        setDeviceInfo(data);
                    } else if (topic.endsWith('/alert')) {
                        setDeviceOnline(true);
                        setAlert({ ...data, timestamp: new Date().getTime() });
                    } else if (topic.endsWith('/webrtc/offer')) {
                        setDeviceOnline(true);
                        setRtcOffer(data);
                    } else if (topic.endsWith('/webrtc/candidate')) {
                        setDeviceOnline(true);
                        setIceCandidates(prev => [...prev, data]);
                    }
                } catch (e) {
                    console.error('Lỗi parse JSON từ tin nhắn (topic không phải presence):', e);
                }
            };

            newClient.onConnectionLost = (responseObject: Paho.MQTTError) => {
                if (responseObject.errorCode !== 0) {
                    console.log('Mất kết nối:', responseObject.errorMessage);
                    setIsConnected(false);
                    setDeviceOnline(false);
                }
            };

            newClient.connect({
                onSuccess: () => {
                    console.log('✅ Kết nối MQTT thành công!');
                    setIsConnected(true);
                    setClient(newClient);
                    setDeviceOnline(false); // reset trạng thái online cho thiết bị mới

                    // --- Tự động subscribe các topic cần thiết ---
                    const topicsToSubscribe = [
                        `device/${deviceId}/presence`,
                        `device/${deviceId}/info`,
                        `device/${deviceId}/alert`,
                        `device/${deviceId}/webrtc/offer`,
                        `device/${deviceId}/webrtc/candidate`,
                    ];
                    
                    console.log("Đang subscribe các topic:", topicsToSubscribe);
                    topicsToSubscribe.forEach(topic => {
                        newClient.subscribe(topic);
                    });
                    
                    // Gửi ping yêu cầu thiết bị phản hồi presence (tuỳ vào thiết bị side xử lý)
                    try {
                        const payload = JSON.stringify({ from: clientId, ts: Date.now() });
                        // 1) Một số thiết bị có thể subscribe theo device/{deviceId}/ping
                        const pingTopic1 = `device/${deviceId}/ping`;
                        const pingMsg1 = new Paho.Message(payload);
                        pingMsg1.destinationName = pingTopic1;
                        newClient.send(pingMsg1);
                        console.log(`Đã gửi ping tới ${pingTopic1}`);

                        // 2) Hoặc thiết bị subscribe theo app/{clientId}/ping
                        const pingTopic2 = `app/${clientId}/ping`;
                        const pingMsg2 = new Paho.Message(payload);
                        pingMsg2.destinationName = pingTopic2;
                        newClient.send(pingMsg2);
                        console.log(`Đã gửi ping tới ${pingTopic2}`);
                    } catch (e) {
                        console.warn('Không thể gửi ping:', e);
                    }
                    
                    resolve();
                },
                onFailure: (err: Paho.MQTTError) => {
                    console.error('❌ Kết nối MQTT thất bại:', err.errorMessage);
                    reject(new Error(err.errorMessage));
                },
                useSSL: false,
                timeout: 10,
            });
        });
    };

    const disconnect = () => {
        if (client) {
            console.log('Đang ngắt kết nối MQTT...');
            client.disconnect();
            setIsConnected(false);
            setClient(null);
        }
    };
    
    const publish = (topic: string, message: string, qos: 0 | 1 | 2 = 1) => {
        if (client && isConnected) {
            console.log(`Publish tới topic ${topic}`);
            const mqttMessage = new Paho.Message(message);
            mqttMessage.destinationName = topic;
            mqttMessage.qos = qos;
            client.send(mqttMessage);
        } else {
            console.warn("Không thể publish vị chưa kết nối MQTT.");
        }
    };

    const clearWebRTCState = () => {
        console.log('🔄 Xóa WebRTC state');
        setRtcOffer(null);
        setIceCandidates([]);
    };

    return (
        <MQTTContext.Provider value={{ client, isConnected, deviceOnline, deviceInfo, alert, rtcOffer, iceCandidates, connect, disconnect, publish, clearWebRTCState }}>
            {children}
        </MQTTContext.Provider>
    );
};

export const useMQTT = (): MQTTContextType => {
    const context = useContext(MQTTContext);
    if (!context) {
        throw new Error('useMQTT phải được sử dụng bên trong một MQTTProvider');
    }
    return context;
};

