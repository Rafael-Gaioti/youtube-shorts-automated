from scripts.utils import supabase_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup")


def archive_irrelevant():
    client = supabase_client.get_supabase_client()
    if not client:
        logger.error("Supabase not available")
        return

    # Get all videos in pre-analysis stages
    videos = []
    for stage in ["discovered", "downloaded", "transcribed"]:
        videos.extend(supabase_client.get_videos_by_stage(stage))

    keywords = [
        "produtividade",
        "hábito",
        "rotina",
        "foco",
        "disciplina",
        "sono",
        "performance",
        "tempo",
    ]

    archived_count = 0
    for video in videos:
        title = video.get("title", "").lower()
        is_relevant = any(kw in title for kw in keywords)

        if not is_relevant:
            logger.info(
                f"Marking irrelevant video as failed (Off-niche): {video['title']}"
            )
            supabase_client.update_video_stage(
                video["video_code"], "failed", "REJECTED_BY_NICHE_FILTER"
            )
            archived_count += 1

    logger.info(f"Cleanup complete. {archived_count} videos archived.")


if __name__ == "__main__":
    archive_irrelevant()
