"""
Xử lý video
"""
import asyncio
import time
import fractions
import platform
import av
import numpy as np
from aiortc.mediastreams import MediaStreamTrack
from aiortc.contrib.media import MediaPlayer
from config import logger, state, VIDEO_FRAME_LOG_INTERVAL, VIDEO_FIRST_FRAME_TIMEOUT

class MonitoredVideoTrack(MediaStreamTrack):
    """Video track với monitoring"""
    kind = "video"

    def __init__(self, source_track: MediaStreamTrack):
        super().__init__()
        self._source = source_track

    async def recv(self):
        frame = await self._source.recv()
        state.video_frame_count += 1
        if state.video_first_frame_ts is None:
            state.video_first_frame_ts = time.time()
            logger.info("🎬 First video frame captured (outgoing)")
        if state.video_frame_count % VIDEO_FRAME_LOG_INTERVAL == 0:
            logger.info(f"📡 Sent {state.video_frame_count} video frames")
        return frame

    def stop(self):
        try:
            self._source.stop()
        except Exception:
            pass
        super().stop()

class SyntheticVideo(MediaStreamTrack):
    """Video track tổng hợp (màu sắc thay đổi)"""
    kind = "video"
    
    def __init__(self):
        super().__init__()
        self._pts = 0
        self._time_base = fractions.Fraction(1, 30)
        self._hue = 0
    
    async def recv(self):
        await asyncio.sleep(1/30)
        frame = av.VideoFrame(width=640, height=480, format='rgb24')
        # Generate solid color changing over time
        self._hue = (self._hue + 3) % 360
        # Simple hue to RGB approximation
        r = abs((self._hue % 360) - 180) / 180
        g = abs(((self._hue + 120) % 360) - 180) / 180
        b = abs(((self._hue + 240) % 360) - 180) / 180
        arr = np.zeros((480, 640, 3), dtype=np.uint8)
        arr[..., 0] = int(r * 255)
        arr[..., 1] = int(g * 255)
        arr[..., 2] = int(b * 255)
        frame.pts = self._pts
        frame.time_base = self._time_base
        frame.planes[0].update(arr.tobytes())
        self._pts += 1
        if self._pts == 1:
            logger.info("🧪 Synthetic video track started")
        if self._pts % 120 == 0:
            logger.info(f"🧪 Synthetic frames sent: {self._pts}")
        return frame

async def replace_with_synthetic_video(pc):
    """Thay thế track video bằng track tổng hợp"""
    try:
        for sender in list(pc.getSenders()):
            if sender.track and sender.track.kind == 'video':
                await sender.replaceTrack(None)
        synthetic = SyntheticVideo()
        pc.addTrack(synthetic)
        logger.info("🔁 Replaced camera video with synthetic test track")
    except Exception as e:
        logger.warning(f"Could not replace video track: {e}")

async def monitor_video():
    """Monitor video frames sau khi kết nối"""
    await asyncio.sleep(VIDEO_FIRST_FRAME_TIMEOUT)
    if state.video_first_frame_ts is None or state.video_frame_count == 0:
        logger.warning(
            f"⚠️ No video frame within {VIDEO_FIRST_FRAME_TIMEOUT}s after connection. Switching to synthetic test video track."
        )
        if state.pc:
            await replace_with_synthetic_video(state.pc)

def setup_video_player():
    """Thiết lập video player theo platform"""
    options = {"framerate": "30", "video_size": "640x480"}
    
    if platform.system() == "Windows":
        # Windows: Try to open video from webcam
        video_devices = [
            "Integrated Webcam",
            "USB Camera",
            "HD Webcam",
            "Webcam",
        ]
        
        for video_name in video_devices:
            try:
                # Try to open video with audio from same device
                player = MediaPlayer(f"video={video_name}:audio={video_name}", format="dshow", options=options)
                logger.info(f"📹 Using camera with audio: {video_name}")
                return player
            except Exception:
                # If audio fails, try video-only
                try:
                    player = MediaPlayer(f"video={video_name}", format="dshow", options=options)
                    logger.info(f"📹 Using camera (video only): {video_name}")
                    return player
                except Exception:
                    continue
        
        # Try default
        try:
            player = MediaPlayer("video=0", format="dshow", options=options)
            logger.info("📹 Using default camera")
            return player
        except Exception as e:
            logger.error(f"Could not open webcam: {e}")
            return None
    
    elif platform.system() == "Darwin":
        try:
            player = MediaPlayer("default:none", format="avfoundation", options=options)
            logger.info("📹 Using macOS camera")
            return player
        except Exception as e:
            logger.error(f"Could not open camera: {e}")
            return None
    
    else:  # Linux
        camera_devices = ["/dev/video0", "/dev/video1"]
        
        for device in camera_devices:
            try:
                player = MediaPlayer(device, format="v4l2", options=options)
                logger.info(f"📹 Using camera at {device}")
                return player
            except Exception as e:
                logger.warning(f"Could not open {device}: {e}")
        
        logger.error("❌ Could not open any camera device!")
        return None
