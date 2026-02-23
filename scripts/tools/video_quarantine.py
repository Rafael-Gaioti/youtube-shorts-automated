import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def quarantine_video(video_path: Path, reason: str = "audit_failure"):
    """
    Moves a video and its associated assets to the quarantine folder.
    """
    try:
        # Define quarantine base dir
        quarantine_base = video_path.parent / "quarantine"
        quarantine_base.mkdir(parents=True, exist_ok=True)

        # Create a timestamped subfolder for this specific failure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{timestamp}_{video_path.stem}"
        target_dir = quarantine_base / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        # Save the reason
        with open(target_dir / "quarantine_reason.txt", "w", encoding="utf-8") as f:
            f.write(f"Reason: {reason}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Original Path: {video_path}\n")

        # Move the video
        if video_path.exists():
            shutil.move(str(video_path), str(target_dir / video_path.name))
            logger.info(f"Video quarantined: {video_path.name} -> {target_dir}")

        # Search for associated assets (thumbnails, subtitles with same stem)
        for asset in video_path.parent.glob(f"{video_path.stem}*"):
            if asset.is_file() and asset != video_path:
                shutil.move(str(asset), str(target_dir / asset.name))
                logger.info(f"Asset quarantined: {asset.name}")

        return target_dir
    except Exception as e:
        logger.error(f"Failed to quarantine video {video_path}: {e}")
        return None
