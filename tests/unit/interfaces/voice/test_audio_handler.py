"""Unit tests for interfaces/voice/audio_handler.py module.

This module tests the audio stream processing for voice interface.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.interfaces.voice.audio_handler import AudioHandler


class TestAudioHandler:
    """Test AudioHandler class."""
    
    @pytest.fixture
    def default_handler(self):
        """Create audio handler with default settings."""
        return AudioHandler()
    
    @pytest.fixture
    def custom_handler(self):
        """Create audio handler with custom settings."""
        return AudioHandler(sample_rate=48000, channels=2)
    
    def test_default_initialization(self, default_handler):
        """Test initialization with default values."""
        assert default_handler.sample_rate == 16000
        assert default_handler.channels == 1
    
    def test_custom_initialization(self, custom_handler):
        """Test initialization with custom values."""
        assert custom_handler.sample_rate == 48000
        assert custom_handler.channels == 2
    
    @pytest.mark.asyncio
    async def test_stream_microphone(self, default_handler):
        """Test microphone streaming."""
        chunks = []
        
        # Collect only a few chunks for testing
        async for chunk in default_handler.stream_microphone():
            chunks.append(chunk)
            if len(chunks) >= 3:
                break
        
        assert len(chunks) == 3
        # Each chunk should be bytes
        for chunk in chunks:
            assert isinstance(chunk, bytes)
            assert len(chunk) == 320  # 20ms of 16-bit 8kHz audio
    
    @pytest.mark.asyncio
    async def test_stream_microphone_yields_audio_chunks(self, default_handler):
        """Test that microphone stream yields valid audio chunks."""
        chunk_count = 0
        
        async for chunk in default_handler.stream_microphone():
            assert isinstance(chunk, bytes)
            assert len(chunk) > 0
            chunk_count += 1
            if chunk_count >= 2:
                break
        
        assert chunk_count == 2
    
    @pytest.mark.asyncio
    async def test_play_audio(self, default_handler):
        """Test audio playback."""
        async def mock_audio_stream():
            for i in range(3):
                yield b"\x00" * 320
        
        # Should not raise
        await default_handler.play_audio(mock_audio_stream())
    
    @pytest.mark.asyncio
    async def test_play_audio_empty_stream(self, default_handler):
        """Test playing empty audio stream."""
        async def empty_stream():
            return
            yield b""  # Make it a generator
        
        # Should not raise
        await default_handler.play_audio(empty_stream())
    
    @pytest.mark.asyncio
    async def test_play_audio_consumes_all_chunks(self, default_handler):
        """Test that play_audio consumes all chunks from stream."""
        chunks_received = []
        
        async def audio_stream():
            for i in range(5):
                chunk = f"chunk_{i}".encode()
                chunks_received.append(chunk)
                yield chunk
        
        await default_handler.play_audio(audio_stream())
        
        assert len(chunks_received) == 5
    
    @pytest.mark.asyncio
    async def test_stream_microphone_respects_sample_rate(self):
        """Test that streaming respects sample rate timing."""
        handler_8k = AudioHandler(sample_rate=8000)
        handler_16k = AudioHandler(sample_rate=16000)
        
        # Both should work, just with different timing
        chunks_8k = []
        chunks_16k = []
        
        async for chunk in handler_8k.stream_microphone():
            chunks_8k.append(chunk)
            if len(chunks_8k) >= 2:
                break
        
        async for chunk in handler_16k.stream_microphone():
            chunks_16k.append(chunk)
            if len(chunks_16k) >= 2:
                break
        
        assert len(chunks_8k) == 2
        assert len(chunks_16k) == 2
    
    def test_audio_handler_properties(self):
        """Test audio handler properties are accessible."""
        handler = AudioHandler(sample_rate=44100, channels=2)
        
        assert hasattr(handler, 'sample_rate')
        assert hasattr(handler, 'channels')
        assert handler.sample_rate == 44100
        assert handler.channels == 2
    
    @pytest.mark.asyncio
    async def test_stream_and_play_integration(self, default_handler):
        """Test streaming and playing work together."""
        # Stream from microphone and play back
        async def relay_stream():
            async for chunk in default_handler.stream_microphone():
                yield chunk
                # Only process a few chunks
                break
        
        # Should not raise
        await default_handler.play_audio(relay_stream())
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, default_handler):
        """Test that multiple handlers can operate concurrently."""
        handler1 = AudioHandler(sample_rate=16000, channels=1)
        handler2 = AudioHandler(sample_rate=48000, channels=2)
        
        chunks1 = []
        chunks2 = []
        
        async def collect_from_handler1():
            async for chunk in handler1.stream_microphone():
                chunks1.append(chunk)
                if len(chunks1) >= 2:
                    break
        
        async def collect_from_handler2():
            async for chunk in handler2.stream_microphone():
                chunks2.append(chunk)
                if len(chunks2) >= 2:
                    break
        
        # Run concurrently
        await asyncio.gather(collect_from_handler1(), collect_from_handler2())
        
        assert len(chunks1) == 2
        assert len(chunks2) == 2
