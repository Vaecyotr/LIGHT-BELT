"""Analysis sub-package: video and audio feature extraction."""

from light_engine.analysis.audio import AudioAnalyzer
from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.analysis.managed_audio_input import ManagedAudioInput
from light_engine.analysis.pulse_capture import ParecCapture, PCMChunk
from light_engine.analysis.source_selector import AudioSourceSelector
from light_engine.analysis.video import VideoAnalyzer
from light_engine.analysis.wled_audio_sync import (
    WledAudioSyncV2Source,
    decode_wled_audio_sync_v2,
)

__all__ = [
    "AudioAnalyzer",
    "AudioSourceSelector",
    "ManagedAudioInput",
    "ParecCapture",
    "PCMChunk",
    "MusicControlAnalyzer",
    "VideoAnalyzer",
    "WledAudioSyncV2Source",
    "decode_wled_audio_sync_v2",
]
