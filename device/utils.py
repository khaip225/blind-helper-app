"""
Các hàm tiện ích
"""
import aioice.stun

def is_private_address(addr):
    """Kiểm tra địa chỉ IP có phải là private không"""
    if addr.startswith("10.") or addr.startswith("192.168."):
        return True
    if addr.startswith("172."):
        try:
            second_octet = int(addr.split(".")[1])
            return 16 <= second_octet <= 31
        except:
            return False
    return False

# Patch STUN private address check
aioice.stun.is_private_address = is_private_address

def print_banner(device_id, mqtt_broker, mqtt_port, force_turn, force_ipv4, turn_urls, turn_username, turn_password, playback_gain, playback_rate):
    """In banner khởi động"""
    print("\n" + "="*60)
    print("🚀 WebRTC Video Call Simulator")
    print("="*60)
    print(f"📱 Device ID: {device_id}")
    print(f"🌐 MQTT Broker: {mqtt_broker}:{mqtt_port}")
    if force_turn or force_ipv4:
        print("🔧 Active flags:")
        print(f"   - FORCE_TURN: {force_turn}")
        print(f"   - FORCE_IPV4: {force_ipv4}")
    if turn_urls:
        print(f"   - TURN_URLS: {turn_urls}")
        print(f"   - TURN_USERNAME set: {bool(turn_username)}")
        print(f"   - TURN_PASSWORD set: {bool(turn_password)}")
    print(f"🔊 Playback gain: {playback_gain}")
    print(f"🎚️ Playback rate: {playback_rate} Hz")
    print("📹 Press Enter to START SOS call (Device -> Mobile)")
    print("📞 Also listening for incoming calls from Mobile...")
    print("="*60 + "\n")
