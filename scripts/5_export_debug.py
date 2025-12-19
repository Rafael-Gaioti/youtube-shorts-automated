import os
import json
import subprocess
from pathlib import Path

# Paths for testing
CUT_FILE = Path("data/output/ff88SpBpkD0_cut_01.mp4")
ANALYSIS_FILE = Path("data/analysis/ff88SpBpkD0_analysis.json")
OUTPUT_FILE = Path("data/shorts/debug_test.mp4")


def debug_export():
    if not CUT_FILE.exists():
        print(f"Error: Cut file not found: {CUT_FILE}")
        return

    # Mock settings
    video_cfg = {
        "video_codec": "libx264",
        "preset": "veryfast",
        "crf": 23,
        "video_bitrate": "5000k",
        "fps": 30,
        "audio_codec": "aac",
        "audio_bitrate": "192k",
    }

    # Filters
    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "ass=temp_captions_0.ass",
        "drawtext=text='VAMOS FALAR DE CARREIRA':x=(w-text_w)/2:y=200:fontcolor=white:fontsize=70:box=1:boxcolor=black@0.7:boxborderw=30",
    ]

    # Command
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(CUT_FILE.absolute()),
        "-vf",
        ",".join(filters),
        "-c:v",
        video_cfg["video_codec"],
        "-preset",
        video_cfg["preset"],
        "-crf",
        str(video_cfg["crf"]),
        "-b:v",
        video_cfg["video_bitrate"],
        "-r",
        str(video_cfg["fps"]),
        "-c:a",
        video_cfg["audio_codec"],
        "-b:a",
        video_cfg["audio_bitrate"],
        "-movflags",
        "+faststart",
        str(OUTPUT_FILE.absolute()),
    ]

    print(f"Running command: {' '.join(cmd)}")

    try:
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode == 0:
            print("Success!")
        else:
            print(f"Failed with return code {process.returncode}")
            print(f"STDOUT: {process.stdout}")
            print(f"STDERR: {process.stderr}")
    except Exception as e:
        print(f"Subprocess error: {e}")


if __name__ == "__main__":
    debug_export()
