import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useRef, useState } from 'react';
import { useMQTTConnection, useWebRTC } from '../hooks';
import { AlertMessage, DeviceInfo, MQTTContextType } from '../types/mqtt.types';

export const MQTTContext = createContext<MQTTContextType | null>(null);

export const MQTTProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
    const [alertHistory, setAlertHistory] = useState<AlertMessage[]>([]);
    
    const mobileId = useRef<string>('mobile001');
    const savedDeviceId = useRef<string | null>(null);

    // Message routing handler
    const handleMessage = async (topic: string, payload: string) => {
        console.log(`[MQTT] 📨 Received on ${topic}`);
        let data: any = null;
        try {
            data = JSON.parse(payload);
        } catch (err) {
            console.warn('[MQTT] Received non-JSON payload or failed parse:', err);
            return;
        }

        const endsWith = (s: string) => topic.endsWith(s);

        // Device -> Mobile: GPS
        if (endsWith('/gps')) {
            console.log('[MQTT] 📍 GPS payload from device:', JSON.stringify(data));
            const gpsData = {
                lat: data?.lat || data?.latitude || 0,
                long: data?.long || data?.lng || data?.longitude || 0,
            };
            setDeviceInfo(prev => ({
                pin: prev?.pin || data?.pin || 0,
                gps: gpsData
            }));
            console.log('[MQTT] 📍 GPS updated:', gpsData);
            return;
        }

        // Device -> Mobile: Alert
        if (endsWith('/alert')) {
            console.log('[MQTT] 🚨 Alert from device:', data);
            setAlertHistory(prev => [{ ...data, timestamp: Date.now() }, ...prev].slice(0, 10));
            return;
        }

        // WebRTC signaling: Offer from device
        if (endsWith('/webrtc/offer')) {
            await webrtc.handleOffer(data);
            return;
        }

        // WebRTC signaling: Answer from device
        if (endsWith('/webrtc/answer')) {
            await webrtc.handleAnswer(data);
            return;
        }

        // WebRTC signaling: Candidate from device
        if (endsWith('/webrtc/candidate')) {
            await webrtc.handleCandidate(data);
            return;
        }
    };

    // Initialize MQTT connection
    const mqtt = useMQTTConnection({
        onMessage: handleMessage,
        onConnectionLost: () => {
            // WebRTC cleanup on connection loss
            webrtc.hangup();
        },
    });

    // Initialize WebRTC
    const webrtc = useWebRTC({
        mobileId: mobileId.current,
        deviceId: savedDeviceId.current,
        publish: mqtt.publish,
    });

    // Enhanced connect function
    const connect = async (deviceId: string) => {
        savedDeviceId.current = deviceId;
        await AsyncStorage.setItem('deviceId', deviceId);
        await mqtt.connect(deviceId);
    };

    // Enhanced disconnect function
    const disconnect = () => {
        webrtc.hangup();
        mqtt.disconnect();
    };

    // Enhanced startCall function
    const startCall = async () => {
        // Ensure MQTT connected
        if (!mqtt.isConnected) {
            const id = savedDeviceId.current || (await AsyncStorage.getItem('deviceId'));
            if (!id) {
                console.error('[WebRTC] ❌ No deviceId, cannot start call');
                throw new Error('Missing deviceId');
            }
            savedDeviceId.current = id;
            console.log('[MQTT] Connecting to device:', id);
            await mqtt.connect(id);
        }

        await webrtc.startCall();
    };

    return (
        <MQTTContext.Provider value={{
            isConnected: mqtt.isConnected,
            deviceInfo,
            alertHistory,
            localStream: webrtc.localStream,
            remoteStream: webrtc.remoteStream,
            callState: webrtc.callState,
            connect,
            disconnect,
            publish: mqtt.publish,
            startCall,
            answerCall: webrtc.answerCall,
            hangup: webrtc.hangup,
        }}>
            {children}
        </MQTTContext.Provider>
    );
};
