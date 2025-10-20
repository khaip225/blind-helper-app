# MQTT Topics Architecture

## Topic Naming Convention

```
device/<deviceId>/*   → Device publishes, Mobile subscribes
mobile/<deviceId>/*   → Mobile publishes, Device subscribes
```

---

## 📱 Mobile App Topics

### Subscribe (Receive from Device)
| Topic | Purpose | Payload | QoS |
|-------|---------|---------|-----|
| `device/<deviceId>/presence` | Device online/offline status | `"online"` or `"offline"` | 1 |
| `device/<deviceId>/info` | Device status (battery, GPS) | `{"pin": 85, "gps": {"lat": 16.054, "long": 108.202}}` | 1 |
| `device/<deviceId>/alert` | Alerts from device | `{"type": "obstacle", "message": "...", "timestamp": 123}` | 1 |
| `device/<deviceId>/webrtc/offer` | **SOS call**: Device sends offer | `{"type": "offer", "sdp": "..."}` | 1 |
| `device/<deviceId>/webrtc/answer` | **Normal call**: Device answers mobile's offer | `{"type": "answer", "sdp": "..."}` | 1 |
| `device/<deviceId>/webrtc/candidate` | ICE candidates from device | `{"candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0}` | 1 |

### Publish (Send to Device)
| Topic | Purpose | Payload | QoS |
|-------|---------|---------|-----|
| `mobile/<deviceId>/webrtc/offer` | **Normal call**: Mobile initiates call | `{"type": "offer", "sdp": "..."}` | 1 |
| `mobile/<deviceId>/webrtc/answer` | **SOS call**: Mobile answers device's offer | `{"type": "answer", "sdp": "..."}` | 1 |
| `mobile/<deviceId>/webrtc/candidate` | ICE candidates from mobile | `{"candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0}` | 1 |

---

## 🔧 Device (Simulator) Topics

### Subscribe (Receive from Mobile)
| Topic | Purpose | Payload | QoS |
|-------|---------|---------|-----|
| `mobile/<deviceId>/webrtc/offer` | **Normal call**: Mobile initiates call | `{"type": "offer", "sdp": "..."}` | 1 |
| `mobile/<deviceId>/webrtc/answer` | **SOS call**: Mobile answers device's offer | `{"type": "answer", "sdp": "..."}` | 1 |
| `mobile/<deviceId>/webrtc/candidate` | ICE candidates from mobile | `{"candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0}` | 1 |

### Publish (Send to Mobile)
| Topic | Purpose | Payload | QoS |
|-------|---------|---------|-----|
| `device/<deviceId>/presence` | Device status | `"online"` | 1 |
| `device/<deviceId>/info` | Status updates | `{"pin": 85, "gps": {...}}` | 1 |
| `device/<deviceId>/alert` | Alerts | `{"type": "...", "message": "..."}` | 1 |
| `device/<deviceId>/webrtc/offer` | **SOS call**: Device initiates | `{"type": "offer", "sdp": "..."}` | 1 |
| `device/<deviceId>/webrtc/answer` | **Normal call**: Device responds | `{"type": "answer", "sdp": "..."}` | 1 |
| `device/<deviceId>/webrtc/candidate` | ICE candidates | `{"candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0}` | 1 |

---

## 📞 WebRTC Call Flows

### Flow 1: SOS Call (Device → Mobile) - INCOMING Mode

```
1. Device detects SOS
   └─> Publish to: device/device/webrtc/offer

2. Mobile receives offer
   └─> Subscribe from: device/device/webrtc/offer
   └─> Create answer
   └─> Publish to: mobile/device/webrtc/answer

3. Device receives answer
   └─> Subscribe from: mobile/device/webrtc/answer
   └─> WebRTC connection established

4. ICE Candidate Exchange (bidirectional)
   - Device publishes: device/device/webrtc/candidate
   - Mobile publishes: mobile/device/webrtc/candidate
```

**Simulator command:**
```bash
python webrtc_device_simulator.py --sos-at 10
```

**Mobile trigger:** 
- App shows alert: "Yêu cầu SOS!" → Navigate to `/call?mode=incoming`

