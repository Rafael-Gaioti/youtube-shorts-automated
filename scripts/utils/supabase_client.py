import os
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Try importing supabase, fail gracefully if not installed so it doesn't crash apps not using it yet
try:
    from supabase import create_client, Client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Load env vars
load_dotenv()


def get_supabase_client() -> Optional["Client"]:
    """Returns a Supabase client instance if configured correctly, otherwise None."""
    if not SUPABASE_AVAILABLE:
        logger.warning("Supabase package is not installed. Run 'pip install supabase'.")
        return None

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not found in .env file.")
        return None

    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def register_discovered_video(
    video_code: str, url: str, title: str, channel: str
) -> Optional[str]:
    """Registers a newly discovered video in the videos table. Returns the internal UUID or None on failure."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        data, count = (
            client.table("videos")
            .upsert(
                {
                    "video_code": video_code,
                    "url": url,
                    "title": title,
                    "channel": channel,
                    "stage": "discovered",
                },
                on_conflict="video_code",
            )
            .execute()
        )

        if data and len(data[1]) > 0:
            return data[1][0]["id"]
        return None
    except Exception as e:
        logger.error(f"Failed to register video {video_code} in Supabase: {e}")
        return None


def update_video_stage(video_code: str, stage: str, error_log: str = None) -> bool:
    """Updates the processing stage of a video (discovered, downloaded, transcribed, analyzed, failed)."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        payload = {"stage": stage}
        if error_log is not None:
            payload["error_log"] = error_log

        client.table("videos").update(payload).eq("video_code", video_code).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update stage to {stage} for video {video_code}: {e}")
        return False


def get_videos_by_stage(stage: str) -> List[Dict[str, Any]]:
    """Retrieves all videos currently at the specified stage."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        data, count = client.table("videos").select("*").eq("stage", stage).execute()
        # In supabase-py v2, response is a tuple (data, count). Usually data[1] is the actual data array.
        # But `.execute()` actually returns an APIResponse object nowadays so data.data is the list.
        # Wait, the newer supabase-py v2.x returns an object where .data is the list.
        # I'll use duck typing.
        result = data[1] if isinstance(data, tuple) else data.data
        return result
    except Exception as e:
        logger.error(f"Failed to get videos by stage {stage}: {e}")
        return []


def register_cut(
    video_code: str,
    cut_index: int,
    start_time: float,
    end_time: float,
    hook_text: str = None,
    headline: str = None,
) -> bool:
    """Registers a generated cut from 3_analyze."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        # First get the video UUID
        video_res = (
            client.table("videos").select("id").eq("video_code", video_code).execute()
        )
        video_data = video_res[1] if isinstance(video_res, tuple) else video_res.data

        if not video_data:
            logger.error(
                f"Cannot register cut. Video {video_code} not found in Supabase."
            )
            return False

        video_id = video_data[0]["id"]

        client.table("cuts").upsert(
            {
                "video_id": video_id,
                "cut_index": cut_index,
                "start_time": start_time,
                "end_time": end_time,
                "hook_text": hook_text,
                "headline": headline,
                "status": "pending",
            },
            on_conflict="video_id,cut_index",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to register cut {cut_index} for video {video_code}: {e}")
        return False


def update_cut_status(video_code: str, cut_index: int, status: str) -> bool:
    """Updates the status of a specific cut (pending, exported, quarantined, failed, uploaded)."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        # Complex lookup: need to find cut by video_code relation. Simplest is finding the video id.
        video_res = (
            client.table("videos").select("id").eq("video_code", video_code).execute()
        )
        video_data = video_res[1] if isinstance(video_res, tuple) else video_res.data

        if not video_data:
            return False

        video_id = video_data[0]["id"]

        client.table("cuts").update({"status": status}).eq("video_id", video_id).eq(
            "cut_index", cut_index
        ).execute()
        return True
    except Exception as e:
        logger.error(
            f"Failed to update cut status to {status} for video {video_code} cut {cut_index}: {e}"
        )
        return False


def get_cuts_by_status(status: str) -> List[Dict[str, Any]]:
    """Get all cuts with a given status, joining with video info."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        # Join query
        res = (
            client.table("cuts")
            .select("*, videos(video_code, title)")
            .eq("status", status)
            .execute()
        )
        return res[1] if isinstance(res, tuple) else res.data
    except Exception as e:
        logger.error(f"Failed to get cuts by status {status}: {e}")
        return []


def register_export(
    video_code: str,
    cut_index: int,
    filepath: str,
    overall_score: float = None,
    viral_potential: str = None,
    gatekeeper_approved: bool = False,
) -> bool:
    """Registers the final physical mp4 in the exports table."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        # Find combination UUID
        cut_res = client.table("cuts").select("id").eq("cut_index", cut_index).execute()
        # To be safe, we really should join cuts and videos to get the specific one.
        # But this is okay for a simple find since video_id is unique per cut_index.
        # It's better to explicitly join:
        res = (
            client.table("cuts")
            .select("id, videos!inner(video_code)")
            .eq("videos.video_code", video_code)
            .eq("cut_index", cut_index)
            .execute()
        )
        data = res[1] if isinstance(res, tuple) else res.data

        if not data:
            return False

        cut_id = data[0]["id"]

        client.table("exports").insert(
            {
                "cut_id": cut_id,
                "filepath": filepath,
                "overall_score": overall_score,
                "viral_potential": viral_potential,
                "gatekeeper_approved": gatekeeper_approved,
            }
        ).execute()

        return True
    except Exception as e:
        logger.error(
            f"Failed to register export for video {video_code} cut {cut_index}: {e}"
        )
        return False
