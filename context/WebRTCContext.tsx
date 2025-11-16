import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { mediaDevices, MediaStream, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';
import { useMQTT } from './MQTTContext';

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

type CallState = 'idle' | 'calling' | 'receiving' | 'connected';

// --- Định nghĩa kiểu dữ liệu cho Context ---
interface WebRTCContextType {
    localStream: MediaStream | null;
    remoteStream: MediaStream | null;
    callState: CallState;
    
    startCall: () => Promise<void>;
    answerCall: () => Promise<void>;
    hangup: () => void;
}

const WebRTCContext = createContext<WebRTCContextType | null>(null);

export const WebRTCProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { isConnected, publish, subscribe } = useMQTT();
    
    // --- WebRTC States ---
    const [localStream, setLocalStream] = useState<MediaStream | null>(null);
    const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
    const [callState, setCallState] = useState<CallState>('idle');
    
    const peerConnection = useRef<RTCPeerConnection | null>(null);
    const savedDeviceId = useRef<string | null>(null);
    
    // ✅ CRITICAL FIX: Buffer cho ICE candidates nhận trước remoteDescription
    const pendingIceCandidates = useRef<any[]>([]);

    // Lấy deviceId từ AsyncStorage khi mount
    useEffect(() => {
        const getDeviceId = async () => {
            try {
                const id = await AsyncStorage.getItem('deviceId');
                if (id) {
                    savedDeviceId.current = id;
                }
            } catch (error) {
                console.warn('[WebRTC] Failed to read deviceId from storage');
            }
        };
        getDeviceId();
    }, []);

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

    // Subscribe to WebRTC topics khi MQTT connected
    useEffect(() => {
        if (!isConnected || !savedDeviceId.current) return;

        const deviceId = savedDeviceId.current;
        
        // Subscribe to WebRTC offer topic
        subscribe(`device/${deviceId}/webrtc/offer`, async (topic: string, payload: string) => {
            console.log('[WebRTC] 📞 Received offer from device');
            await initializePeerConnection();
            
            if (peerConnection.current) {
                try {
                    const data = JSON.parse(payload);
                    await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                    console.log('[WebRTC] ✅ Remote description set');
                    
                    // Process any pending ICE candidates
                    await processPendingIceCandidates();
                    
                    setCallState('receiving');
                } catch (error) {
                    console.error('[WebRTC] ❌ Error handling offer:', error);
                }
            }
        });

        // Subscribe to WebRTC answer topic
        subscribe(`device/${deviceId}/webrtc/answer`, async (topic: string, payload: string) => {
            if (!peerConnection.current) return;
            
            console.log('[WebRTC] 📞 Received answer from device');
            try {
                const data = JSON.parse(payload);
                await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                console.log('[WebRTC] ✅ Remote description set');
                
                // Process any pending ICE candidates
                await processPendingIceCandidates();
            } catch (error) {
                console.error('[WebRTC] ❌ Error handling answer:', error);
            }
        });

        // Subscribe to WebRTC candidate topic
        subscribe(`device/${deviceId}/webrtc/candidate`, async (topic: string, payload: string) => {
            if (!peerConnection.current) {
                console.warn('[WebRTC] ⚠️ ICE candidate received but no peer connection');
                return;
            }

            try {
                const data = JSON.parse(payload);
                
                // Check if remote description is set
                if (!peerConnection.current.remoteDescription) {
                    console.warn('[WebRTC] ⏳ Buffering ICE candidate (waiting for remote description)');
                    pendingIceCandidates.current.push(data);
                    return;
                }

                // Remote description is set, add candidate immediately
                await peerConnection.current.addIceCandidate(new RTCIceCandidate(data));
                console.log('[WebRTC] ✅ ICE candidate added');
            } catch (error) {
                console.error('[WebRTC] ❌ Failed to add ICE candidate:', error);
            }
        });
    }, [isConnected, subscribe]);

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

    const startCall = async () => {
        if (callState !== 'idle') {
            console.warn('[WebRTC] Cannot start call, state:', callState);
            return;
        }
        
        console.log('[WebRTC] 📞 Starting call...');
        
        // Ensure MQTT connected
        if (!isConnected) {
            const id = savedDeviceId.current || (await AsyncStorage.getItem('deviceId'));
            if (!id) {
                console.error('[WebRTC] ❌ No deviceId, cannot start call');
                throw new Error('Missing deviceId');
            }
            savedDeviceId.current = id;
            console.log('[WebRTC] ⚠️ MQTT not connected, cannot start call');
            throw new Error('MQTT not connected');
        }

        if (!savedDeviceId.current) {
            const id = await AsyncStorage.getItem('deviceId');
            if (!id) {
                throw new Error('Missing deviceId');
            }
            savedDeviceId.current = id;
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

    return (
        <WebRTCContext.Provider value={{ 
            localStream, 
            remoteStream, 
            callState, 
            startCall, 
            answerCall, 
            hangup 
        }}>
            {children}
        </WebRTCContext.Provider>
    );
};

export const useWebRTC = (): WebRTCContextType => {
    const context = useContext(WebRTCContext);
    if (!context) throw new Error('useWebRTC must be used within a WebRTCProvider');
    return context;
};

