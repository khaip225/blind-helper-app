import { MediaStream } from 'react-native-webrtc';

// --- Device Info ---
export interface DeviceInfo {
    pin: number;
    gps: { 
        lat: number; 
        long: number; 
        latitude?: number; 
        longitude?: number 
    };
}

// --- Alert Message ---
export interface AlertMessage {
    type: string;
    message: string;
    timestamp: number;
}

// --- Call State ---
export type CallState = 'idle' | 'calling' | 'receiving' | 'connected';

// --- WebRTC Hook Props & Return ---
export interface UseWebRTCProps {
    mobileId: string;
    deviceId: string | null;
    publish: (topic: string, message: string, qos?: 0 | 1 | 2) => void;
    connect?: (deviceId: string) => Promise<void>;
}

export interface UseWebRTCReturn {
    localStream: MediaStream | null;
    remoteStream: MediaStream | null;
    callState: CallState;
    
    initializePeerConnection: () => Promise<void>;
    startCall: () => Promise<void>;
    answerCall: () => Promise<void>;
    hangup: () => void;
    
    // Signal handlers
    handleOffer: (offer: any) => Promise<void>;
    handleAnswer: (answer: any) => Promise<void>;
    handleCandidate: (candidate: any) => Promise<void>;
}

// --- MQTT Connection Hook Props & Return ---
export interface UseMQTTConnectionProps {
    onMessage: (topic: string, payload: string) => void;
    onConnectionLost?: () => void;
}

export interface UseMQTTConnectionReturn {
    client: any; // Paho.Client
    isConnected: boolean;
    connect: (deviceId: string) => Promise<void>;
    disconnect: () => void;
    publish: (topic: string, message: string, qos?: 0 | 1 | 2) => void;
}

// --- MQTT Context Type ---
export interface MQTTContextType {
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
