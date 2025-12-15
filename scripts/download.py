import subprocess
import sys
from pathlib import Path

URL = sys.argv[1]

output_dir = Path("data/raw")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "fonte.mp4"

cmd = [
    "yt-dlp",
    "-f", "bestvideo+bestaudio",
    "-o", str(output_file),
    URL
]

subprocess.run(cmd, check=True)