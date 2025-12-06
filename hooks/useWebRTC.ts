import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useRef, useState } from 'react';
import { mediaDevices, MediaStream, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription } from 'react-native-webrtc';
import { getConfiguration } from '../config/webrtc.config';
import type { CallState, UseWebRTCProps, UseWebRTCReturn } from '../types/mqtt.types';
import { startRingtone, stopRingtone } from '../utils/audioManager';

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

export const useWebRTC = ({ mobileId, deviceId, publish, connect }: UseWebRTCProps): UseWebRTCReturn => {
    // --- WebRTC States ---
    const [localStream, setLocalStream] = useState<MediaStream | null>(null);
    const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
    const [callState, setCallState] = useState<CallState>('idle');

    // --- Refs ---
    const peerConnection = useRef<RTCPeerConnection | null>(null);
    const pcTrackHandlerRef = useRef<((event: any) => void) | null>(null);
    const pcIceHandlerRef = useRef<((event: any) => void) | null>(null);
    const pendingIceCandidates = useRef<any[]>([]);
    const lastPublishedAnswerSdp = useRef<string | null>(null);
    const answeredRef = useRef(false);
    const isInitializingRef = useRef(false);
    const lastRingtoneTsRef = useRef<number>(0);

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

    const initializePeerConnection = async () => {
        console.log('[WebRTC] Initializing peer connection...');
        
        // Clear pending ICE candidates and reset answer flag
        pendingIceCandidates.current = [];
        try { answeredRef.current = false; } catch {}
        lastPublishedAnswerSdp.current = null;
        
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
        
        // Fetch TURN credentials and create peer connection
        console.log('[WebRTC] Fetching TURN credentials...');
        const configuration = await getConfiguration();
        console.log('[WebRTC] Creating peer connection with', configuration.iceServers.length, 'ICE servers');
        const pc = new RTCPeerConnection(configuration);
        peerConnection.current = pc;
        
        // Get local media
        console.log('[WebRTC] Requesting camera/microphone access...');
        const stream = await mediaDevices.getUserMedia({ 
            audio: {
                echoCancellation: true,        // ✅ Quan trọng: Loại bỏ echo
                noiseSuppression: true,        // ✅ Giảm noise nền
                autoGainControl: false,        // ❌ TẮT auto gain để tự control volume
                sampleRate: 48000,
                channelCount: 1,               // Mono
                volume: 0.3,                   // ✅ Giảm volume xuống 30% để tránh clip/distort
            } as any,
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            }
        });
        console.log('[WebRTC] Got local stream with audio + video');
        
        // ✅ Giảm gain của audio track để tránh clipping/distortion
        stream.getAudioTracks().forEach(track => {
            try {
                const audioTrack = track as any;
                // Apply constraints to reduce volume
                if (audioTrack.applyConstraints) {
                    audioTrack.applyConstraints({
                        volume: 0.3,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: false,
                    }).catch((err: any) => console.warn('[WebRTC] Could not apply audio constraints:', err));
                }
                console.log('[WebRTC] 🎤 Audio track volume reduced to 30%');
            } catch (err) {
                console.warn('[WebRTC] Error adjusting audio track:', err);
            }
        });
        
        setLocalStream(stream);

        // Add tracks to peer connection
        stream.getTracks().forEach(track => {
            console.log(`[WebRTC] Adding ${track.kind} track (enabled=${track.enabled})`);
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
                    
                    // 🔊 Initialize InCallManager (but don't force speaker - let call.tsx handle it)
                    console.log('[Audio] 🔍 InCallManager type:', typeof InCallManager);
                    
                    if (InCallManager && typeof InCallManager.start === 'function') {
                        try {
                            console.log('[Audio] 📞 Starting InCallManager session...');
                            InCallManager.start({ media: 'video', ringback: '' });
                            console.log('[Audio] ✅ InCallManager session started (speaker control delegated to UI)');
                        } catch (err) {
                            console.error('[Audio] ❌ Failed to start InCallManager:', err);
                        }
                    } else {
                        console.warn('[Audio] ⚠️ InCallManager not available');
                    }
                }
            } catch (err) {
                console.warn('[WebRTC] ontrack handler error:', err);
            }
        };
        
        // ICE candidate handler
        const onIceCandidate = (event: any) => {
            if (event?.candidate && deviceId) {
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
                // ✅ CRITICAL FIX: Mobile publishes using its OWN mobileId, NOT deviceId!
                // Mobile publishes local ICE candidates to `mobile/<mobileId>/webrtc/candidate`
                // Device subscribes to `mobile/+/webrtc/candidate` to receive from any mobile
                publish(`mobile/${mobileId}/webrtc/candidate`, JSON.stringify(payload));
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
                // Attempt a one-time ICE restart to recover without tearing down
                try {
                    if (typeof (pc as any).restartIce === 'function') {
                        console.log('[WebRTC] 🔁 Attempting ICE restart...');
                        (pc as any).restartIce();
                        // Re-publish last answer SDP to re-sync signaling after restart
                        if (lastPublishedAnswerSdp.current) {
                            console.log('[WebRTC] 📤 Re-publishing last answer SDP after ICE restart');
                            publish(`mobile/${mobileId}/webrtc/answer`, JSON.stringify({ sdp: lastPublishedAnswerSdp.current, type: 'answer' }));
                        }
                        return;
                    }
                } catch (e) {
                    console.warn('[WebRTC] ICE restart unsupported or failed:', e);
                }
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

    const startCall = async () => {
        if (callState !== 'idle') {
            console.warn('[WebRTC] Cannot start call, state:', callState);
            return;
        }
        
        console.log('[WebRTC] 📞 Starting call...');
        
        // Ensure MQTT connected
        if (connect) {
            const id = deviceId || (await AsyncStorage.getItem('deviceId'));
            if (!id) {
                console.error('[WebRTC] ❌ No deviceId, cannot start call');
                throw new Error('Missing deviceId');
            }
            console.log('[MQTT] Ensuring connection to device:', id);
            await connect(id);
        }

        setCallState('calling');
        await initializePeerConnection();
        
        if (peerConnection.current && deviceId) {
            const offer = await peerConnection.current.createOffer();
            await peerConnection.current.setLocalDescription(offer);
            console.log('[WebRTC] 📤 Sending offer to device');
            console.log('[WebRTC] 🔍 signalingState after setLocalDescription:', peerConnection.current.signalingState);
            // ✅ CRITICAL FIX: Mobile publishes using its OWN mobileId!
            publish(`mobile/${mobileId}/webrtc/offer`, JSON.stringify(offer));
        }
    };

    const answerCall = async () => {
        // 🔕 Stop ringtone IMMEDIATELY when answerCall is invoked
        console.log('[WebRTC] 🔕 Stopping ringtone...');
        stopRingtone();
        
        if (!peerConnection.current) {
            console.warn('[WebRTC] Cannot answer: no peerConnection');
            return;
        }
        const pc = peerConnection.current;

        // Valid only if we have a remote offer
        if (!pc.remoteDescription) {
            // In background, offer may arrive slightly after notification tap.
            // Wait briefly for remoteDescription to be set.
            console.warn('[WebRTC] No remoteDescription yet. Waiting up to 1500ms...');
            const start = Date.now();
            while (!pc.remoteDescription && Date.now() - start < 1500) {
                await new Promise(res => setTimeout(res, 100));
            }
            if (!pc.remoteDescription) {
                console.warn('[WebRTC] Cannot answer: still no remoteDescription. signalingState=', pc.signalingState);
                return;
            }
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
        
        // ✅ REMOVED callState check - it may be reset when app is in background
        // Instead, rely on signalingState which is maintained by native WebRTC
        console.log('[WebRTC] 🔍 Current callState:', callState, 'signalingState:', pc.signalingState);
        
        // Ensure deviceId is available (fetch from storage if missing)
        let currentDeviceId = deviceId;
        if (!currentDeviceId) {
            try {
                console.log('[WebRTC] deviceId missing, fetching from AsyncStorage...');
                currentDeviceId = await (await import('@react-native-async-storage/async-storage')).default.getItem('deviceId');
                console.log('[WebRTC] Fetched deviceId from storage:', currentDeviceId);
            } catch (e) {
                console.warn('[WebRTC] Failed to fetch deviceId from storage:', e);
            }
        }
        if (!currentDeviceId) {
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
            // Mark connected once local answer is set; avoid UI loops
            setCallState('connected');

            // Ensure MQTT is connected before publishing answer/candidates
            if (connect) {
                try {
                    const idToConnect = currentDeviceId || (await AsyncStorage.getItem('deviceId'));
                    if (idToConnect) {
                        console.log('[MQTT] Ensuring connection before publishing answer...');
                        await connect(idToConnect);
                        // Small wait to allow broker subscription/connection to settle
                        await new Promise((r) => setTimeout(r, 500));
                    }
                } catch (e) {
                    console.warn('[MQTT] Failed to ensure connection before publish:', e);
                }
            }
            // Only publish if not already published same SDP
            if (lastPublishedAnswerSdp.current !== answer.sdp) {
                lastPublishedAnswerSdp.current = answer.sdp;
                console.log('[WebRTC] 📤 Sending answer to device');
                // ✅ CRITICAL FIX: Mobile publishes using its OWN mobileId!
                // Device subscribes to `mobile/+/webrtc/answer` to receive from any mobile
                // Add a short delay in case connection just established
                await new Promise((r) => setTimeout(r, 300));
                publish(`mobile/${mobileId}/webrtc/answer`, JSON.stringify(answer));
            } else {
                console.log('[WebRTC] ⚠️ Skipping duplicate answer publish (same SDP)');
            }
        } catch (err) {
            console.error('[WebRTC] ❌ Failed to create/send answer:', err);
        }
    };

    const hangup = useCallback(() => {
        console.log('[WebRTC] 📴 Hanging up...');
        
        // 🔕 Stop ringtone if still playing
        try {
            stopRingtone();
        } catch (err) {
            console.warn('[Audio] Failed to stop ringtone:', err);
        }
        
        // 🔊 Disable speakerphone and stop call manager
        if (InCallManager) {
            try {
                InCallManager.setForceSpeakerphoneOn(false);
                InCallManager.stop();
                console.log('[Audio] 🔇 Speakerphone disabled and call manager stopped');
            } catch (err) {
                console.warn('[Audio] Failed to disable speakerphone:', err);
            }
        }
        
        // ✅ Stop and release local media tracks FIRST (before closing peer connection)
        if (localStream) {
            try {
                localStream.getTracks().forEach(track => {
                    track.stop();
                    console.log(`[WebRTC] 🛑 Stopped local ${track.kind} track`);
                });
                localStream.release();
                console.log('[WebRTC] ✅ Local stream released');
            } catch (err) {
                console.warn('[WebRTC] Error stopping local stream:', err);
            }
        }
        
        // ✅ Stop remote media tracks
        if (remoteStream) {
            try {
                remoteStream.getTracks().forEach(track => {
                    track.stop();
                    console.log(`[WebRTC] 🛑 Stopped remote ${track.kind} track`);
                });
                remoteStream.release();
                console.log('[WebRTC] ✅ Remote stream released');
            } catch (err) {
                console.warn('[WebRTC] Error stopping remote stream:', err);
            }
        }
        
        // ✅ Close peer connection and remove all handlers
        if (peerConnection.current) {
            try {
                // Remove event handlers to prevent memory leaks
                (peerConnection.current as any).ontrack = null;
                (peerConnection.current as any).onicecandidate = null;
                (peerConnection.current as any).oniceconnectionstatechange = null;
                (peerConnection.current as any).onconnectionstatechange = null;
                (peerConnection.current as any).onsignalingstatechange = null;
                (peerConnection.current as any).onicegatheringstatechange = null;
                
                // Close the peer connection
                peerConnection.current.close();
                console.log('[WebRTC] 🔒 Peer connection closed');
                peerConnection.current = null;
            } catch (err) {
                console.warn('[WebRTC] Error closing peer connection:', err);
                peerConnection.current = null;
            }
        }
        
        // ✅ Clear all pending candidates and refs
        pendingIceCandidates.current = [];
        answeredRef.current = false;
        lastPublishedAnswerSdp.current = null;
        pcTrackHandlerRef.current = null;
        pcIceHandlerRef.current = null;
        
        // ✅ Reset all states
        setLocalStream(null);
        setRemoteStream(null);
        setCallState('idle');
        
        console.log('[WebRTC] ✅ Hangup complete - all resources released');
    }, [localStream, remoteStream]);

    const handleOffer = async (data: any) => {
        console.log('[WebRTC] 📞 Offer received from device');
        // Prevent re-initializing PC concurrently or for duplicate offers
        if (isInitializingRef.current) {
            console.warn('[WebRTC] Offer ignored: initialization in progress');
            return;
        }
        // If we already have a remote description, treat this as a duplicate and ignore
        if (peerConnection.current && peerConnection.current.remoteDescription) {
            console.warn('[WebRTC] Offer ignored: remoteDescription already set');
            return;
        }
        isInitializingRef.current = true;
        await initializePeerConnection();
        isInitializingRef.current = false;
        if (peerConnection.current) {
            try {
                await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                await processPendingIceCandidates();
                setCallState('receiving');

                // 🔔 Start ringtone only if not already answered and throttle repeats
                const now = Date.now();
                const since = now - (lastRingtoneTsRef.current || 0);
                const shouldRing = !answeredRef.current && since > 3000; // throttle 3s
                if (shouldRing) {
                    lastRingtoneTsRef.current = now;
                    console.log('[WebRTC] 🔔 Starting ringtone for incoming SOS call...');
                    startRingtone('_BUNDLE_');
                } else {
                    console.log('[WebRTC] ⏭️ Skipping ringtone (already answered or throttled)');
                }
            } catch (e) {
                console.error('[WebRTC] Failed to apply offer:', e);
            }
        }
    };

    const handleAnswer = async (data: any) => {
        console.log('[WebRTC] 📥 Answer received from device');
        if (peerConnection.current && peerConnection.current.signalingState === 'have-local-offer') {
            try {
                await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data));
                await processPendingIceCandidates();
            } catch (e) {
                console.error('[WebRTC] Failed to apply answer:', e);
            }
        } else {
            console.warn('[WebRTC] Ignoring answer; no matching local offer');
        }
    };

    const handleCandidate = async (data: any) => {
        console.log('[WebRTC] 📥 Candidate from device:', data?.candidate?.substring?.(0, 80) || data);
        if (!peerConnection.current) {
            pendingIceCandidates.current.push(data);
            console.warn('[WebRTC] Candidate buffered (no peer connection yet)');
            return;
        }
        if (!peerConnection.current.remoteDescription) {
            pendingIceCandidates.current.push(data);
            console.warn('[WebRTC] Candidate buffered (waiting remote description)');
            return;
        }
        try {
            await peerConnection.current.addIceCandidate(new RTCIceCandidate(data));
            console.log('[WebRTC] ✅ Candidate added');
        } catch (e) {
            console.error('[WebRTC] ❌ Failed to add candidate:', e);
        }
    };

    return {
        localStream,
        remoteStream,
        callState,
        initializePeerConnection,
        startCall,
        answerCall,
        hangup,
        handleOffer,
        handleAnswer,
        handleCandidate,
    };
};

export default useWebRTC;