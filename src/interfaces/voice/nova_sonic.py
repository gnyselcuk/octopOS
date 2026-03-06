"""Nova Sonic Client — Real-time bidirectional speech-to-speech.

AWS Nova Sonic uses InvokeModelWithBidirectionalStream (not invoke_model).
This module wraps that streaming API with:
  - Wake-word detection via keyword scan on partial transcripts
  - Microphone capture (sounddevice preferred, pyaudio fallback)
  - TTS synthesis + audio playback
  - Graceful degradation when audio hardware or AWS is unavailable

Usage (CLI uses this internally via `octo voice`):
    sonic = NovaSonicClient()
    async for event in sonic.start_session(language="tr-TR", wake_word="hey octo"):
        if event["type"] == "transcript":
            print("You said:", event["text"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Any, AsyncIterator, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()

# ── optional audio deps ──────────────────────────────────────────────────────
try:
    import sounddevice as sd  # type: ignore
    import numpy as np         # type: ignore
    _HAS_AUDIO = True
except Exception:
    _HAS_AUDIO = False

try:
    import pyaudio            # type: ignore
    _HAS_PYAUDIO = True
except Exception:
    _HAS_PYAUDIO = False


# ── constants ────────────────────────────────────────────────────────────────
MODEL_ID = "amazon.nova-sonic-v1:0"
SAMPLE_RATE = 16_000          # Hz — Nova Sonic requires 16 kHz PCM
CHANNELS = 1
CHUNK_FRAMES = 1_600           # 100 ms per chunk
AUDIO_FORMAT = "pcm"


class NovaSonicClient:
    """AWS Nova Sonic bidirectional streaming client.

    Wraps ``bedrock-runtime:InvokeModelWithBidirectionalStream`` to provide
    real-time speech-to-speech capabilities.
    """

    def __init__(self, region: Optional[str] = None) -> None:
        self._config = get_config()
        self._region = region or self._config.aws.region
        self._client: Optional[Any] = None
        self._stream: Optional[Any] = None
        self._closed = False

        try:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
            )
            logger.info("Nova Sonic client initialised")
        except Exception as exc:
            logger.warning(f"Nova Sonic unavailable: {exc}")

    # ── public helpers ───────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True when both AWS client and audio hardware are accessible."""
        return self._client is not None and (_HAS_AUDIO or _HAS_PYAUDIO)

    async def close(self) -> None:
        """Close the active streaming session if any."""
        self._closed = True
        if self._stream:
            try:
                await self._stream.input_stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("Nova Sonic session closed")

    # ── main session generator ───────────────────────────────────────────────

    async def start_session(
        self,
        language: str = "en-US",
        wake_word: str = "hey octo",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Async generator that yields voice session events.

        Events:
            ``{"type": "wake"}``               — wake word detected
            ``{"type": "transcript", "text"}`` — final transcription
            ``{"type": "error",    "message"}``
            ``{"type": "exit"}``               — user said "exit" / "bye"
        """
        if not self.is_available():
            yield {"type": "error", "message": "Audio hardware or AWS client not available"}
            return

        if not self._client:
            yield {"type": "error", "message": "Bedrock client not initialised"}
            return

        self._closed = False
        logger.info(f"Nova Sonic session started (lang={language}, wake='{wake_word}')")

        try:
            # Open bidirectional stream
            self._stream = self._client.invoke_model_with_bidirectional_stream(
                modelId=MODEL_ID,
                body=self._build_session_config(language),
            )

            # Run mic capture + event processing concurrently
            async for event in self._session_loop(wake_word):
                yield event

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            msg = exc.response["Error"]["Message"]
            logger.error(f"Nova Sonic AWS error {code}: {msg}")
            yield {"type": "error", "message": f"AWS {code}: {msg}"}
        except Exception as exc:
            logger.error(f"Nova Sonic session error: {exc}")
            yield {"type": "error", "message": str(exc)}
        finally:
            await self.close()

    # ── TTS ─────────────────────────────────────────────────────────────────

    async def text_to_speech(self, text: str, voice_id: str = "Joanna") -> bytes:
        """Synthesise *text* and return raw PCM audio bytes.

        Falls back to Amazon Polly if Nova Sonic TTS is unavailable.
        """
        if not self._client:
            return b""

        # Send TTS request over the existing stream when active
        if self._stream:
            try:
                tts_event = json.dumps({
                    "event": "synthesize",
                    "text": text,
                    "voiceId": voice_id,
                })
                await self._stream.input_stream.send({"chunk": {"bytes": tts_event.encode()}})
                # Collect audio chunks from output until synthesis done
                audio_chunks: list[bytes] = []
                async for output_event in self._stream.output_stream:
                    chunk = output_event.get("chunk", {}).get("bytes")
                    if chunk:
                        parsed = json.loads(chunk)
                        if parsed.get("event") == "audio_chunk":
                            import base64
                            audio_chunks.append(base64.b64decode(parsed["audio"]))
                        elif parsed.get("event") == "synthesis_complete":
                            break
                return b"".join(audio_chunks)
            except Exception as exc:
                logger.warning(f"Nova Sonic TTS via stream failed: {exc}")

        # Polly fallback
        return await self._polly_tts(text, voice_id)

    async def play_audio(self, audio_bytes: bytes) -> None:
        """Play raw PCM audio bytes through the default output device."""
        if not audio_bytes:
            return
        try:
            if _HAS_AUDIO:
                import numpy as np
                samples = np.frombuffer(audio_bytes, dtype=np.int16)
                sd.play(samples, samplerate=SAMPLE_RATE, blocking=False)
                sd.wait()
            elif _HAS_PYAUDIO:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    output=True,
                )
                stream.write(audio_bytes)
                stream.stop_stream()
                stream.close()
                pa.terminate()
        except Exception as exc:
            logger.warning(f"Audio playback failed: {exc}")

    # ── internals ────────────────────────────────────────────────────────────

    def _build_session_config(self, language: str) -> bytes:
        config = {
            "event": "session_start",
            "language": language,
            "audioFormat": {
                "encoding": AUDIO_FORMAT,
                "sampleRateHz": SAMPLE_RATE,
                "channelCount": CHANNELS,
            },
            "transcriptionConfig": {
                "enablePartialResults": True,
            },
        }
        return json.dumps(config).encode()

    async def _session_loop(
        self, wake_word: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Drive the mic → stream → transcript loop."""
        activated = False
        transcript_buf: list[str] = []

        # Launch mic capture in a background task
        mic_task = asyncio.create_task(self._mic_producer())

        try:
            async for output_event in self._stream.output_stream:
                if self._closed:
                    break

                chunk = output_event.get("chunk", {}).get("bytes")
                if not chunk:
                    continue

                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                event_type = parsed.get("event", "")

                if event_type == "partial_transcript":
                    partial = parsed.get("text", "").lower()
                    if not activated and wake_word.lower() in partial:
                        activated = True
                        transcript_buf.clear()
                        yield {"type": "wake"}

                elif event_type == "final_transcript":
                    text = parsed.get("text", "").strip()
                    if not text:
                        continue

                    if not activated:
                        if wake_word.lower() in text.lower():
                            activated = True
                            yield {"type": "wake"}
                        continue

                    # exit phrases
                    if any(kw in text.lower() for kw in ("exit", "bye", "kapat", "güle güle")):
                        yield {"type": "exit"}
                        break

                    yield {"type": "transcript", "text": text}
                    activated = False   # wait for next wake word

                elif event_type == "error":
                    yield {"type": "error", "message": parsed.get("message", "Unknown")}
                    break

        finally:
            mic_task.cancel()
            try:
                await mic_task
            except asyncio.CancelledError:
                pass

    async def _mic_producer(self) -> None:
        """Continuously reads mic chunks and sends them to the stream."""
        if not self._stream:
            return

        loop = asyncio.get_running_loop()

        if _HAS_AUDIO:
            await self._mic_via_sounddevice(loop)
        elif _HAS_PYAUDIO:
            await self._mic_via_pyaudio(loop)

    async def _mic_via_sounddevice(self, loop: asyncio.AbstractEventLoop) -> None:
        q: asyncio.Queue[bytes] = asyncio.Queue()

        def callback(indata, frames, time_info, status):
            loop.call_soon_threadsafe(q.put_nowait, indata.tobytes())

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_FRAMES,
            callback=callback,
        ):
            while not self._closed and self._stream:
                try:
                    chunk = await asyncio.wait_for(q.get(), timeout=0.2)
                    await self._stream.input_stream.send(
                        {"chunk": {"bytes": chunk}}
                    )
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    logger.debug(f"Mic send error: {exc}")
                    break

    async def _mic_via_pyaudio(self, loop: asyncio.AbstractEventLoop) -> None:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_FRAMES,
        )
        try:
            while not self._closed and self._stream:
                raw = await loop.run_in_executor(
                    None, stream.read, CHUNK_FRAMES, False
                )
                await self._stream.input_stream.send({"chunk": {"bytes": raw}})
                await asyncio.sleep(0)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    async def _polly_tts(self, text: str, voice_id: str) -> bytes:
        """Amazon Polly fallback for TTS."""
        try:
            polly = boto3.client("polly", region_name=self._region)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: polly.synthesize_speech(
                    Text=text,
                    OutputFormat="pcm",
                    SampleRate=str(SAMPLE_RATE),
                    VoiceId=voice_id,
                    LanguageCode="tr-TR" if "tr" in self._region else "en-US",
                ),
            )
            return response["AudioStream"].read()
        except Exception as exc:
            logger.warning(f"Polly TTS fallback failed: {exc}")
            return b""
