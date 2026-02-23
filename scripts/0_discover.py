import os
import json
import sqlite3
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Configuração de Logging
import argparse
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils.settings_manager import settings_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


from scripts.utils import supabase_client


class VideoDiscoverer:
    def __init__(self):
        # We no longer use local SQLite; using Supabase Postgres instead.
        pass

    def is_processed(self, video_id: str) -> bool:
        """Verifica se o vídeo já foi descoberto no Supabase."""

        # A simple check: if the video exists in the videos table, it's processed
        if not supabase_client.SUPABASE_AVAILABLE:
            logger.warning("Supabase não disponível. Histórico não será checado.")
            return False

        client = supabase_client.get_supabase_client()
        if not client:
            return False

        try:
            res = (
                client.table("videos").select("id").eq("video_code", video_id).execute()
            )
            data = res[1] if isinstance(res, tuple) else res.data
            return len(data) > 0
        except Exception as e:
            logger.error(f"Erro ao checar processed no Supabase: {e}")
            return False

    def mark_discovered(self, video_id: str, title: str, channel: str):
        """Registra no banco Supabase que um vídeo foi descoberto."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        supabase_client.register_discovered_video(video_id, url, title, channel)

    def fetch_top_videos(
        self,
        channel_url: str,
        days: int = 90,
        limit: int = 50,
        discovery_rules: dict = None,
    ) -> List[Dict[str, Any]]:
        """
        Usa yt-dlp para listar videos de um canal e filtrar pelos com maior view_count (ROI).
        """
        discovery_rules = discovery_rules or {}
        logger.info(
            f"Buscando TOP vídeos (ROI) de: {channel_url} nos últimos {days} dias"
        )

        date_after = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # --flat-playlist é rápido mas nem sempre traz o view_count correto no JSON flat.
        # Vamos pegar um número maior de itens da playlist para ter base de comparação.
        # Vamos pegar um número maior de itens da playlist para ter base de comparação.
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--quiet",
            "--no-warnings",
            "--print-json",
            "--flat-playlist",
            "--dateafter",
            date_after,
            "--playlist-end",
            str(limit),
            channel_url,
        ]

        videos = []
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8"
            )
            if result.returncode != 0:
                logger.error(f"Erro ao rodar yt-dlp: {result.stderr}")
                return []

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                video_data = json.loads(line)

                # Ignorar Shorts e vídeos muito longos conforme regras do perfil
                min_dur = discovery_rules.get("min_duration_sec", 300)
                max_dur = discovery_rules.get("max_duration_sec", 1800)

                duration = video_data.get("duration", 0)
                if duration and (duration < min_dur or duration > max_dur):
                    continue

                # Alguns provedores flat não dão view_count.
                # Se não tiver, assume 0 para não quebrar o sort.
                view_count = video_data.get("view_count", 0) or 0

                videos.append(
                    {
                        "id": video_data["id"],
                        "title": video_data["title"],
                        "url": f"https://www.youtube.com/watch?v={video_data['id']}",
                        "view_count": view_count,
                        "channel": video_data.get("channel", "Unknown"),
                        "duration": duration or 0,
                    }
                )

            # Ordenar por views (Maior primeiro) -> ROI Estratégico
            videos.sort(key=lambda x: x["view_count"], reverse=True)

        except Exception as e:
            logger.error(f"Falha na descoberta ROI: {e}")

        return videos

    def get_viral_candidates(
        self,
        channels: List[str],
        max_per_channel: int = 3,
        discovery_rules: dict = None,
    ) -> List[Dict[str, Any]]:
        """Busca os vídeos com melhor performance que ainda não foram processados."""
        candidates = []
        for channel in channels:
            # Busca os 50 mais recentes dos últimos 3 meses para comparar ROI
            all_recent = self.fetch_top_videos(
                channel, days=90, limit=50, discovery_rules=discovery_rules
            )

            channel_picks = 0
            for v in all_recent:
                if self.is_processed(v["id"]):
                    continue

                if channel_picks >= max_per_channel:
                    break

                logger.info(
                    f"🏆 Top ROI encontrado: {v['title']} ({v['view_count']} views)"
                )
                candidates.append(v)
                self.mark_discovered(v["id"], v["title"], v["channel"])
                channel_picks += 1

        return candidates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discovery de vídeos virais.")
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil do usuário (SaaS)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limite total de vídeos a descobrir"
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=None,
        help="Duração máxima em MINUTOS (override)",
    )
    args = parser.parse_args()

    # Configuração de Logs
    # The global logging.basicConfig is already set up.
    # We can just get a logger specific to this script's main execution.
    logger = logging.getLogger("DISCOVER")

    # Carregar Profile
    # settings_manager is already imported as an instance.
    settings = settings_manager.get_settings(args.profile)
    discovery_rules = settings.get("user_profile", {}).get("discovery_rules", {})

    # Override de duração via CLI (útil para testes rápidos)
    if args.max_duration:
        max_duration_sec = args.max_duration * 60
        logger.info(
            f"Override de Duração: Limitando a {args.max_duration} min ({max_duration_sec}s)"
        )
        discovery_rules["max_duration_sec"] = max_duration_sec

    target_channels = [
        "https://www.youtube.com/@PrimoCast/videos",
        "https://www.youtube.com/@FlowPodcast/videos",
    ]

    discoverer = VideoDiscoverer()
    # Pega mais vídeos do que o limite para garantir diversidade, depois aplicamos o limite global
    new_picks = discoverer.get_viral_candidates(
        target_channels, max_per_channel=3, discovery_rules=discovery_rules
    )

    if args.limit:
        new_picks = new_picks[: args.limit]

    if new_picks:
        queue_path = Path("data/discovery_queue.json")
        queue_path.parent.mkdir(parents=True, exist_ok=True)

        current_queue = []
        if queue_path.exists():
            try:
                current_queue = json.loads(queue_path.read_text(encoding="utf-8"))
            except:
                current_queue = []

        current_queue.extend(new_picks)
        queue_path.write_text(
            json.dumps(current_queue, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info(
            f"🚀 ROI Update: {len(new_picks)} vídeos de alta performance adicionados à fila."
        )
    else:
        logger.info("Nenhum vídeo novo de alta performance encontrado no período.")
