"""
Auto-Reframe Engine using MediaPipe Face Detection.
Tracks face coordinates in video segments and generates dynamic FFmpeg crop expressions.
"""

import cv2
import numpy as np
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
except ImportError:
    mp = None


class AutoReframeEngine:
    def __init__(self, step_frames: int = 10, pan_duration: float = 0.5):
        """
        Initialize the Auto-Reframe Engine.

        Args:
            step_frames: Process 1 frame every N frames (improves CPU performance).
            pan_duration: Transition duration (in seconds) for camera pans.
        """
        self.step_frames = step_frames
        self.pan_duration = pan_duration

    def analyze_video_faces(self, video_path: Path) -> Optional[List[Tuple[float, float]]]:
        """
        Analyze a video clip to track face X coordinates over time.

        Args:
            video_path: Path to the input video clip.

        Returns:
            List of (timestamp_seconds, normalized_face_x) tuples, or None if tracking fails.
        """
        if mp is None:
            logger.warning("MediaPipe is not installed. Auto-reframe will fallback to static crop.")
            return None

        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error(f"Could not open video file: {video_path}")
            return None

        width = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total_frames <= 0 or width <= 0 or height <= 0:
            logger.error(f"Invalid video metadata: {video_path}")
            cap.release()
            return None

        # Initialize MediaPipe Face Detection
        mp_face_detection = mp.solutions.face_detection
        face_detection = mp_face_detection.FaceDetection(
            model_selection=1,  # 1 for full range (within 5m), 0 for short range (within 2m)
            min_detection_confidence=0.5
        )

        detections = []
        frame_idx = 0

        logger.info(f"Analyzing faces in {video_path.name} ({total_frames} frames)...")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Sub-sample frames to optimize CPU usage
            if frame_idx % self.step_frames == 0:
                timestamp = frame_idx / fps
                
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_detection.process(rgb_frame)

                face_x = 0.5  # Fallback to center
                
                if results.detections:
                    # If multiple faces detected, find the largest one (likely the active speaker)
                    largest_face = None
                    largest_area = 0.0
                    
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        area = bbox.width * bbox.height
                        if area > largest_area:
                            largest_area = area
                            largest_face = detection
                    
                    if largest_face:
                        bbox = largest_face.location_data.relative_bounding_box
                        # Center X of the face bounding box
                        face_x = bbox.xmin + bbox.width / 2.0
                        
                detections.append((timestamp, face_x))

            frame_idx += 1

        cap.release()
        face_detection.close()

        logger.info(f"Analyzed {len(detections)} frames for face tracking.")
        return detections

    def smooth_coordinates(self, detections: List[Tuple[float, float]], window_size: int = 5) -> List[Tuple[float, float]]:
        """
        Apply a moving average filter to smooth coordinates and prevent camera jitter.

        Args:
            detections: List of (timestamp, x) tuples.
            window_size: Moving average window size.

        Returns:
            Smoothed list of (timestamp, x) tuples.
        """
        if not detections:
            return []

        timestamps = [d[0] for d in detections]
        coords = [d[1] for d in detections]

        smoothed_coords = []
        n = len(coords)

        for i in range(n):
            # Calculate dynamic window indices
            start_idx = max(0, i - window_size // 2)
            end_idx = min(n, i + window_size // 2 + 1)
            
            # Compute average of coordinates in the window
            avg_x = sum(coords[start_idx:end_idx]) / (end_idx - start_idx)
            smoothed_coords.append((timestamps[i], avg_x))

        return smoothed_coords

    def generate_ffmpeg_crop_expression(
        self, 
        detections: List[Tuple[float, float]], 
        video_w: float, 
        video_h: float
    ) -> Optional[str]:
        """
        Generates a dynamic crop filter expression for FFmpeg based on face coordinates.
        Target resolution is 9:16 relative to video height (e.g., 1080x1920 aspect ratio crop).

        Args:
            detections: List of (timestamp, normalized_x) tuples.
            video_w: Width of original video.
            video_h: Height of original video.

        Returns:
            FFmpeg crop expression string, or None if fails.
        """
        if not detections:
            return None

        # Smooth coordinates
        smoothed = self.smooth_coordinates(detections)

        # Target crop width is (video_h * 9/16)
        crop_w = int(video_h * 9.0 / 16.0)
        # Ensure crop width is even
        if crop_w % 2 != 0:
            crop_w += 1

        # Max crop X coordinate to stay inside boundaries
        max_crop_x = video_w - crop_w
        
        # Map normalized face X to actual crop X coordinate (clamped)
        points = []
        for t, x_norm in smoothed:
            face_x_pixels = x_norm * video_w
            target_crop_x = face_x_pixels - crop_w / 2.0
            # Clamp to prevent crop box from going off-screen
            clamped_x = max(0.0, min(max_crop_x, target_crop_x))
            points.append((t, clamped_x))

        # Build recursive conditional expression for FFmpeg
        # Formula: if(lt(t, t1), interp(t0, t1, x0, x1), if(lt(t, t2), interp(t1, t2, x1, x2), ...))
        
        def build_expr(idx: int) -> str:
            if idx >= len(points) - 1:
                return f"{points[-1][1]:.1f}"

            t0, x0 = points[idx]
            t1, x1 = points[idx + 1]
            
            # Detect sharp camera cut/jump (e.g., if X position jumps by more than 15% of width)
            # If so, do an instant cut instead of a smooth pan
            is_cut = abs(x1 - x0) > (video_w * 0.15)
            
            if is_cut:
                # Instant jump at the middle of the interval
                t_mid = (t0 + t1) / 2.0
                return f"if(lt(t, {t_mid:.2f}), {x0:.1f}, {build_expr(idx + 1)})"
            else:
                # Smooth pan (linear interpolation) between points
                dur = t1 - t0
                if dur <= 0:
                    return build_expr(idx + 1)
                
                # Pan expression: x0 + (t - t0) * (x1 - x0) / dur
                slope = (x1 - x0) / dur
                expr = f"({x0:.1f} + (t - {t0:.2f}) * {slope:.3f})"
                
                return f"if(lt(t, {t1:.2f}), {expr}, {build_expr(idx + 1)})"

        crop_x_expression = build_expr(0)
        
        # Combine into crop filter: crop=w:h:x:y
        crop_y = f"(in_h-out_h)/2"
        crop_filter = f"crop={crop_w}:{int(video_h)}:{crop_x_expression}:{crop_y}"
        
        return crop_filter
