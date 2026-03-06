"""
Screenshot Storage for Browser Missions

Manages storage of browser screenshots for missions, supporting:
- Local filesystem storage
- S3 upload for persistent cloud storage
- Metadata tracking
- Expiration/cleanup policies

Author: octopOS Team
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
import mimetypes

import boto3
from botocore.exceptions import ClientError

from ...utils.config import OctoConfig
from ...utils.logger import get_logger

logger = get_logger()


@dataclass
class ScreenshotMetadata:
    """Metadata for a stored screenshot."""
    screenshot_id: str
    mission_id: str
    step_number: int
    url: str
    timestamp: datetime
    local_path: Optional[str] = None
    s3_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    s3_url: Optional[str] = None
    width: int = 1920
    height: int = 1080
    file_size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "screenshot_id": self.screenshot_id,
            "mission_id": self.mission_id,
            "step_number": self.step_number,
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "local_path": self.local_path,
            "s3_key": self.s3_key,
            "s3_bucket": self.s3_bucket,
            "s3_url": self.s3_url,
            "dimensions": {"width": self.width, "height": self.height},
            "file_size_bytes": self.file_size_bytes,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScreenshotMetadata':
        """Create from dictionary."""
        return cls(
            screenshot_id=data["screenshot_id"],
            mission_id=data["mission_id"],
            step_number=data.get("step_number", 0),
            url=data.get("url", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now()),
            local_path=data.get("local_path"),
            s3_key=data.get("s3_key"),
            s3_bucket=data.get("s3_bucket"),
            s3_url=data.get("s3_url"),
            width=data.get("dimensions", {}).get("width", 1920),
            height=data.get("dimensions", {}).get("height", 1080),
            file_size_bytes=data.get("file_size_bytes", 0),
            metadata=data.get("metadata", {})
        )


class ScreenshotStorage:
    """
    Manages screenshot storage for browser missions.
    
    Supports both local filesystem and S3 backends with automatic
    upload to cloud for persistence.
    """
    
    def __init__(
        self,
        local_base_dir: str = "~/.octopos/screenshots",
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "screenshots/missions/",
        enable_s3: bool = False,
        config: Optional[OctoConfig] = None
    ):
        """
        Initialize screenshot storage.
        
        Args:
            local_base_dir: Base directory for local screenshot storage
            s3_bucket: S3 bucket name for cloud storage
            s3_prefix: Prefix path in S3 bucket
            enable_s3: Whether to enable S3 upload
            config: OctoConfig instance
        """
        self.local_base_dir = Path(local_base_dir).expanduser()
        self.local_base_dir.mkdir(parents=True, exist_ok=True)
        
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.enable_s3 = enable_s3 and s3_bucket is not None
        self.config = config or OctoConfig()
        
        # S3 client (initialized lazily)
        self._s3_client: Optional[Any] = None
        
        # In-memory index of stored screenshots
        self._screenshots: Dict[str, ScreenshotMetadata] = {}
        
        # Metadata storage path
        self._metadata_path = self.local_base_dir / "index.json"
        
        # Load existing index
        self._load_index()
        
        logger.info(f"ScreenshotStorage initialized: local={self.local_base_dir}, s3={self.enable_s3}")
    
    def _get_s3_client(self) -> Any:
        """Get or create S3 client."""
        if self._s3_client is None and self.enable_s3:
            self._s3_client = boto3.client("s3")
        return self._s3_client
    
    def _load_index(self):
        """Load screenshot index from disk."""
        if self._metadata_path.exists():
            try:
                with open(self._metadata_path, "r") as f:
                    data = json.load(f)
                    for screenshot_id, screenshot_data in data.items():
                        self._screenshots[screenshot_id] = ScreenshotMetadata.from_dict(screenshot_data)
                logger.info(f"Loaded {len(self._screenshots)} screenshots from index")
            except Exception as e:
                logger.warning(f"Failed to load screenshot index: {e}")
    
    def _save_index(self):
        """Save screenshot index to disk."""
        try:
            data = {sid: meta.to_dict() for sid, meta in self._screenshots.items()}
            with open(self._metadata_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save screenshot index: {e}")
    
    async def store_screenshot(
        self,
        mission_id: str,
        step_number: int,
        local_path: str,
        url: str = "",
        upload_to_s3: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ScreenshotMetadata:
        """
        Store a screenshot and optionally upload to S3.
        
        Args:
            mission_id: Associated mission ID
            step_number: Step number in the mission
            local_path: Path to the screenshot file
            url: URL of the page when screenshot was taken
            upload_to_s3: Whether to upload to S3
            metadata: Additional metadata
            
        Returns:
            ScreenshotMetadata with storage details
        """
        screenshot_id = f"{mission_id}_{step_number}_{uuid4().hex[:8]}"
        
        local_path_obj = Path(local_path)
        if not local_path_obj.exists():
            raise FileNotFoundError(f"Screenshot not found: {local_path}")
        
        # Get file info
        stat = local_path_obj.stat()
        file_size = stat.st_size
        
        # Try to get image dimensions
        width, height = 1920, 1080
        try:
            from PIL import Image
            with Image.open(local_path) as img:
                width, height = img.size
        except ImportError:
            pass  # PIL not available
        except Exception:
            pass  # Could not read image
        
        # Create metadata
        screenshot_meta = ScreenshotMetadata(
            screenshot_id=screenshot_id,
            mission_id=mission_id,
            step_number=step_number,
            url=url,
            timestamp=datetime.now(),
            local_path=str(local_path_obj.absolute()),
            width=width,
            height=height,
            file_size_bytes=file_size,
            metadata=metadata or {}
        )
        
        # Upload to S3 if enabled
        if upload_to_s3 and self.enable_s3:
            await self._upload_to_s3(screenshot_meta, local_path)
        
        # Store in index
        self._screenshots[screenshot_id] = screenshot_meta
        self._save_index()
        
        logger.info(f"Stored screenshot {screenshot_id}: {local_path}")
        
        return screenshot_meta
    
    async def _upload_to_s3(self, meta: ScreenshotMetadata, local_path: str):
        """Upload screenshot to S3."""
        try:
            s3_client = self._get_s3_client()
            if not s3_client:
                return
            
            s3_key = f"{self.s3_prefix}{meta.mission_id}/{meta.screenshot_id}.png"
            
            # Upload with metadata
            extra_args = {
                "ContentType": "image/png",
                "Metadata": {
                    "mission_id": meta.mission_id,
                    "step_number": str(meta.step_number),
                    "url": meta.url,
                    "timestamp": meta.timestamp.isoformat()
                }
            }
            
            s3_client.upload_file(local_path, self.s3_bucket, s3_key, ExtraArgs=extra_args)
            
            # Update metadata
            meta.s3_key = s3_key
            meta.s3_bucket = self.s3_bucket
            meta.s3_url = f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}"
            
            logger.info(f"Uploaded screenshot to S3: {s3_key}")
            
        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
        except Exception as e:
            logger.error(f"S3 upload error: {e}")
    
    def get_screenshot(self, screenshot_id: str) -> Optional[ScreenshotMetadata]:
        """Get screenshot metadata by ID."""
        return self._screenshots.get(screenshot_id)
    
    def get_mission_screenshots(self, mission_id: str) -> List[ScreenshotMetadata]:
        """Get all screenshots for a mission."""
        return [
            meta for meta in self._screenshots.values()
            if meta.mission_id == mission_id
        ]
    
    def get_screenshot_data(self, screenshot_id: str) -> Optional[bytes]:
        """Get raw screenshot data."""
        meta = self._screenshots.get(screenshot_id)
        if not meta or not meta.local_path:
            return None
        
        try:
            with open(meta.local_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read screenshot {screenshot_id}: {e}")
            return None
    
    async def delete_screenshot(self, screenshot_id: str, delete_from_s3: bool = True) -> bool:
        """
        Delete a screenshot.
        
        Args:
            screenshot_id: Screenshot to delete
            delete_from_s3: Also delete from S3 if present
            
        Returns:
            True if deleted successfully
        """
        meta = self._screenshots.get(screenshot_id)
        if not meta:
            return False
        
        try:
            # Delete local file
            if meta.local_path and Path(meta.local_path).exists():
                Path(meta.local_path).unlink()
            
            # Delete from S3
            if delete_from_s3 and meta.s3_key and self.enable_s3:
                try:
                    s3_client = self._get_s3_client()
                    if s3_client:
                        s3_client.delete_object(
                            Bucket=meta.s3_bucket,
                            Key=meta.s3_key
                        )
                except ClientError as e:
                    logger.warning(f"Failed to delete from S3: {e}")
            
            # Remove from index
            del self._screenshots[screenshot_id]
            self._save_index()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete screenshot {screenshot_id}: {e}")
            return False
    
    async def cleanup_old_screenshots(self, max_age_days: int = 30):
        """
        Clean up screenshots older than specified age.
        
        Args:
            max_age_days: Maximum age in days
        """
        cutoff = datetime.now() - timedelta(days=max_age_days)
        to_delete = [
            sid for sid, meta in self._screenshots.items()
            if meta.timestamp < cutoff
        ]
        
        deleted_count = 0
        for sid in to_delete:
            if await self.delete_screenshot(sid):
                deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} old screenshots")
        return deleted_count
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        total_size = sum(meta.file_size_bytes for meta in self._screenshots.values())
        s3_count = sum(1 for meta in self._screenshots.values() if meta.s3_url)
        
        return {
            "total_screenshots": len(self._screenshots),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "s3_uploaded": s3_count,
            "local_only": len(self._screenshots) - s3_count,
            "missions": len(set(meta.mission_id for meta in self._screenshots.values()))
        }
    
    async def generate_mission_gallery(
        self,
        mission_id: str,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate an HTML gallery of mission screenshots.
        
        Args:
            mission_id: Mission to create gallery for
            output_path: Path to save HTML file (optional)
            
        Returns:
            Path to generated HTML file
        """
        screenshots = self.get_mission_screenshots(mission_id)
        if not screenshots:
            return None
        
        # Sort by step number
        screenshots.sort(key=lambda x: x.step_number)
        
        # Generate HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            f"<title>Mission {mission_id} - Screenshot Gallery</title>",
            "<style>",
            "body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }",
            ".gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 20px; }",
            ".screenshot { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
            ".screenshot img { width: 100%; height: auto; display: block; }",
            ".screenshot-info { padding: 15px; }",
            ".step-number { font-size: 24px; font-weight: bold; color: #333; }",
            ".url { color: #666; font-size: 12px; word-break: break-all; }",
            ".timestamp { color: #999; font-size: 12px; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>Mission: {mission_id}</h1>",
            f"<p>Total Screenshots: {len(screenshots)}</p>",
            "<div class='gallery'>"
        ]
        
        for meta in screenshots:
            html_parts.extend([
                "<div class='screenshot'>",
                f"<img src='file://{meta.local_path}' alt='Step {meta.step_number}'>" if meta.local_path else "<p>No image</p>",
                "<div class='screenshot-info'>",
                f"<div class='step-number'>Step {meta.step_number}</div>",
                f"<div class='url'>{meta.url}</div>",
                f"<div class='timestamp'>{meta.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</div>",
                "</div>",
                "</div>"
            ])
        
        html_parts.extend([
            "</div>",
            "</body>",
            "</html>"
        ])
        
        # Save HTML
        if not output_path:
            output_path = str(self.local_base_dir / f"{mission_id}_gallery.html")
        
        with open(output_path, "w") as f:
            f.write("\n".join(html_parts))
        
        return output_path


# Global instance
_global_storage: Optional[ScreenshotStorage] = None


def get_screenshot_storage(
    local_base_dir: str = "~/.octopos/screenshots",
    enable_s3: bool = False,
    config: Optional[OctoConfig] = None
) -> ScreenshotStorage:
    """Get or create global screenshot storage instance."""
    global _global_storage
    if _global_storage is None:
        cfg = config or OctoConfig()
        s3_bucket = cfg.aws.s3_bucket_name if enable_s3 else None
        _global_storage = ScreenshotStorage(
            local_base_dir=local_base_dir,
            s3_bucket=s3_bucket,
            enable_s3=enable_s3,
            config=cfg
        )
    return _global_storage
