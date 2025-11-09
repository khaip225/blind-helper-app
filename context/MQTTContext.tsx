import AsyncStorage from '@react-native-async-storage/async-storage';
import { Buffer } from 'buffer';
import Paho from 'paho-mqtt';
import React, { createContext, useCallback, useContext, useRef, useState } from 'react';

// Polyfill Buffer
global.Buffer = Buffer;

// --- Định nghĩa các kiểu dữ liệu ---
interface DeviceInfo {
    pin: number;
    gps: { lat: number; long: number };
}

interface AlertMessage {
    type: string;
    message: string;
    timestamp: number;
}

// --- Định nghĩa kiểu dữ liệu cho Context ---
interface MQTTContextType {
    isConnected: boolean;
    deviceInfo: DeviceInfo | null;
    alertHistory: AlertMessage[];
    
    connect: (deviceId: string) => Promise<void>;
    disconnect: () => void;
    publish: (topic: string, message: string, qos?: 0 | 1 | 2) => void;
    subscribe: (topic: string, callback: (topic: string, payload: string) => void) => void;
}

const MQTTContext = createContext<MQTTContextType | null>(null);

export const MQTTProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [client, setClient] = useState<Paho.Client | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
    const [alertHistory, setAlertHistory] = useState<AlertMessage[]>([]);
    
    const savedDeviceId = useRef<string | null>(null);
    const isConnecting = useRef(false);
    const messageHandlers = useRef<Map<string, (topic: string, payload: string) => void>>(new Map());

    const connect = useCallback((deviceId: string): Promise<void> => {
        savedDeviceId.current = deviceId;

        // Cấu hình MQTT Broker
        const BROKER_HOST = 'mqtt.phuocnguyn.id.vn';
        const BROKER_PORT = 443;
        const BROKER_WS_PATH = '/';
        const BROKER_USE_TLS = true;
        const MQTT_USER = 'mobile001';
        const MQTT_PASSWORD = '123456';

        return new Promise((resolve, reject) => {
            // Tạo client ID unique để tránh conflict
            // Một số broker yêu cầu client ID unique mỗi lần kết nối
            const clientId = `${MQTT_USER}`;
            
            console.log('[MQTT] Connecting with:', {
                host: BROKER_HOST,
                port: BROKER_PORT,
                path: BROKER_WS_PATH,
                clientId: clientId,
                userName: MQTT_USER,
                useSSL: BROKER_USE_TLS,
            });

            const newClient = new Paho.Client(BROKER_HOST, BROKER_PORT, BROKER_WS_PATH, clientId);

            newClient.onMessageArrived = (message: Paho.Message) => {
                const topic = message.destinationName;
                const payload = message.payloadString;
                
                // Gọi handler cho topic cụ thể
                const handler = messageHandlers.current.get(topic);
                if (handler) {
                    handler(topic, payload);
                }
                
                // Xử lý các message mặc định
                handleDefaultMessage(topic, payload);
            };
            
            newClient.onConnectionLost = (response) => {
                if (response.errorCode !== 0) {
                    console.warn('[MQTT] Connection lost:', response.errorMessage);
                    setIsConnected(false);
                    const id = savedDeviceId.current;
                    if (id && !isConnecting.current) {
                        isConnecting.current = true;
                        setTimeout(() => {
                            connect(id).finally(() => { isConnecting.current = false; });
                        }, 2000);
                    }
                }
            };

            const connectOptions: Paho.ConnectionOptions = {
                onSuccess: () => {
                    console.log('[MQTT] ✅ Connected successfully to', BROKER_HOST);
                    setClient(newClient);
                    setIsConnected(true);
                    
                    // Subscribe to default topics
                    const topics = [
                        `device/${deviceId}/info`,
                        `device/${deviceId}/alert`,
                    ];
                    topics.forEach(topic => {
                        newClient.subscribe(topic);
                        console.log(`[MQTT] Subscribed to ${topic}`);
                    });
                    
                    resolve();
                },
                onFailure: (err) => {
                    console.error('[MQTT] ❌ Connection failed:', {
                        errorMessage: err.errorMessage,
                        errorCode: err.errorCode,
                        returnCode: (err as any).returnCode,
                    });
                    setIsConnected(false);
                    reject(err);
                },
                useSSL: BROKER_USE_TLS,
                userName: MQTT_USER,
                password: MQTT_PASSWORD,
                timeout: 10,
                cleanSession: true,
                reconnect: false,
            };

            console.log('[MQTT] Attempting connection with options:', {
                userName: connectOptions.userName,
                password: connectOptions.password ? '***' : 'missing',
                hasPassword: !!connectOptions.password,
                useSSL: connectOptions.useSSL,
                cleanSession: connectOptions.cleanSession,
                clientId: clientId,
            });

            // Debug: Kiểm tra password có được truyền đúng không
            if (!connectOptions.password) {
                console.error('[MQTT] ⚠️ WARNING: Password is missing!');
            }

            newClient.connect(connectOptions);
        });
    }, []);

    // Xử lý các message mặc định (device info, alert)
    const handleDefaultMessage = (topic: string, payload: string) => {
        try {
            const data = JSON.parse(payload);
            
            if (topic.endsWith('/info')) {
                console.log('[MQTT] 📍 Device info updated');
                setDeviceInfo(data);
            }
            
            if (topic.endsWith('/alert')) {
                console.log('[MQTT] 🚨 Alert received:', data.message);
                setAlertHistory(prev => [{ ...data, timestamp: Date.now() }, ...prev].slice(0, 10));
            }
        } catch (e) {
            console.error(`[MQTT] ❌ Error parsing message on ${topic}:`, e);
        }
    };

    // Auto-connect on mount if a deviceId was saved previously
    React.useEffect(() => {
        let cancelled = false;
        const tryAutoConnect = async () => {
            try {
                const id = await AsyncStorage.getItem('deviceId');
                if (cancelled) return;
                if (id && !isConnected && !(client && client.isConnected()) && !isConnecting.current) {
                    isConnecting.current = true;
                    savedDeviceId.current = id;
                    await connect(id).catch((e) => {
                        console.warn('[MQTT] Auto-connect failed:', e?.message || e);
                    });
                    isConnecting.current = false;
                }
            } catch {
                console.warn('[MQTT] Failed to read deviceId from storage');
            }
        };
        tryAutoConnect();
        return () => { cancelled = true; };
    }, [isConnected, client, connect]);

    const disconnect = useCallback(() => {
        console.log('[MQTT] Disconnecting...');
        messageHandlers.current.clear();
        if (client && client.isConnected()) {
            client.disconnect();
        }
        setClient(null);
        setIsConnected(false);
    }, [client]);

    const publish = (topic: string, message: string, qos: 0 | 1 | 2 = 1) => {
        if (client && client.isConnected()) {
            client.send(topic, message, qos, false);
            console.log(`[MQTT] 📤 Published to ${topic}`);
        } else {
            console.warn(`[MQTT] ⚠️ Not connected. Cannot publish to ${topic}`);
        }
    };

    const subscribe = useCallback((topic: string, callback: (topic: string, payload: string) => void) => {
        if (client && client.isConnected()) {
            messageHandlers.current.set(topic, callback);
            client.subscribe(topic);
            console.log(`[MQTT] Subscribed to ${topic} with custom handler`);
        } else {
            console.warn(`[MQTT] ⚠️ Not connected. Cannot subscribe to ${topic}`);
        }
    }, [client]);

    return (
        <MQTTContext.Provider value={{ 
            isConnected, 
            deviceInfo, 
            alertHistory, 
            connect, 
            disconnect, 
            publish,
            subscribe
        }}>
            {children}
        </MQTTContext.Provider>
    );
};

export const useMQTT = (): MQTTContextType => {
    const context = useContext(MQTTContext);
    if (!context) throw new Error('useMQTT must be used within a MQTTProvider');
    return context;
};
