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

// Cấu hình STUN + TURN servers với ExpressTurn credentials
const configuration = {
  iceServers: [
    // Google STUN servers (luôn reliable)
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
    
    // ExpressTurn TURN Server (Your credentials) - UDP + TCP
    {
      urls: [
        'turn:relay1.expressturn.com:3478',
        'turn:relay1.expressturn.com:3478?transport=tcp',
        'turns:relay1.expressturn.com:5349',
      ],
      username: '000000002076506456',
      credential: 'bK8A/K+WGDw/tYcuvM9/5xCnEZs=',
    },
    
    // Twilio STUN/TURN (public free tier)
    {
      urls: [
        'turn:global.turn.twilio.com:3478?transport=udp',
        'turn:global.turn.twilio.com:3478?transport=tcp',
        'turn:global.turn.twilio.com:443?transport=tcp',
      ],
      username: 'f4b4035eaa76f4a55de5f4351567653ee4ff6fa97b50b6b334fcc1be9c27212d',
      credential: 'w1uxM55V9yVoqyVFjt+mxDBV0F87AUCemaYVQGxsPLw=',
    },
  ],
  // Cho phép thử tất cả các loại kết nối (host, srflx, relay)
  // ICE sẽ tự động chọn đường đi tốt nhất
  iceTransportPolicy: 'all' as const,
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
    const pcTrackHandlerRef = useRef<((event: any) => void) | null>(null);
    const pcIceHandlerRef = useRef<((event: any) => void) | null>(null);
    const savedDeviceId = useRef<string | null>(null);
    const isConnecting = useRef(false);
    const handleMessageRef = useRef<(topic: string, payload: string) => void>(() => {});
    const hangupRef = useRef<() => void>(() => {});
    
    // ✅ CRITICAL FIX: Buffer cho ICE candidates nhận trước remoteDescription
    const pendingIceCandidates = useRef<any[]>([]);

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
                        console.warn('[MQTT] Connection lost:', response.errorMessage);
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
                    onSuccess: () => {
                        console.log('[MQTT] Connected successfully');
                        resolve(newClient);
                    },
                    onFailure: (err) => {
                        console.warn('[MQTT] Connection failed:', err.errorMessage);
                        reject(err);
                    },
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
            topics.forEach(topic => {
                connectedClient.subscribe(topic);
                console.log(`[MQTT] Subscribed to ${topic}`);
            });
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
        console.log('[WebRTC] Initializing peer connection...');
        
        // Clear pending ICE candidates
        pendingIceCandidates.current = [];
        
        // Close any existing connection first
        if (peerConnection.current) {
            try {
                (peerConnection.current as any).ontrack = null;
                (peerConnection.current as any).onicecandidate = null;
                (peerConnection.current as any).oniceconnectionstatechange = null;
                (peerConnection.current as any).onconnectionstatechange = null;
            } catch {}
            peerConnection.current.close();
        }
        
        const pc = new RTCPeerConnection(configuration);
        peerConnection.current = pc;
        
        // Get local media
        console.log('[WebRTC] Requesting camera/microphone access...');
        const stream = await mediaDevices.getUserMedia({ 
            audio: true, 
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            }
        });
        console.log('[WebRTC] Got local stream');
        setLocalStream(stream);

        // Add tracks to peer connection
        stream.getTracks().forEach(track => {
            console.log(`[WebRTC] Adding ${track.kind} track`);
            pc.addTrack(track, stream);
        });

        // Track handler
        const onTrack = (event: any) => {
            console.log('[WebRTC] 📹 Received remote track:', event.track.kind);
            const streams = event?.streams;
            if (streams && streams[0]) {
                console.log('[WebRTC] ✅ Setting remote stream');
                setRemoteStream(streams[0]);
                setCallState('connected');
            } else if (event?.track) {
                // Fallback: if streams not provided, assemble a MediaStream
                console.log('[WebRTC] Assembling remote stream from track');
                const remote = new MediaStream();
                remote.addTrack(event.track);
                setRemoteStream(remote);
                setCallState('connected');
            }
        };
        
        // ICE candidate handler
        const onIceCandidate = (event: any) => {
            if (event?.candidate && savedDeviceId.current) {
                const cand = event.candidate;
                const candStr = cand.candidate || '';
                
                // Detect candidate type from SDP string
                let type = 'unknown';
                if (candStr.includes('typ relay')) type = 'relay';
                else if (candStr.includes('typ srflx')) type = 'srflx';
                else if (candStr.includes('typ host')) type = 'host';
                
                const emoji = type === 'relay' ? '🔄' : type === 'srflx' ? '🌐' : type === 'host' ? '🏠' : '❓';
                console.log(`[WebRTC] ${emoji} Generated ${type.toUpperCase()} candidate:`, candStr.substring(0, 80));
                
                publish(`mobile/${savedDeviceId.current}/webrtc/candidate`, JSON.stringify({
                    candidate: cand.candidate,
                    sdpMid: cand.sdpMid,
                    sdpMLineIndex: cand.sdpMLineIndex,
                }));
            } else if (!event?.candidate) {
                console.log('[WebRTC] 🏁 ICE gathering complete');
            }
        };

        // Connection state handlers
        const onIceConnectionStateChange = () => {
            const state = pc.iceConnectionState;
            console.log(`[WebRTC] 🧊 ICE connection state: ${state}`);
            if (state === 'failed') {
                console.error('[WebRTC] ❌ ICE connection failed!');
            } else if (state === 'connected' || state === 'completed') {
                console.log('[WebRTC] ✅ ICE connection established!');
            }
        };

        const onConnectionStateChange = () => {
            const state = pc.connectionState;
            console.log(`[WebRTC] 🔗 Connection state: ${state}`);
            if (state === 'failed') {
                console.error('[WebRTC] ❌ WebRTC connection failed!');
            } else if (state === 'connected') {
                console.log('[WebRTC] 🎉 WebRTC connection established!');
            }
        };

        // Attach handlers
        (pc as any).ontrack = onTrack;
        (pc as any).onicecandidate = onIceCandidate;
        (pc as any).oniceconnectionstatechange = onIceConnectionStateChange;
        (pc as any).onconnectionstatechange = onConnectionStateChange;
        
        pcTrackHandlerRef.current = onTrack;
        pcIceHandlerRef.current = onIceCandidate;
    };

    // ✅ Helper function to process pending ICE candidates
    const processPendingIceCandidates = async () => {
        if (!peerConnection.current || pendingIceCandidates.current.length === 0) {
            return;
        }

        console.log(`[WebRTC] Processing ${pendingIceCandidates.current.length} pending ICE candidates...`);
        
        const candidates = [...pendingIceCandidates.current];
        pendingIceCandidates.current = [];
        
        for (const candidateData of candidates) {
            try {
                await peerConnection.current.addIceCandidate(new RTCIceCandidate(candidateData));
                console.log('[WebRTC] ✅ Added pending ICE candidate');
            } catch (error) {
                console.error('[WebRTC] ❌ Failed to add pending ICE candidate:', error);
            }
        }
    };

    const handleMessage = async (topic: string, payload: string) => {
        console.log(`[MQTT] 📨 Received on ${topic}`);
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

            // ✅ WebRTC Offer handling
            if (topic.endsWith('/webrtc/offer')) {
                console.log('[WebRTC] 📞 Received offer from device');
                await initializePeerConnection();
                
                if (peerConnection.current) {
                    await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                    console.log('[WebRTC] ✅ Remote description set');
                    
                    // Process any pending ICE candidates
                    await processPendingIceCandidates();
                    
                    setCallState('receiving');
                }
            }
            
            // ✅ WebRTC Answer handling
            if (topic.endsWith('/webrtc/answer') && peerConnection.current) {
                console.log('[WebRTC] 📞 Received answer from device');
                await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                console.log('[WebRTC] ✅ Remote description set');
                
                // Process any pending ICE candidates
                await processPendingIceCandidates();
            }
            
            // ✅ CRITICAL FIX: ICE Candidate handling with buffering
            if (topic.endsWith('/webrtc/candidate')) {
                if (!peerConnection.current) {
                    console.warn('[WebRTC] ⚠️ ICE candidate received but no peer connection');
                    return;
                }

                // Check if remote description is set
                if (!peerConnection.current.remoteDescription) {
                    console.warn('[WebRTC] ⏳ Buffering ICE candidate (waiting for remote description)');
                    pendingIceCandidates.current.push(data);
                    return;
                }

                // Remote description is set, add candidate immediately
                try {
                    await peerConnection.current.addIceCandidate(new RTCIceCandidate(data));
                    console.log('[WebRTC] ✅ ICE candidate added');
                } catch (error) {
                    console.error('[WebRTC] ❌ Failed to add ICE candidate:', error);
                }
            }
        } catch (e) {
            console.error(`[MQTT] ❌ Error parsing message on ${topic}:`, e);
        }
    };
    
    // Keep latest handleMessage in a ref
    handleMessageRef.current = (t: string, p: string) => { void handleMessage(t, p); };
    
    const hangup = useCallback(() => {
        console.log('[WebRTC] 📴 Hanging up...');
        
        // Clear pending candidates
        pendingIceCandidates.current = [];
        
        if (peerConnection.current) {
            // Remove handlers before closing to avoid leaks
            try {
                (peerConnection.current as any).ontrack = null;
                (peerConnection.current as any).onicecandidate = null;
                (peerConnection.current as any).oniceconnectionstatechange = null;
                (peerConnection.current as any).onconnectionstatechange = null;
            } catch {}
            peerConnection.current.close();
            peerConnection.current = null;
        }
        
        localStream?.getTracks().forEach(track => {
            track.stop();
            console.log(`[WebRTC] Stopped ${track.kind} track`);
        });
        remoteStream?.getTracks().forEach(track => track.stop());
        
        setLocalStream(null);
        setRemoteStream(null);
        setCallState('idle');
        console.log('[WebRTC] ✅ Hangup complete');
    }, [localStream, remoteStream]);
    
    // Keep latest hangup in a ref
    hangupRef.current = () => hangup();

    const disconnect = useCallback(() => {
        console.log('[MQTT] Disconnecting...');
        hangup();
        if (client && client.isConnected()) {
            client.disconnect();
        }
        setClient(null);
        setIsConnected(false);
    }, [client, hangup]);

    const startCall = async () => {
        if (callState !== 'idle') {
            console.warn('[WebRTC] Cannot start call, state:', callState);
            return;
        }
        
        console.log('[WebRTC] 📞 Starting call...');
        
        // Ensure MQTT connected
        if (!(client && client.isConnected())) {
            const id = savedDeviceId.current || (await AsyncStorage.getItem('deviceId'));
            if (!id) {
                console.error('[WebRTC] ❌ No deviceId, cannot start call');
                throw new Error('Missing deviceId');
            }
            savedDeviceId.current = id;
            console.log('[MQTT] Connecting to device:', id);
            await connect(id);
        }

        setCallState('calling');
        await initializePeerConnection();
        
        if (peerConnection.current && savedDeviceId.current) {
            const offer = await peerConnection.current.createOffer();
            await peerConnection.current.setLocalDescription(offer);
            console.log('[WebRTC] 📤 Sending offer to device');
            publish(`mobile/${savedDeviceId.current}/webrtc/offer`, JSON.stringify(offer));
        }
    };
    
    const answerCall = async () => {
        if (callState !== 'receiving' || !peerConnection.current || !savedDeviceId.current) {
            console.warn('[WebRTC] Cannot answer call, state:', callState);
            return;
        }
        
        console.log('[WebRTC] 📞 Answering call...');
        const answer = await peerConnection.current.createAnswer();
        await peerConnection.current.setLocalDescription(answer);
        console.log('[WebRTC] 📤 Sending answer to device');
        publish(`mobile/${savedDeviceId.current}/webrtc/answer`, JSON.stringify(answer));
    };

    const publish = (topic: string, message: string, qos: 0 | 1 | 2 = 1) => {
        if (client && client.isConnected()) {
            client.send(topic, message, qos, false);
            console.log(`[MQTT] 📤 Published to ${topic}`);
        } else {
            console.warn(`[MQTT] ⚠️ Not connected. Cannot publish to ${topic}`);
        }
    };

    return (
        <MQTTContext.Provider value={{ 
            isConnected, 
            deviceInfo, 
            alertHistory, 
            localStream, 
            remoteStream, 
            callState, 
            connect, 
            disconnect, 
            publish, 
            startCall, 
            answerCall, 
            hangup 
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