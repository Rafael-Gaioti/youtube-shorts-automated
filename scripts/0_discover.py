import os
import json
import sqlite3
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VideoDiscoverer:
    def __init__(self, db_path: str = "data/discovery_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Inicializa o banco de dados de histórico para evitar duplicatas."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_videos (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                channel TEXT,
                discovered_at TIMESTAMP,
                processed BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def is_processed(self, video_id: str) -> bool:
        """Verifica se o vídeo já foi descoberto ou processado."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_videos WHERE video_id = ?", (video_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def mark_discovered(self, video_id: str, title: str, channel: str):
        """Registra no banco que um vídeo foi descoberto."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO processed_videos (video_id, title, channel, discovered_at)
            VALUES (?, ?, ?, ?)
        """,
            (video_id, title, channel, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def fetch_top_videos(
        self, channel_url: str, days: int = 90, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Usa yt-dlp para listar videos de um canal e filtrar pelos com maior view_count (ROI).
        """
        logger.info(
            f"Buscando TOP vídeos (ROI) de: {channel_url} nos últimos {days} dias"
        )

        date_after = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # --flat-playlist é rápido mas nem sempre traz o view_count correto no JSON flat.
        # Vamos pegar um número maior de itens da playlist para ter base de comparação.
        cmd = [
            "yt-dlp",
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

                # Ignorar Shorts e vídeos muito curtos
                duration = video_data.get("duration")
                if duration and duration < 300:  # < 5 min
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
        self, channels: List[str], max_per_channel: int = 3
    ) -> List[Dict[str, Any]]:
        """Busca os vídeos com melhor performance que ainda não foram processados."""
        candidates = []
        for channel in channels:
            # Busca os 50 mais recentes dos últimos 3 meses para comparar ROI
            all_recent = self.fetch_top_videos(channel, days=90, limit=50)

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
    target_channels = [
        "https://www.youtube.com/@PrimoCast/videos",
        "https://www.youtube.com/@FlowPodcast/videos",
    ]

    discoverer = VideoDiscoverer()
    # Pega os 3 melhores (mais vistos) de cada canal nos últimos 3 meses que ainda não fizemos
    new_picks = discoverer.get_viral_candidates(target_channels, max_per_channel=3)

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