---

### Flow 2: Normal Call (Mobile → Device) - OUTGOING Mode

```
1. User taps "📹 Video Call" in app
   └─> Mobile creates offer
   └─> Publish to: mobile/device/webrtc/offer

2. Device receives offer
   └─> Subscribe from: mobile/device/webrtc/offer
   └─> Create answer
   └─> Publish to: device/device/webrtc/answer

3. Mobile receives answer
   └─> Subscribe from: device/device/webrtc/answer
   └─> WebRTC connection established

4. ICE Candidate Exchange (bidirectional)
   - Mobile publishes: mobile/device/webrtc/candidate
   - Device publishes: device/device/webrtc/candidate
```

**Simulator command:**
```bash
python webrtc_device_simulator.py --answer-mode
```

**Mobile trigger:** 
- Tap "📹 Video Call" button → Navigate to `/call?mode=outgoing`

---

## 🔐 Security Considerations

### Current Implementation (Public Broker)
- ⚠️ Using `broker.hivemq.com` (public, no authentication)
- ⚠️ Anyone can subscribe to `device/*` or `mobile/*` topics
- ⚠️ No encryption on MQTT payload (WebRTC has encryption but signaling is exposed)

### Production Recommendations
1. **Private MQTT Broker**: Self-hosted Mosquitto or AWS IoT Core
2. **Authentication**: Username/password or client certificates
3. **Authorization**: ACL rules to restrict topic access
4. **TLS/SSL**: Use port 8883/8084 with SSL certificates
5. **Token-based Auth**: JWT tokens for mobile clients
6. **Payload Encryption**: Encrypt sensitive data before publishing

### Example ACL (Mosquitto)
```
# Device can only publish to device/* and subscribe to mobile/*
user device-001
topic write device/device-001/#
topic read mobile/device-001/#

# Mobile can only publish to mobile/* and subscribe to device/*
user mobile-app-123
topic write mobile/device-001/#
topic read device/device-001/#
```

---

## 🧪 Testing

### Test MQTT Topics with MQTT Explorer
1. Download: http://mqtt-explorer.com/
2. Connect to `broker.hivemq.com:1883`
3. Subscribe to `device/#` and `mobile/#`
4. Monitor all messages during call

### Test with Mosquitto CLI
```bash
# Subscribe to all device topics
mosquitto_sub -h broker.hivemq.com -p 1883 -t "device/#" -v

# Subscribe to all mobile topics
mosquitto_sub -h broker.hivemq.com -p 1883 -t "mobile/#" -v

# Publish test offer
mosquitto_pub -h broker.hivemq.com -p 1883 -t "mobile/device/webrtc/offer" -m '{"type":"offer","sdp":"..."}'
```

---

## 📊 Topic Usage Statistics

| Topic Pattern | Messages/Call | Size (avg) | Critical |
|---------------|---------------|------------|----------|
| `*/webrtc/offer` | 1 | 2-5 KB | ✅ Yes |
| `*/webrtc/answer` | 1 | 2-5 KB | ✅ Yes |
| `*/webrtc/candidate` | 5-20 | 200 B | ✅ Yes |
| `device/info` | 1/10s | 100 B | ⚠️ Medium |
| `device/alert` | On-demand | 150 B | ⚠️ Medium |
| `device/presence` | On connect | 10 B | ℹ️ Low |

---

## 🚀 Future Enhancements

### Push Notifications (FCM/APNs)
When mobile app is closed/background:
```
1. Device sends SOS
   └─> Backend server receives MQTT message
   └─> Send FCM/APNs notification
   └─> "User A is calling SOS. Tap to connect"

2. User taps notification
   └─> App opens to /call?mode=incoming
   └─> Subscribe to topics and connect WebRTC
```

### Topic for Backend Server
```
backend/notifications/<deviceId>
  └─> Device publishes SOS alerts here
  └─> Backend forwards to FCM/APNs
```

### Presence Heartbeat
```
device/<deviceId>/heartbeat (every 30s)
  └─> Mobile monitors for timeout
  └─> Show "Device disconnected" if no heartbeat
```
