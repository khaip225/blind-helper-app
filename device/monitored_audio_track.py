#!/usr/bin/env python3
"""
Monitor audio track to verify frames are being sent
"""
import asyncio
import time
from aiortc.mediastreams import MediaStreamTrack
from config import logger

class MonitoredAudioTrack(MediaStreamTrack):
    """Audio track với monitoring để debug"""
    kind = "audio"
    
    def __init__(self, track):
        super().__init__()
        self.track = track
        self.frame_count = 0
        self.first_frame_ts = None
        self.last_log_ts = time.time()
        self.log_interval = 5  # Log mỗi 5 giây
        
    async def recv(self):
        frame = await self.track.recv()
        
        self.frame_count += 1
        if self.first_frame_ts is None:
            self.first_frame_ts = time.time()
            logger.info(f"🎤 First AUDIO frame captured from microphone!")
            logger.info(f"   Sample rate: {frame.sample_rate}")
            logger.info(f"   Samples: {frame.samples}")
            logger.info(f"   Format: {frame.format.name}")
            try:
                logger.info(f"   Layout: {frame.layout.name}")
            except:
                pass
        
        now = time.time()
        if now - self.last_log_ts >= self.log_interval:
            elapsed = now - self.first_frame_ts
            fps = self.frame_count / elapsed if elapsed > 0 else 0
            logger.info(f"🎤 Audio frames sent: {self.frame_count} ({fps:.1f} frames/sec)")
            self.last_log_ts = now
        
        return frame
