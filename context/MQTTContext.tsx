import AsyncStorage from '@react-native-async-storage/async-storage';
import { Buffer } from 'buffer';
import Paho from 'paho-mqtt';
import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { mediaDevices, MediaStream, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';

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

type CallState = 'idle' | 'calling' | 'receiving' | 'connected';

// Cấu hình STUN servers
const configuration = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ],
};

// --- Định nghĩa kiểu dữ liệu cho Context ---
interface MQTTContextType {
    isConnected: boolean;
    deviceInfo: DeviceInfo | null;
    alertHistory: AlertMessage[];
    
    // WebRTC States
    localStream: MediaStream | null;
    remoteStream: MediaStream | null;
    callState: CallState;
    
    connect: (deviceId: string) => Promise<void>;
    disconnect: () => void;
    publish: (topic: string, message: string, qos?: 0 | 1 | 2) => void;
    
    // WebRTC Actions
    startCall: () => Promise<void>;
    answerCall: () => Promise<void>;
    hangup: () => void;
}

const MQTTContext = createContext<MQTTContextType | null>(null);

export const MQTTProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [client, setClient] = useState<Paho.Client | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
    const [alertHistory, setAlertHistory] = useState<AlertMessage[]>([]);

    // --- WebRTC States ---
    const [localStream, setLocalStream] = useState<MediaStream | null>(null);
    const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
    const [callState, setCallState] = useState<CallState>('idle');
    
    const peerConnection = useRef<RTCPeerConnection | null>(null);
    // Keep references to event handlers so we can clear them on cleanup
    const pcTrackHandlerRef = useRef<((event: any) => void) | null>(null);
    const pcIceHandlerRef = useRef<((event: any) => void) | null>(null);
    const savedDeviceId = useRef<string | null>(null);
    const isConnecting = useRef(false);
    const handleMessageRef = useRef<(topic: string, payload: string) => void>(() => {});
    const hangupRef = useRef<() => void>(() => {});

    const connect = useCallback((deviceId: string): Promise<void> => {
        savedDeviceId.current = deviceId;

        const attempt = (port: number, useSSL: boolean): Promise<Paho.Client> => {
            return new Promise((resolve, reject) => {
                const newClient = new Paho.Client('broker.hivemq.com', port, '/mqtt', `react-native-mobile-${Date.now()}`);

                newClient.onMessageArrived = (message: Paho.Message) => {
                    handleMessageRef.current(message.destinationName, message.payloadString);
                };
                newClient.onConnectionLost = (response) => {
                    if (response.errorCode !== 0) {
                        setIsConnected(false);
                        hangupRef.current();
                        const id = savedDeviceId.current;
                        if (id && !isConnecting.current) {
                            isConnecting.current = true;
                            setTimeout(() => {
                                connect(id).finally(() => { isConnecting.current = false; });
                            }, 2000);
                        }
                    }
                };

                newClient.connect({
                    onSuccess: () => resolve(newClient),
                    onFailure: (err) => reject(err),
                    useSSL,
                    timeout: 10,
                });
            });
        };

        const finish = (connectedClient: Paho.Client) => {
            setClient(connectedClient);
            setIsConnected(true);
            const topics = [
                `device/${deviceId}/info`,
                `device/${deviceId}/alert`,
                `device/${deviceId}/webrtc/offer`,
                `device/${deviceId}/webrtc/answer`,
                `device/${deviceId}/webrtc/candidate`,
            ];
            topics.forEach(topic => connectedClient.subscribe(topic));
        };

        // Try secure first, then fallback to ws if needed
        return attempt(8884, true)
            .then((c) => { finish(c); })
            .catch((err1) => {
                console.warn('[MQTT] Secure connect failed, trying ws fallback:', err1?.errorMessage || err1);
                return attempt(8000, false).then((c) => { finish(c); });
            });
    }, []);

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

    const initializePeerConnection = async () => {
        // Close any existing connection first, and remove handlers
        if (peerConnection.current) {
            try {
                (peerConnection.current as any).ontrack = null;
                (peerConnection.current as any).onicecandidate = null;
            } catch {}
            peerConnection.current.close();
        }
        const pc = new RTCPeerConnection(configuration);
        peerConnection.current = pc;
        
        const stream = await mediaDevices.getUserMedia({ audio: true, video: true });
        setLocalStream(stream);

        stream.getTracks().forEach(track => pc.addTrack(track, stream));

        const onTrack = (event: any) => {
            const streams = event?.streams;
            if (streams && streams[0]) {
                setRemoteStream(streams[0]);
                setCallState('connected');
            } else if (event?.track) {
                // Fallback: if streams not provided, assemble a MediaStream
                const remote = new MediaStream();
                remote.addTrack(event.track);
                setRemoteStream(remote);
                setCallState('connected');
            }
        };
        const onIceCandidate = (event: any) => {
            if (event?.candidate && savedDeviceId.current) {
                publish(`mobile/${savedDeviceId.current}/webrtc/candidate`, JSON.stringify(event.candidate));
            }
        };

        (pc as any).ontrack = onTrack;
        (pc as any).onicecandidate = onIceCandidate;
        pcTrackHandlerRef.current = onTrack;
        pcIceHandlerRef.current = onIceCandidate;
    };

    const handleMessage = async (topic: string, payload: string) => {
        console.log(`Received on ${topic}`);
        try {
            const data = JSON.parse(payload);
            
            if (topic.endsWith('/info')) setDeviceInfo(data);
            if (topic.endsWith('/alert')) setAlertHistory(prev => [{ ...data, timestamp: Date.now() }, ...prev].slice(0, 10));

            if (topic.endsWith('/webrtc/offer')) {
                await initializePeerConnection();
                await peerConnection.current?.setRemoteDescription(new RTCSessionDescription(data));
                setCallState('receiving');
            }
            if (topic.endsWith('/webrtc/answer') && peerConnection.current) {
                await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
            }
            if (topic.endsWith('/webrtc/candidate') && peerConnection.current) {
                await peerConnection.current.addIceCandidate(new RTCIceCandidate(data));
            }
        } catch (e) {
            console.error(`Lỗi parse JSON trên topic ${topic}:`, e);
        }
    };
    // keep latest handleMessage in a ref
    handleMessageRef.current = (t: string, p: string) => { void handleMessage(t, p); };
    
    const hangup = useCallback(() => {
        if (peerConnection.current) {
            // Remove handlers before closing to avoid leaks
            try {
                (peerConnection.current as any).ontrack = null;
                (peerConnection.current as any).onicecandidate = null;
            } catch {}
            peerConnection.current.close();
            peerConnection.current = null;
        }
        localStream?.getTracks().forEach(track => track.stop());
        remoteStream?.getTracks().forEach(track => track.stop());
        setLocalStream(null);
        setRemoteStream(null);
        setCallState('idle');
    }, [localStream, remoteStream]);
    // keep latest hangup in a ref
    hangupRef.current = () => hangup();

    const disconnect = useCallback(() => {
        hangup();
        if (client && client.isConnected()) {
            client.disconnect();
        }
        setClient(null);
        setIsConnected(false);
    }, [client, hangup]);

    const startCall = async () => {
        if (callState !== 'idle') return;
        // Ensure MQTT connected; try auto-connect using saved or stored deviceId
        if (!(client && client.isConnected())) {
            const id = savedDeviceId.current || (await AsyncStorage.getItem('deviceId'));
            if (!id) {
                console.warn('[MQTT] No deviceId, cannot start call');
                throw new Error('Missing deviceId');
            }
            savedDeviceId.current = id;
            await connect(id).catch((e) => {
                console.warn('[MQTT] Connect before call failed:', e?.message || e);
                throw e;
            });
        }

        setCallState('calling');
        await initializePeerConnection();
        if (peerConnection.current && savedDeviceId.current) {
            const offer = await peerConnection.current.createOffer();
            await peerConnection.current.setLocalDescription(offer);
            publish(`mobile/${savedDeviceId.current}/webrtc/offer`, JSON.stringify(offer));
        }
    };
    
    const answerCall = async () => {
        if (callState !== 'receiving' || !peerConnection.current || !savedDeviceId.current) return;
        const answer = await peerConnection.current.createAnswer();
        await peerConnection.current.setLocalDescription(answer);
        publish(`mobile/${savedDeviceId.current}/webrtc/answer`, JSON.stringify(answer));
    };

    const publish = (topic: string, message: string, qos: 0 | 1 | 2 = 1) => {
        if (client && client.isConnected()) {
            client.send(topic, message, qos, false);
        } else {
            console.warn(`[MQTT] Not connected. Cannot publish to ${topic}`);
        }
    };

    return (
        <MQTTContext.Provider value={{ isConnected, deviceInfo, alertHistory, localStream, remoteStream, callState, connect, disconnect, publish, startCall, answerCall, hangup }}>
            {children}
        </MQTTContext.Provider>
    );
};

export const useMQTT = (): MQTTContextType => {
    const context = useContext(MQTTContext);
    if (!context) throw new Error('useMQTT must be used within a MQTTProvider');
    return context;
};

