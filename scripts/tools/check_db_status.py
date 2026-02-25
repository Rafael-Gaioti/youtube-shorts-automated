from scripts.utils import supabase_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("check_db")


def check_active_videos():
    client = supabase_client.get_supabase_client()
    if not client:
        print("Supabase not available")
        return

    stages = [
        "discovered",
        "downloaded",
        "transcribed",
        "analyzed",
        "exported",
        "uploaded",
        "failed",
        "archived",
    ]
    for stage in stages:
        videos = supabase_client.get_videos_by_stage(stage)
        print(f"Stage '{stage}': {len(videos)} videos")
        if videos and stage != "failed" and stage != "archived":
            for v in videos[:3]:
                print(f"  - {v['title']} ({v['video_code']})")


if __name__ == "__main__":
    check_active_videos()
