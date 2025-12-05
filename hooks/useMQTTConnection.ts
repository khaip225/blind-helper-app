import AsyncStorage from '@react-native-async-storage/async-storage';
import { Buffer } from 'buffer';
import Paho from 'paho-mqtt';
import { useCallback, useEffect, useRef, useState } from 'react';
import { UseMQTTConnectionProps, UseMQTTConnectionReturn } from '../types/mqtt.types';

// Polyfill Buffer
global.Buffer = Buffer;

/**
 * Custom hook for MQTT connection management
 * Handles connection, reconnection, subscription, and publishing
 */
export const useMQTTConnection = ({ 
    onMessage, 
    onConnectionLost 
}: UseMQTTConnectionProps): UseMQTTConnectionReturn => {
    const [client, setClient] = useState<Paho.Client | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const savedDeviceId = useRef<string | null>(null);
    const isConnecting = useRef(false);
    const onMessageRef = useRef(onMessage);

    // Keep onMessage callback up to date
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    /**
     * Connect to MQTT broker
     */
    const connect = useCallback((deviceId: string): Promise<void> => {
        console.log('[MQTT] ▶️ connect() called with deviceId=', deviceId);
        savedDeviceId.current = deviceId;

        const attempt = (port: number, useSSL: boolean): Promise<Paho.Client> => {
            return new Promise((resolve, reject) => {
                // Generate unique mobile clientId
                const rand = Math.random().toString(36).substr(2, 8);
                let clientId = `mobile_${deviceId}_${rand}`;
                if (clientId === deviceId) {
                    clientId = `mobile_${rand}_${Date.now()}`;
                }
                console.log('[MQTT] Using mobile clientId=', clientId);
                
                const newClient = new Paho.Client('mqtt.phuocnguyn.id.vn', port, '/', clientId);

                // Message handler
                newClient.onMessageArrived = (message: Paho.Message) => {
                    onMessageRef.current(message.destinationName, message.payloadString);
                };

                // Enable debug mode
                try {
                    // @ts-ignore
                    Paho.DEBUG = true;
                    console.log('[MQTT] Paho.DEBUG enabled');
                } catch (e) {
                    console.warn('[MQTT] Failed to enable Paho.DEBUG:', e);
                }

                // Connection lost handler
                newClient.onConnectionLost = (response) => {
                    console.warn('[MQTT] Connection lost:', response);
                    setIsConnected(false);
                    onConnectionLost?.();

                    // Reconnection with exponential backoff
                    const id = savedDeviceId.current;
                    if (!id) return;
                    if (isConnecting.current) {
                        console.log('[MQTT] Reconnect already in progress');
                        return;
                    }
                    isConnecting.current = true;
                    const backoffs = [2000, 5000, 10000, 20000, 60000];
                    let attemptNum = 0;

                    const tryReconnect = () => {
                        const delay = backoffs[Math.min(attemptNum, backoffs.length - 1)];
                        console.log(`[MQTT] Reconnect attempt ${attemptNum + 1} in ${delay}ms`);
                        setTimeout(async () => {
                            try {
                                await connect(id);
                                console.log('[MQTT] Reconnected successfully');
                                isConnecting.current = false;
                            } catch (err) {
                                console.warn('[MQTT] Reconnect failed:', (err as any)?.message ?? String(err));
                                attemptNum += 1;
                                if (attemptNum < 6) tryReconnect();
                                else {
                                    console.error('[MQTT] Giving up reconnect attempts');
                                    isConnecting.current = false;
                                }
                            }
                        }, delay);
                    };
                    tryReconnect();
                };

                // Connection options
                const connectOpts: any = {
                    onSuccess: () => {
                        console.log('[MQTT] Connected successfully to mqtt.phuocnguyn.id.vn');
                        resolve(newClient);
                    },
                    onFailure: (err: any) => {
                        console.warn('[MQTT] Connection failed:', err?.errorMessage ?? String(err));
                        reject(err);
                    },
                    useSSL,
                    cleanSession: true,
                    keepAliveInterval: 60,
                    userName: 'mobile001',
                    password: '123456',
                    timeout: 10,
                };

                newClient.connect(connectOpts);
            });
        };

        const finish = (connectedClient: Paho.Client) => {
            setClient(connectedClient);
            setIsConnected(true);
            
            // Subscribe to topics
            const topics = [
                `device/${deviceId}/alert`,
                `device/${deviceId}/gps`,
                `device/${deviceId}/webrtc/offer`,
                `device/${deviceId}/webrtc/answer`,
                `device/${deviceId}/webrtc/candidate`,
            ];
            topics.forEach(topic => {
                const qos = topic.includes('/webrtc/candidate') ? 0 : 1;
                connectedClient.subscribe(topic, { qos });
                console.log(`[MQTT] Subscribed to ${topic} (QoS=${qos})`);
            });
        };

        // Try secure websocket (port 443 with TLS)
        return attempt(443, true)
            .then((c) => { finish(c); })
            .catch((err1) => {
                console.warn('[MQTT] Secure websocket (443) failed, trying fallback 8000:', err1?.errorMessage || err1);
                return attempt(8000, false).then((c) => { finish(c); });
            });
    }, [onConnectionLost]);

    /**
     * Auto-connect on mount if deviceId was saved
     */
    useEffect(() => {
        let cancelled = false;
        const tryAutoConnect = async () => {
            try {
                const id = await AsyncStorage.getItem('deviceId');
                console.log('[MQTT] 🔎 tryAutoConnect read deviceId from AsyncStorage ->', id);
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

    /**
     * Disconnect from MQTT broker
     */
    const disconnect = useCallback(() => {
        console.log('[MQTT] Disconnecting...');
        if (client && client.isConnected()) {
            client.disconnect();
        }
        setClient(null);
        setIsConnected(false);
    }, [client]);

    /**
     * Publish message to MQTT topic
     */
    const publish = useCallback((topic: string, message: string, qos: 0 | 1 | 2 = 1) => {
        if (client && client.isConnected()) {
            client.send(topic, message, qos, false);
            console.log(`[MQTT] 📤 Published to ${topic}`);
        } else {
            console.warn(`[MQTT] ⚠️ Not connected. Cannot publish to ${topic}`);
        }
    }, [client]);

    return {
        client,
        isConnected,
        connect,
        disconnect,
        publish,
    };
};
