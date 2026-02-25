import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add scripts/utils to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from scripts.utils.supabase_client import get_supabase_client


def identify_unnecessary_videos():
    load_dotenv()
    client = get_supabase_client()
    if not client:
        print("Error: Could not initialize Supabase client.")
        return

    # 1. Get all video_codes from Supabase
    try:
        res = client.table("videos").select("video_code, stage").execute()
        db_videos = {
            v["video_code"]: v["stage"]
            for v in (res[1] if isinstance(res, tuple) else res.data)
        }
    except Exception as e:
        print(f"Error querying Supabase: {e}")
        return

    # 2. Get all files in data/raw
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        print(f"Error: {raw_dir} does not exist.")
        return

    raw_files = list(raw_dir.glob("*.mp4"))

    orphaned_files = []
    finished_files = []
    active_files = []

    for file_path in raw_files:
        video_code = file_path.stem

        if video_code not in db_videos:
            orphaned_files.append(file_path)
        else:
            stage = db_videos[video_code]
            if stage in ["exported", "uploaded"]:
                finished_files.append((file_path, stage))
            else:
                active_files.append((file_path, stage))

    print("\n--- RESULTS ---")
    print(f"Total raw files: {len(raw_files)}")
    print(f"Active files (keep): {len(active_files)}")

    print(f"\nOrphaned files (suggest DELETE - {len(orphaned_files)}):")
    for f in orphaned_files:
        print(f"- {f.name}")

    print(
        f"\nFinished files (suggest ARCHIVE/DELETE if space needed - {len(finished_files)}):"
    )
    for f, stage in finished_files:
        print(f"- {f.name} (Stage: {stage})")


if __name__ == "__main__":
    identify_unnecessary_videos()
