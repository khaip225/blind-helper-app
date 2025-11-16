import AsyncStorage from '@react-native-async-storage/async-storage';
import { Buffer } from 'buffer';
import Paho from 'paho-mqtt';
import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { mediaDevices, MediaStream, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';

// Import InCallManager for speaker control
let InCallManager: any = null;
try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const incallModule = require('react-native-incall-manager');
    InCallManager = incallModule?.default || incallModule;
    console.log('[Audio] InCallManager loaded:', typeof InCallManager, InCallManager);
} catch (err) {
    console.warn('[Audio] react-native-incall-manager not installed:', err);
}

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

// 🔥 Chỉ dùng Metered.ca STUN/TURN - KHÔNG dùng Google STUN
// Cấu hình giống y hệt code mẫu của Metered.ca
const configuration = {
  iceServers: [
    {
      urls: 'stun:stun.relay.metered.ca:80',
    },
    {
      urls: 'turn:sg.relay.metered.ca:80',
      username: '93e17668232018bed69fae39',
      credential: '/NDIlk/I1eVxIjo2',
    },
    {
      urls: 'turn:sg.relay.metered.ca:80?transport=tcp',
      username: '93e17668232018bed69fae39',
      credential: '/NDIlk/I1eVxIjo2',
    },
    {
      urls: 'turn:sg.relay.metered.ca:443',
      username: '93e17668232018bed69fae39',
      credential: '/NDIlk/I1eVxIjo2',
    },
    {
      urls: 'turns:sg.relay.metered.ca:443?transport=tcp',
      username: '93e17668232018bed69fae39',
      credential: '/NDIlk/I1eVxIjo2',
    },
  ],
  // 🔥 'all' allows HOST/SRFLX/RELAY - will try direct connection first, then relay
  iceTransportPolicy: 'all' as const,
  iceCandidatePoolSize: 10,
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
    // Track last published answer SDP to avoid duplicate publishes
    const lastPublishedAnswerSdp = useRef<string | null>(null);
    // Auto-answer đã bị gỡ bỏ để đơn giản hóa luồng: chỉ trả lời khi người dùng bấm nút

    const connect = useCallback((deviceId: string): Promise<void> => {
        console.log('[MQTT] ▶️ connect() called with deviceId=', deviceId);
        savedDeviceId.current = deviceId;

        const attempt = (port: number, useSSL: boolean): Promise<Paho.Client> => {
            return new Promise((resolve, reject) => {
                // 🔥 Connect to custom MQTT broker: mqtt.phuocnguyn.id.vn
                const newClient = new Paho.Client('mqtt.phuocnguyn.id.vn', port, '/', `mobile001`);

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
                        console.log('[MQTT] Connected successfully to mqtt.phuocnguyn.id.vn');
                        resolve(newClient);
                    },
                    onFailure: (err) => {
                        console.warn('[MQTT] Connection failed:', err.errorMessage);
                        reject(err);
                    },
                    useSSL,
                    // Request a persistent session so broker keeps subscriptions/messages across reconnects
                    cleanSession: false,
                    userName: 'mobile001',      // 🔥 MQTT authentication
                    password: '123456',          // 🔥 MQTT authentication
                    timeout: 10,
                });
            });
        };

        const finish = (connectedClient: Paho.Client) => {
            setClient(connectedClient);
            setIsConnected(true);
            // App should SUBSCRIBE to what Device PUBLISHes: `mobile/{deviceId}/*`
            const topics = [
                `mobile/${deviceId}/info`,
                `mobile/${deviceId}/alert`,
                `mobile/${deviceId}/webrtc/offer`,
                `mobile/${deviceId}/webrtc/answer`,
                `mobile/${deviceId}/webrtc/candidate`,
                `device/${deviceId}/gps`,
            ];
            topics.forEach(topic => {
                // 🔥 Match device QoS: offer/answer = QoS 1, candidate = QoS 0
                const qos = topic.includes('/webrtc/offer') || topic.includes('/webrtc/answer') || topic.includes('/gps') ? 1 : 0;
                connectedClient.subscribe(topic, { qos });
                console.log(`[MQTT] Subscribed to ${topic} (QoS=${qos})`);
            });
        };

        // Try secure websocket (port 443 with TLS)
        return attempt(443, true)
            .then((c) => { finish(c); })
            .catch((err1) => {
                console.warn('[MQTT] Secure websocket (443) failed, trying fallback 8000:', err1?.errorMessage || err1);
                // Fallback to non-secure port 8000 if TLS fails
                return attempt(8000, false).then((c) => { finish(c); });
            });
    }, []);

    // Auto-connect on mount if a deviceId was saved previously
    React.useEffect(() => {
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

    const initializePeerConnection = async () => {
        console.log('[WebRTC] Initializing peer connection...');
        
    // Clear pending ICE candidates and reset answer flag
        pendingIceCandidates.current = [];
        try { answeredRef.current = false; } catch {}
        lastPublishedAnswerSdp.current = null;
    // Không dùng autoAnswerRequested nữa
        
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
            try {
                console.log('[WebRTC] 📹 Received remote track:', event.track?.kind, 'id=', event.track?.id);
                const streams = event?.streams;
                let remote: MediaStream | null = null;
                if (streams && streams[0]) {
                    remote = streams[0];
                    console.log('[WebRTC] ✅ Using remote stream from event.streams[0], id=', (remote as any)?.id);
                } else if (event?.track) {
                    // Fallback: assemble a MediaStream from single track
                    console.log('[WebRTC] 🧩 Assembling remote stream from single track');
                    remote = new MediaStream();
                    remote.addTrack(event.track);
                }
                if (remote) {
                    // Ensure tracks are enabled
                    try {
                        const vTracks = remote.getVideoTracks?.() || [];
                        const aTracks = remote.getAudioTracks?.() || [];
                        vTracks.forEach((t) => {
                            if ((t as any).enabled === false) (t as any).enabled = true;
                            console.log('[WebRTC] 🎞️ Remote video track:', t.id, 'enabled=', (t as any).enabled);
                        });
                        aTracks.forEach((t) => {
                            if ((t as any).enabled === false) (t as any).enabled = true;
                            console.log('[WebRTC] 🔈 Remote audio track:', t.id, 'enabled=', (t as any).enabled);
                        });
                        console.log('[WebRTC] 📦 Remote stream tracks -> video:', vTracks.length, 'audio:', aTracks.length);
                    } catch (e) {
                        console.log('[WebRTC] (log tracks) error:', e);
                    }
                    setRemoteStream(remote);
                    // Tentatively mark connected here; ICE handler will also confirm
                    setCallState('connected');
                    
                    // 🔊 Enable speakerphone when remote stream is received
                    console.log('[Audio] 🔍 InCallManager type:', typeof InCallManager);
                    console.log('[Audio] 🔍 InCallManager.start type:', typeof InCallManager?.start);
                    
                    if (InCallManager && typeof InCallManager.start === 'function') {
                        try {
                            console.log('[Audio] 🔊 Attempting to enable speakerphone...');
                            InCallManager.start({ media: 'video', ringback: '' });
                            InCallManager.setForceSpeakerphoneOn(true);
                            InCallManager.setSpeakerphoneOn(true);
                            console.log('[Audio] ✅ Speakerphone enabled');
                        } catch (err) {
                            console.error('[Audio] ❌ Failed to enable speakerphone:', err);
                        }
                    } else {
                        console.warn('[Audio] ⚠️ InCallManager not properly linked - try rebuild: npx expo prebuild --clean && npx expo run:android');
                    }
                }
            } catch (err) {
                console.warn('[WebRTC] ontrack handler error:', err);
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
                
                // ✅ CRITICAL: Log để debug TURN - phải thấy RELAY candidates!
                if (type === 'relay') {
                    console.log('[WebRTC] ✅ TURN is working! RELAY candidate generated.');
                } else if (type === 'host') {
                    console.log('[WebRTC] 🏠 Local candidate (may not work across networks)');
                }
                
                // 🔥 FIX: Thêm type field để device parser nhận dạng đúng
                const payload = {
                    type: 'candidate',  // ← Thêm field này!
                    candidate: cand.candidate,
                    sdpMid: cand.sdpMid,
                    sdpMLineIndex: cand.sdpMLineIndex,
                };
                console.log(`[WebRTC] 📤 Publishing ${type} candidate payload:`, JSON.stringify(payload).substring(0, 150));
                // ✅ ĐÚNG: publish tới topic mà device đang subscribe
                publish(`device/${savedDeviceId.current}/webrtc/candidate`, JSON.stringify(payload));
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
                // Ensure UI reflects connected state once ICE is established
                setCallState((prev) => (prev !== 'connected' ? 'connected' : prev));
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
            
            if (topic.endsWith('/gps')) {
                // Detailed logging to help debug GPS messages from device
                console.log('[MQTT] 📍 Device info updated');
                console.log('[MQTT] 📍 Raw payload string:', payload);
                try {
                    console.log('[MQTT] 📍 Parsed GPS object:', data);
                    // Detect common shapes and log helpful hints
                    if (data && data.gps) {
                        console.log('[MQTT] 📍 Detected nested `gps` object ->', data.gps);
                    } else if (data && (data.lat !== undefined || data.latitude !== undefined)) {
                        console.log('[MQTT] 📍 Detected top-level lat/long ->', { lat: data.lat ?? data.latitude, long: data.long ?? data.longitude });
                    }
                } catch (e) {
                    console.warn('[MQTT] 📍 Failed to inspect GPS payload:', e);
                }
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
                    console.log('[WebRTC] 🔍 signalingState before setRemoteDescription:', peerConnection.current.signalingState);
                    await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                    console.log('[WebRTC] ✅ Remote description set, signalingState=', peerConnection.current.signalingState);
                    
                    // Process any pending ICE candidates
                    await processPendingIceCandidates();
                    
                    // Đặt trạng thái đang nhận – chờ người dùng bấm "Trả lời"
                    setCallState('receiving');
                }
            }
            
            // ✅ WebRTC Answer handling
            if (topic.endsWith('/webrtc/answer') && peerConnection.current) {
                console.log('[WebRTC] 📞 Received answer from device');
                console.log('[WebRTC] 🔍 Current signalingState:', peerConnection.current.signalingState);
                
                // Only set if we're waiting for an answer (we sent an offer)
                if (peerConnection.current.signalingState === 'have-local-offer') {
                    try {
                        await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                        console.log('[WebRTC] ✅ Remote answer set, signalingState=', peerConnection.current.signalingState);
                        
                        // Process any pending ICE candidates
                        await processPendingIceCandidates();
                    } catch (error) {
                        console.error('[WebRTC] ❌ Failed to set remote answer:', error);
                    }
                } else {
                    console.warn('[WebRTC] ⚠️ Ignoring answer, wrong signalingState:', peerConnection.current.signalingState);
                }
            }
            
            // ✅ CRITICAL FIX: ICE Candidate handling with buffering
            if (topic.endsWith('/webrtc/candidate')) {
                if (!peerConnection.current) {
                    console.warn('[WebRTC] ⚠️ ICE candidate received but no peer connection');
                    return;
                }

                // 🔍 DEBUG: Log candidate type để debug RELAY
                const candStr = data.candidate || '';
                let type = 'unknown';
                if (candStr.includes('typ relay')) type = 'RELAY';
                else if (candStr.includes('typ srflx')) type = 'SRFLX';
                else if (candStr.includes('typ host')) type = 'HOST';
                console.log(`[WebRTC] 📥 Received ${type} candidate from device:`, candStr.substring(0, 80));

                // Check if remote description is set
                if (!peerConnection.current.remoteDescription) {
                    console.warn('[WebRTC] ⏳ Buffering ICE candidate (waiting for remote description)');
                    pendingIceCandidates.current.push(data);
                    return;
                }

                // Remote description is set, add candidate immediately
                try {
                    await peerConnection.current.addIceCandidate(new RTCIceCandidate(data));
                    console.log(`[WebRTC] ✅ ${type} candidate added successfully`);
                } catch (error) {
                    console.error(`[WebRTC] ❌ Failed to add ${type} candidate:`, error);
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
        
        // 🔊 Disable speakerphone
        if (InCallManager) {
            try {
                InCallManager.setForceSpeakerphoneOn(false);
                InCallManager.stop();
                console.log('[Audio] 🔇 Speakerphone disabled');
            } catch (err) {
                console.warn('[Audio] Failed to disable speakerphone:', err);
            }
        }
        
        // Clear pending candidates
        pendingIceCandidates.current = [];
        answeredRef.current = false;
        lastPublishedAnswerSdp.current = null;
        
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
            console.log('[WebRTC] 🔍 signalingState after setLocalDescription:', peerConnection.current.signalingState);
            // ✅ ĐÚNG: publish tới topic mà device đang subscribe
            publish(`mobile/${savedDeviceId.current}/webrtc/offer`, JSON.stringify(offer));
        }
    };
    
    // Prevent duplicate/invalid answer creation
    const answeredRef = useRef(false);

    const answerCall = async () => {
        if (!peerConnection.current) {
            console.warn('[WebRTC] Cannot answer: no peerConnection');
            return;
        }
        const pc = peerConnection.current;

        // Valid only if we have a remote offer
        if (!pc.remoteDescription) {
            console.warn('[WebRTC] Cannot answer: chưa có remoteDescription (offer). signalingState=', pc.signalingState);
            return;
        }
        if (pc.signalingState === 'have-remote-offer') {
            // proceed
        } else if (pc.signalingState === 'stable') {
            // Already negotiated. Do not re-publish to avoid duplicates.
            console.log('[WebRTC] Answer already created or signalingState stable - skipping');
            return;
        } else {
            console.warn('[WebRTC] Cannot answer in signalingState=', pc.signalingState);
            return;
        }
        if (answeredRef.current) {
            console.log('[WebRTC] Answer already created - skipping');
            return;
        }
        // Chỉ cho phép trả lời khi đang ở trạng thái nhận cuộc gọi
        if (callState !== 'receiving') {
            console.warn('[WebRTC] Cannot answer, callState=', callState);
            return;
        }
        if (!savedDeviceId.current) {
            console.warn('[WebRTC] Cannot answer: missing deviceId');
            return;
        }

        try {
            console.log('[WebRTC] 📞 Creating answer...');
            console.log('[WebRTC] 🔍 signalingState before createAnswer:', pc.signalingState);
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            console.log('[WebRTC] 🔍 signalingState after setLocalDescription:', pc.signalingState);
            answeredRef.current = true;
            // Sau khi tạo answer, chuyển sang trạng thái 'calling' để ẩn nút Trả lời và tránh spam
            setCallState('calling');
            // Only publish if not already published same SDP
                if (lastPublishedAnswerSdp.current !== answer.sdp) {
                lastPublishedAnswerSdp.current = answer.sdp;
                console.log('[WebRTC] 📤 Sending answer to device');
                // ✅ ĐÚNG: publish tới topic mà device đang subscribe
                publish(`device/${savedDeviceId.current}/webrtc/answer`, JSON.stringify(answer));
            } else {
                console.log('[WebRTC] ⚠️ Skipping duplicate answer publish (same SDP)');
            }
        } catch (err) {
            console.error('[WebRTC] ❌ Failed to create/send answer:', err);
        }
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