import { useMQTT } from "@/context/MQTTContext";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { useEffect, useRef, useState } from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { mediaDevices, MediaStream, RTCIceCandidate, RTCPeerConnection, RTCSessionDescription, RTCView } from "react-native-webrtc";

export default function CallScreen() {
  const { rtcOffer, iceCandidates, publish, deviceOnline } = useMQTT();
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);
  const [callStatus, setCallStatus] = useState<'idle' | 'connecting' | 'connected' | 'failed'>('idle');
  
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const deviceIdRef = useRef<string>('');

  // ICE servers configuration (sử dụng STUN server công khai)
  const iceServers = {
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun1.l.google.com:19302' },
    ],
  };

  // Lấy device ID từ AsyncStorage
  useEffect(() => {
    const loadDeviceId = async () => {
      const id = await AsyncStorage.getItem('DEVICE_ID');
      if (id) deviceIdRef.current = id;
    };
    loadDeviceId();
  }, []);

  // Khởi tạo WebRTC khi có offer từ thiết bị
  useEffect(() => {
    if (!rtcOffer || !deviceOnline) return;

    console.log('📞 Nhận offer từ thiết bị, bắt đầu thiết lập WebRTC...');
    setCallStatus('connecting');
    
    const setupWebRTC = async () => {
      try {
        // 1. Tạo peer connection
        const pc = new RTCPeerConnection(iceServers);
        pcRef.current = pc;

        // 2. Lấy local media stream (camera + mic)
        const stream = await mediaDevices.getUserMedia({
          audio: true,
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30 },
            facingMode: 'user',
          },
        });
        setLocalStream(stream);
        
        // 3. Thêm local tracks vào peer connection
        stream.getTracks().forEach((track) => {
          pc.addTrack(track, stream);
        });

        // 4. Xử lý remote stream (sử dụng addEventListener thay vì ontrack)
        (pc as unknown as EventTarget).addEventListener('addstream', (event: any) => {
          console.log('📹 Nhận remote stream từ thiết bị');
          if (event.stream) {
            setRemoteStream(event.stream);
            setCallStatus('connected');
          }
        });

        // 5. Xử lý ICE candidates của app và gửi cho thiết bị
        (pc as unknown as EventTarget).addEventListener('icecandidate', (event: any) => {
          if (event.candidate) {
            console.log('🧊 Gửi ICE candidate cho thiết bị');
            const candidateData = {
              candidate: event.candidate.candidate,
              sdpMLineIndex: event.candidate.sdpMLineIndex,
              sdpMid: event.candidate.sdpMid,
            };
            publish(
              `device/${deviceIdRef.current}/webrtc/candidate`,
              JSON.stringify(candidateData)
            );
          }
        });

        // 6. Xử lý connection state
        (pc as unknown as EventTarget).addEventListener('connectionstatechange', () => {
          console.log('Connection state:', pc.connectionState);
          if (pc.connectionState === 'connected') {
            setCallStatus('connected');
          } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
            setCallStatus('failed');
            Alert.alert('Lỗi', 'Kết nối WebRTC thất bại hoặc bị ngắt');
          }
        });

        // 7. Set remote description (offer từ thiết bị)
        if (rtcOffer && rtcOffer.sdp) {
          await pc.setRemoteDescription(new RTCSessionDescription({
            type: rtcOffer.type,
            sdp: rtcOffer.sdp,
          }));
          console.log('✅ Đã set remote description (offer)');

          // 8. Tạo answer và gửi cho thiết bị
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          console.log('📤 Gửi answer cho thiết bị');
          
          publish(
            `device/${deviceIdRef.current}/webrtc/answer`,
            JSON.stringify({
              type: answer.type,
              sdp: answer.sdp,
            })
          );
        }
      } catch (err) {
        console.error('❌ Lỗi thiết lập WebRTC:', err);
        setCallStatus('failed');
        Alert.alert('Lỗi', 'Không thể thiết lập cuộc gọi video: ' + (err as Error).message);
      }
    };

    setupWebRTC();

    return () => {
      const cleanup = () => {
        console.log('🧹 Dọn dẹp WebRTC resources');
        
        if (localStream) {
          localStream.getTracks().forEach(track => track.stop());
          setLocalStream(null);
        }
        
        if (remoteStream) {
          remoteStream.getTracks().forEach(track => track.stop());
          setRemoteStream(null);
        }
        
        if (pcRef.current) {
          pcRef.current.close();
          pcRef.current = null;
        }
        
        setCallStatus('idle');
      };
      cleanup();
    };
  }, [rtcOffer, deviceOnline, publish]);

  // Xử lý ICE candidates từ thiết bị
  useEffect(() => {
    if (!pcRef.current || iceCandidates.length === 0) return;

    iceCandidates.forEach(async (candidate) => {
      try {
        await pcRef.current?.addIceCandidate(new RTCIceCandidate(candidate));
        console.log('✅ Đã thêm ICE candidate từ thiết bị');
      } catch (err) {
        console.error('❌ Lỗi thêm ICE candidate:', err);
      }
    });
  }, [iceCandidates]);

  const setupWebRTC = async () => {
    try {
      // 1. Tạo peer connection
      const pc = new RTCPeerConnection(iceServers);
      pcRef.current = pc;

      // 2. Lấy local media stream (camera + mic)
      const stream = await mediaDevices.getUserMedia({
        audio: true,
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30 },
          facingMode: 'user',
        },
      });
      setLocalStream(stream);
      
      // 3. Thêm local tracks vào peer connection
      stream.getTracks().forEach((track) => {
        pc.addTrack(track, stream);
      });

      // 4. Xử lý remote stream (sử dụng addEventListener thay vì ontrack)
      (pc as unknown as EventTarget).addEventListener('addstream', (event: any) => {
        console.log('📹 Nhận remote stream từ thiết bị');
        if (event.stream) {
          setRemoteStream(event.stream);
          setCallStatus('connected');
        }
      });

      // 5. Xử lý ICE candidates của app và gửi cho thiết bị
      (pc as unknown as EventTarget).addEventListener('icecandidate', (event: any) => {
        if (event.candidate) {
          console.log('🧊 Gửi ICE candidate cho thiết bị');
          const candidateData = {
            candidate: event.candidate.candidate,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            sdpMid: event.candidate.sdpMid,
          };
          publish(
            `device/${deviceIdRef.current}/webrtc/candidate`,
            JSON.stringify(candidateData)
          );
        }
      });

      // 6. Xử lý connection state
      (pc as unknown as EventTarget).addEventListener('connectionstatechange', () => {
        console.log('Connection state:', pc.connectionState);
        if (pc.connectionState === 'connected') {
          setCallStatus('connected');
        } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
          setCallStatus('failed');
          Alert.alert('Lỗi', 'Kết nối WebRTC thất bại hoặc bị ngắt');
        }
      });

      // 7. Set remote description (offer từ thiết bị)
      if (rtcOffer && rtcOffer.sdp) {
        await pc.setRemoteDescription(new RTCSessionDescription({
          type: rtcOffer.type,
          sdp: rtcOffer.sdp,
        }));
        console.log('✅ Đã set remote description (offer)');

        // 8. Tạo answer và gửi cho thiết bị
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        console.log('📤 Gửi answer cho thiết bị');
        
        publish(
          `device/${deviceIdRef.current}/webrtc/answer`,
          JSON.stringify({
            type: answer.type,
            sdp: answer.sdp,
          })
        );
      }
    } catch (err) {
      console.error('❌ Lỗi thiết lập WebRTC:', err);
      setCallStatus('failed');
      Alert.alert('Lỗi', 'Không thể thiết lập cuộc gọi video: ' + (err as Error).message);
    }
  };

  const cleanup = () => {
    console.log('🧹 Dọn dẹp WebRTC resources');
    
    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
      setLocalStream(null);
    }
    
    if (remoteStream) {
      remoteStream.getTracks().forEach(track => track.stop());
      setRemoteStream(null);
    }
    
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    
    setCallStatus('idle');
  };

  const toggleMute = () => {
    if (localStream) {
      const audioTrack = localStream.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        setIsMuted(!audioTrack.enabled);
      }
    }
  };

  const toggleVideo = () => {
    if (localStream) {
      const videoTrack = localStream.getVideoTracks()[0];
      if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled;
        setIsVideoEnabled(videoTrack.enabled);
      }
    }
  };

  const endCall = () => {
    cleanup();
    Alert.alert('Kết thúc cuộc gọi', 'Cuộc gọi đã kết thúc');
  };

  if (!deviceOnline) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContent}>
          <Ionicons name="phone-portrait-outline" size={80} color="#999" />
          <Text style={styles.statusText}>Thiết bị chưa kết nối</Text>
          <Text style={styles.hintText}>Vui lòng kết nối thiết bị trước khi gọi</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (callStatus === 'idle' || callStatus === 'failed') {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContent}>
          <Ionicons name="videocam-outline" size={80} color="#007AFF" />
          <Text style={styles.statusText}>
            {callStatus === 'failed' ? 'Cuộc gọi thất bại' : 'Chờ cuộc gọi từ thiết bị'}
          </Text>
          <Text style={styles.hintText}>
            {callStatus === 'failed' 
              ? 'Vui lòng thử lại sau' 
              : 'Thiết bị cần gửi offer để bắt đầu cuộc gọi'}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Remote video (thiết bị) - màn hình chính */}
      {remoteStream ? (
        <RTCView
          streamURL={remoteStream.toURL()}
          style={styles.remoteVideo}
          objectFit="cover"
          mirror={false}
        />
      ) : (
        <View style={styles.remoteVideoPlaceholder}>
          <Ionicons name="videocam-off" size={60} color="#fff" />
          <Text style={styles.placeholderText}>
            {callStatus === 'connecting' ? 'Đang kết nối...' : 'Chờ video từ thiết bị'}
          </Text>
        </View>
      )}

      {/* Local video (app) - preview nhỏ ở góc */}
      {localStream && isVideoEnabled && (
        <View style={styles.localVideoContainer}>
          <RTCView
            streamURL={localStream.toURL()}
            style={styles.localVideo}
            objectFit="cover"
            mirror={true}
          />
        </View>
      )}

      {/* Call status overlay */}
      {callStatus === 'connecting' && (
        <View style={styles.statusOverlay}>
          <Text style={styles.statusOverlayText}>Đang kết nối...</Text>
        </View>
      )}

      {/* Control buttons */}
      <View style={styles.controlsContainer}>
        <TouchableOpacity
          style={[styles.controlButton, isMuted && styles.controlButtonActive]}
          onPress={toggleMute}
        >
          <Ionicons
            name={isMuted ? "mic-off" : "mic"}
            size={28}
            color="white"
          />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.controlButton, styles.endCallButton]}
          onPress={endCall}
        >
          <Ionicons name="call" size={28} color="white" />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.controlButton, !isVideoEnabled && styles.controlButtonActive]}
          onPress={toggleVideo}
        >
          <Ionicons
            name={isVideoEnabled ? "videocam" : "videocam-off"}
            size={28}
            color="white"
          />
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  statusText: {
    fontSize: 20,
    fontWeight: '600',
    color: '#fff',
    marginTop: 20,
    textAlign: 'center',
  },
  hintText: {
    fontSize: 14,
    color: '#999',
    marginTop: 8,
    textAlign: 'center',
  },
  remoteVideo: {
    flex: 1,
    width: '100%',
    backgroundColor: '#000',
  },
  remoteVideoPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
  },
  placeholderText: {
    fontSize: 16,
    color: '#fff',
    marginTop: 16,
  },
  localVideoContainer: {
    position: 'absolute',
    top: 60,
    right: 20,
    width: 120,
    height: 160,
    borderRadius: 12,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: '#007AFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 5,
  },
  localVideo: {
    width: '100%',
    height: '100%',
  },
  statusOverlay: {
    position: 'absolute',
    top: '50%',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  statusOverlayText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  controlsContainer: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 30,
    paddingHorizontal: 20,
  },
  controlButton: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  controlButtonActive: {
    backgroundColor: 'rgba(220, 38, 38, 0.8)',
    borderColor: '#dc2626',
  },
  endCallButton: {
    backgroundColor: '#dc2626',
    borderColor: '#dc2626',
    width: 70,
    height: 70,
    borderRadius: 35,
  },
});
