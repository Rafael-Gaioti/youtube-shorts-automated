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

    def fetch_recent_videos(
        self, channel_url: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Usa yt-dlp para listar vídeos recentes de um canal sem usar API Quota."""
        logger.info(f"Buscando vídeos recentes de: {channel_url}")

        # Filtro de data para yt-dlp: vídeos dos últimos 'days'
        date_after = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        cmd = [
            "yt-dlp",
            "--quiet",
            "--no-warnings",
            "--print-json",
            "--flat-playlist",
            "--dateafter",
            date_after,
            "--playlist-end",
            "5",  # Pegar apenas os 5 mais recentes
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

                # Ignorar se for Shorts (opcional, mas geralmente queremos vídeos longos para cortes)
                if (
                    video_data.get("duration") and video_data["duration"] < 300
                ):  # < 5 min
                    continue

                videos.append(
                    {
                        "id": video_data["id"],
                        "title": video_data["title"],
                        "url": f"https://www.youtube.com/watch?v={video_data['id']}",
                        "view_count": video_data.get("view_count", 0),
                        "channel": video_data.get("channel", "Unknown"),
                        "duration": video_data.get("duration", 0),
                    }
                )
        except Exception as e:
            logger.error(f"Falha na descoberta: {e}")

        return videos

    def get_viral_candidates(self, channels: List[str]) -> List[Dict[str, Any]]:
        """Filtra vídeos com potencial viral (velocity check)."""
        candidates = []
        for channel in channels:
            videos = self.fetch_recent_videos(channel)
            for v in videos:
                if self.is_processed(v["id"]):
                    continue

                # Regra simples de Viralidade: Video com muitas views proporcional ao tempo
                # Por agora, vamos apenas pegar os novos que não processamos
                logger.info(
                    f"Candidato encontrado: {v['title']} ({v['view_count']} views)"
                )
                candidates.append(v)
                self.mark_discovered(v["id"], v["title"], v["channel"])

        return candidates


if __name__ == "__main__":
    # Exemplo de uso: Canais sugeridos
    target_channels = [
        "https://www.youtube.com/@PrimoCast/videos",
        "https://www.youtube.com/@FlowPodcast/videos",
    ]

    discoverer = VideoDiscoverer()
    new_picks = discoverer.get_viral_candidates(target_channels)

    if new_picks:
        # Salva a fila de descoberta para o próximo passo do pipeline
        queue_path = Path("data/discovery_queue.json")
        queue_path.parent.mkdir(parents=True, exist_ok=True)

        current_queue = []
        if queue_path.exists():
            current_queue = json.loads(queue_path.read_text(encoding="utf-8"))

        current_queue.extend(new_picks)
        queue_path.write_text(
            json.dumps(current_queue, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info(
            f"Sucesso! {len(new_picks)} novos vídeos adicionados à fila em {queue_path}"
        )
    else:
        logger.info("Nenhum vídeo novo com alto potencial encontrado.")
