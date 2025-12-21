import cv2
import numpy as np
import os
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_video_for_subtitles(video_path, sample_count=10):
    """
    Checks if a video has burned-in subtitles by sampling frames.
    Returns: (bool has_subtitles, float confidence)
    """
    if not os.path.exists(video_path):
        logger.error(f"Video not found: {video_path}")
        return False, 0.0

    # Get video duration using ffprobe
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        duration = float(subprocess.check_output(cmd).decode().strip())
    except Exception as e:
        logger.error(f"Error getting duration: {e}")
        return False, 0.0

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Could not open video file.")
        return False, 0.0

    hits = 0
    densities = []

    # Sample frames every 10%
    for i in range(1, sample_count):
        t = (duration / sample_count) * i
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w, _ = frame.shape
        # Subtitles are usually in the bottom 25%
        crop = frame[int(h * 0.75) : int(h * 0.95), :, :]

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # High-pass filter (Laplacian) to find sharp text edges
        laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Canny edge density
        edges = cv2.Canny(gray, 100, 200)
        density = np.count_nonzero(edges) / edges.size
        densities.append(density)

        # Heuristic: Density > 0.015 AND Laplacian variance > 100 (text is sharp)
        if density > 0.015 and laplacian > 100:
            hits += 1
            logger.info(
                f"Potential subtitles at {t:.2f}s (Density: {density:.4f}, Lap: {laplacian:.1f})"
            )

    cap.release()

    confidence = hits / (sample_count - 1)
    has_subs = confidence >= 0.3  # If 30% of frames have text patterns

    return has_subs, confidence


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detect_burned_subs.py <video_path>")
        sys.exit(1)

    has_subs, conf = check_video_for_subtitles(sys.argv[1])
    print(f"HAS_SUBTITLES: {has_subs}")
    print(f"CONFIDENCE: {conf:.2f}")
