"""
7_metrics.py — Coleta automática de métricas do YouTube via Supabase

Uso:
    python scripts/7_metrics.py

Este script:
1. Busca vídeos com status 'uploaded' no Supabase.
2. Consulta YouTube Data API v3 (Views, Likes, Comments).
3. Consulta YouTube Analytics API (Retenção).
4. Atualiza os registros na tabela 'exports'.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Google API
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print(
        "❌ Dependências do Google não instaladas.\n"
        "   Execute: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
    )
    sys.exit(1)

# Project Utils
sys.path.append(os.getcwd())
from scripts.utils import supabase_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("METRICS")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CLIENT_SECRETS_PATH = Path("client_secrets.json")
TOKEN_PATH = Path("config/youtube_token.json")


def _find_client_secrets() -> Path | None:
    if CLIENT_SECRETS_PATH.exists():
        return CLIENT_SECRETS_PATH
    candidates = list(Path(".").glob("client_secret_*.json"))
    if candidates:
        return candidates[0]
    return None


def get_authenticated_services():
    creds = None
    secrets_path = _find_client_secrets()
    if not secrets_path:
        logger.error("❌ client_secrets.json não encontrado.")
        sys.exit(1)

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    youtube_service = build("youtube", "v3", credentials=creds)
    analytics_service = build("youtubeAnalytics", "v2", credentials=creds)
    return youtube_service, analytics_service


def fetch_basic_stats(youtube, video_ids: list[str]) -> dict:
    stats = {}
    if not video_ids:
        return stats

    chunk_size = 50
    for i in range(0, len(video_ids), chunk_size):
        chunk = video_ids[i : i + chunk_size]
        try:
            request = youtube.videos().list(part="statistics", id=",".join(chunk))
            response = request.execute()
            for item in response.get("items", []):
                vid = item["id"]
                s = item.get("statistics", {})
                stats[vid] = {
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                }
        except HttpError as e:
            logger.error(f"Erro basic stats: {e}")
    return stats


def fetch_retention_stats(analytics, video_id: str) -> dict:
    stats = {"averageViewDuration": None, "averageViewPercentage": None}
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        request = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="averageViewDuration,averageViewPercentage",
            filters=f"video=={video_id}",
        )
        response = request.execute()
        if "rows" in response and response["rows"]:
            row = response["rows"][0]
            stats["averageViewDuration"] = float(row[0])
            stats["averageViewPercentage"] = float(row[1])
    except HttpError:
        pass  # Silencioso para delay do YouTube (24h)
    return stats


def main():
    logger.info("🔍 Iniciando sincronização de métricas via Supabase...")

    # 1. Buscar vídeos do Banco
    exports = supabase_client.get_uploaded_exports()
    if not exports:
        logger.info("Nenhum vídeo com 'youtube_video_id' encontrado no banco.")
        return

    # 2. Autenticar Google
    youtube, analytics = get_authenticated_services()

    # 3. Mapear IDs para busca em lote
    yt_ids = [e["youtube_video_id"] for e in exports if e["youtube_video_id"]]
    basic_stats = fetch_basic_stats(youtube, yt_ids)

    total_updated = 0
    for exp in exports:
        vid = exp["youtube_video_id"]
        exp_id = exp["id"]

        if vid not in basic_stats:
            continue

        b = basic_stats[vid]

        # Só buscar analytics se tiver views
        r = {"averageViewDuration": None, "averageViewPercentage": None}
        if b["views"] > 0:
            r = fetch_retention_stats(analytics, vid)

        success = supabase_client.update_export_metrics(
            export_id=exp_id,
            views=b["views"],
            likes=b["likes"],
            comments=b["comments"],
            avg_duration=r["averageViewDuration"],
            avg_percentage=r["averageViewPercentage"],
        )

        if success:
            logger.info(
                f"✅ [{vid}] Views: {b['views']} | Retenção: {r['averageViewPercentage']}%"
            )
            total_updated += 1

    logger.info(f"🚀 Fim da sincronização. {total_updated} registros atualizados.")


if __name__ == "__main__":
    main()
