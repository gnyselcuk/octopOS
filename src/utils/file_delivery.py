"""File Delivery Service — S3 storage + secure multi-channel delivery.

When octopOS produces a file (code, screenshot, report, voice) this service:
  1. Uploads the file to a private S3 bucket
  2. Generates a time-limited presigned URL (default 24 h)
  3. Delivers the file via the originating channel:
       • Telegram → sendDocument / sendPhoto / sendVoice
       • CLI     → prints the presigned URL + local path hint
       • Slack   → files.upload (future)

Security model
--------------
* Bucket is PRIVATE (no public-read ACL).
* Only the presigned URL is shared — it carries a cryptographic signature
  that expires after `url_expiry_seconds` (default 86 400 s = 24 h).
* After expiry even the URL holder cannot access the object without a new
  presigned URL being issued by octopOS.

Usage
-----
    from src.utils.file_delivery import FileDeliveryService, DeliveryChannel

    svc = FileDeliveryService()

    # Telegram code delivery
    await svc.deliver(
        channel=DeliveryChannel.TELEGRAM,
        chat_id="12345678",
        file_bytes=code_bytes,
        filename="todo_app.py",
        caption="✅ <b>todo_app</b> hazır!",
        content_type="code",
        bot=telegram_bot_instance,
    )

    # CLI delivery (prints URL)
    await svc.deliver(
        channel=DeliveryChannel.CLI,
        file_bytes=screenshot_bytes,
        filename="mission_screenshot.png",
        content_type="screenshot",
    )
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

from src.utils.config import get_config
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.interfaces.telegram.bot import TelegramBot

logger = get_logger()


class DeliveryChannel(str, Enum):
    TELEGRAM = "telegram"
    CLI      = "cli"
    SLACK    = "slack"   # future


class ContentType(str, Enum):
    CODE       = "code"
    SCREENSHOT = "screenshot"
    REPORT     = "report"
    VOICE      = "voice"
    DOCUMENT   = "document"


class FileDeliveryService:
    """Unified file upload + delivery across channels.

    Thread-safe: each call creates its own boto3 S3 client.
    """

    # S3 key prefix per content type
    _KEY_PREFIXES: Dict[str, str] = {
        ContentType.CODE:       "code",
        ContentType.SCREENSHOT: "screenshots",
        ContentType.REPORT:     "reports",
        ContentType.VOICE:      "voice",
        ContentType.DOCUMENT:   "documents",
    }

    def __init__(
        self,
        bucket: Optional[str] = None,
        url_expiry_seconds: int = 86_400,   # 24 hours
    ) -> None:
        self._config = get_config()
        self._bucket = bucket or getattr(self._config, "s3_bucket", None) or os.environ.get(
            "OCTOPOS_S3_BUCKET", "octopos-artifacts"
        )
        self._expiry = url_expiry_seconds
        logger.info(
            f"FileDeliveryService initialised (bucket={self._bucket}, "
            f"url_expiry={url_expiry_seconds}s)"
        )

    # ── public API ────────────────────────────────────────────────────────────

    async def deliver(
        self,
        *,
        channel: DeliveryChannel,
        file_bytes: bytes,
        filename: str,
        content_type: str = ContentType.DOCUMENT,
        caption: str = "",
        chat_id: Optional[str] = None,
        bot: Optional["TelegramBot"] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload file to S3 and deliver via *channel*.

        Returns a dict with:
            s3_key, presigned_url, channel, delivered (bool)
        """
        # ── 1. S3 upload ─────────────────────────────────────────────────────
        s3_key, presigned_url = await asyncio.get_event_loop().run_in_executor(
            None,
            self._upload_to_s3,
            file_bytes,
            filename,
            content_type,
        )

        result: Dict[str, Any] = {
            "s3_key":        s3_key,
            "presigned_url": presigned_url,
            "channel":       channel,
            "filename":      filename,
            "size_bytes":    len(file_bytes),
            "delivered":     False,
        }

        # ── 2. Channel delivery ───────────────────────────────────────────────
        if channel == DeliveryChannel.TELEGRAM:
            result["delivered"] = await self._deliver_telegram(
                bot=bot,
                chat_id=chat_id,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                caption=self._build_caption(caption, filename, presigned_url),
                reply_to=reply_to,
            )

        elif channel == DeliveryChannel.CLI:
            self._deliver_cli(filename, presigned_url, len(file_bytes))
            result["delivered"] = True

        else:
            logger.warning(f"Delivery channel '{channel}' not yet implemented")

        logger.info(
            f"FileDelivery: {filename} ({len(file_bytes)} bytes) → "
            f"{channel} | delivered={result['delivered']}"
        )
        return result

    async def deliver_code(
        self,
        *,
        code: str,
        name: str,
        channel: DeliveryChannel = DeliveryChannel.CLI,
        chat_id: Optional[str] = None,
        bot: Optional["TelegramBot"] = None,
        reply_to: Optional[str] = None,
        extra_caption: str = "",
    ) -> Dict[str, Any]:
        """Convenience wrapper for code file delivery."""
        filename = f"{name}.py"
        caption = (
            f"✅ <b>{name}</b> oluşturuldu, test edildi ve sisteme kaydedildi.\n"
            f"{extra_caption}"
        )
        return await self.deliver(
            channel=channel,
            file_bytes=code.encode("utf-8"),
            filename=filename,
            content_type=ContentType.CODE,
            caption=caption,
            chat_id=chat_id,
            bot=bot,
            reply_to=reply_to,
        )

    async def deliver_screenshot(
        self,
        *,
        image_bytes: bytes,
        label: str = "screenshot",
        channel: DeliveryChannel = DeliveryChannel.CLI,
        chat_id: Optional[str] = None,
        bot: Optional["TelegramBot"] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convenience wrapper for screenshot delivery."""
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{ts}.png"
        return await self.deliver(
            channel=channel,
            file_bytes=image_bytes,
            filename=filename,
            content_type=ContentType.SCREENSHOT,
            caption=f"📸 <b>{label}</b>",
            chat_id=chat_id,
            bot=bot,
            reply_to=reply_to,
        )

    # ── S3 ────────────────────────────────────────────────────────────────────

    def _upload_to_s3(
        self, file_bytes: bytes, filename: str, content_type: str
    ) -> tuple[str, str]:
        """Upload to private S3 bucket. Returns (s3_key, presigned_url)."""
        try:
            import boto3
            from src.utils.aws_sts import get_auth_manager

            auth = get_auth_manager()
            creds = auth.get_credentials()
            client = boto3.client(
                "s3",
                region_name=creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                aws_session_token=creds.session_token,
            )

            prefix = self._KEY_PREFIXES.get(content_type, "misc")
            ts = datetime.utcnow().strftime("%Y/%m/%d")
            s3_key = f"{prefix}/{ts}/{filename}"

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                client.upload_file(
                    tmp_path,
                    self._bucket,
                    s3_key,
                    ExtraArgs={"ServerSideEncryption": "AES256"},  # encrypt at rest
                )
            finally:
                os.unlink(tmp_path)

            presigned_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": s3_key},
                ExpiresIn=self._expiry,
            )

            logger.info(f"S3 upload: s3://{self._bucket}/{s3_key}")
            return s3_key, presigned_url

        except Exception as exc:
            logger.warning(f"S3 upload failed (continuing without S3): {exc}")
            return filename, ""

    # ── Telegram delivery ─────────────────────────────────────────────────────

    async def _deliver_telegram(
        self,
        bot: Optional["TelegramBot"],
        chat_id: Optional[str],
        file_bytes: bytes,
        filename: str,
        content_type: str,
        caption: str,
        reply_to: Optional[str],
    ) -> bool:
        if not bot or not chat_id:
            logger.warning("Telegram delivery skipped: bot or chat_id missing")
            return False

        # Show upload action
        await bot.send_action(chat_id, action="upload_document")

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if content_type == ContentType.SCREENSHOT or ext in ("png", "jpg", "jpeg", "gif"):
            return await bot.send_photo(
                chat_id=chat_id,
                photo_bytes=file_bytes,
                caption=caption,
                reply_to=reply_to,
            )
        elif content_type == ContentType.VOICE or ext in ("ogg", "mp3", "opus"):
            return await bot.send_voice(
                chat_id=chat_id,
                voice_bytes=file_bytes,
                caption=caption,
                reply_to=reply_to,
            )
        else:
            return await bot.send_document(
                chat_id=chat_id,
                file_bytes=file_bytes,
                filename=filename,
                caption=caption,
                reply_to=reply_to,
            )

    # ── CLI delivery ──────────────────────────────────────────────────────────

    def _deliver_cli(self, filename: str, presigned_url: str, size: int) -> None:
        print(f"\n📎 Dosya hazır: {filename} ({size:,} bytes)")
        if presigned_url:
            expires_h = self._expiry // 3600
            print(f"🔗 S3 link ({expires_h}h geçerli):\n   {presigned_url}")
        else:
            print("⚠️  S3 upload mevcut değil — dosya sadece bellekte.")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_caption(self, base: str, filename: str, presigned_url: str) -> str:
        parts = [base] if base else []
        if presigned_url:
            expires_h = self._expiry // 3600
            parts.append(
                f'\n🔗 <a href="{presigned_url}">S3\'den indir</a> '
                f"<i>({expires_h}h geçerli)</i>"
            )
        return "\n".join(parts)


# ── singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[FileDeliveryService] = None


def get_file_delivery_service() -> FileDeliveryService:
    """Return the singleton FileDeliveryService."""
    global _instance
    if _instance is None:
        _instance = FileDeliveryService()
    return _instance
