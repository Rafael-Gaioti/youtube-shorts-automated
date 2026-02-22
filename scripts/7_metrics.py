"""
7_metrics.py — Coleta métricas dos Shorts publicados via YouTube Analytics API

Uso:
    python scripts/7_metrics.py                        # todos os uploads registrados
    python scripts/7_metrics.py --video-id y9hwhoB9XTI # vídeo específico
    python scripts/7_metrics.py --report               # gera relatório de correlação

Requer que os vídeos já tenham sido publicados com 6_upload.py.
Token OAuth2 salvo em config/youtube_token.json é reaproveitado.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

# Scopes: leitura de dados do canal + analytics
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TOKEN_PATH = Path("config/youtube_token.json")
TOKEN_METRICS_PATH = Path("config/youtube_metrics_token.json")


def get_service(scope_token_path: Path, scopes: list):
    """Autentica e retorna o serviço Google. Reaproveita token se disponível."""
    creds = None

    if scope_token_path.exists():
        creds = Credentials.from_authorized_user_file(str(scope_token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Buscar client_secrets
            secrets = _find_client_secrets()
            if not secrets:
                logger.error("client_secrets.json não encontrado.")
                sys.exit(1)
            logger.info(
                "Iniciando autenticação OAuth2 para métricas — o browser será aberto..."
            )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
            creds = flow.run_local_server(port=0)

        scope_token_path.parent.mkdir(exist_ok=True)
        with open(scope_token_path, "w") as f:
            f.write(creds.to_json())
        logger.info(f"Token salvo em: {scope_token_path}")

    return creds


def _find_client_secrets() -> Path | None:
    if Path("client_secrets.json").exists():
        return Path("client_secrets.json")
    candidates = list(Path(".").glob("client_secret_*.json"))
    return candidates[0] if candidates else None


def fetch_video_stats(youtube, youtube_video_id: str) -> dict | None:
    """
    Busca estatísticas básicas do vídeo via YouTube Data API v3.
    Retorna views, likes, comments do snippet statistics.
    """
    try:
        resp = (
            youtube.videos()
            .list(
                part="statistics,contentDetails",
                id=youtube_video_id,
            )
            .execute()
        )

        items = resp.get("items", [])
        if not items:
            logger.warning(f"Vídeo não encontrado: {youtube_video_id}")
            return None

        stats = items[0].get("statistics", {})
        details = items[0].get("contentDetails", {})

        return {
            "youtube_video_id": youtube_video_id,
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "duration": details.get("duration", ""),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    except HttpError as e:
        logger.error(f"Erro ao buscar stats de {youtube_video_id}: {e}")
        return None


def fetch_analytics(analytics, youtube_video_id: str, days: int = 28) -> dict | None:
    """
    Busca métricas de retenção via YouTube Analytics API.
    Requer scope yt-analytics.readonly.
    """
    from datetime import datetime, timedelta

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        resp = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,averageViewDuration,averageViewPercentage,likes,comments",
                dimensions="video",
                filters=f"video=={youtube_video_id}",
            )
            .execute()
        )

        rows = resp.get("rows", [])
        if not rows:
            logger.warning(
                f"Sem dados analytics para {youtube_video_id} nos últimos {days} dias."
            )
            return None

        row = rows[0]
        return {
            "youtube_video_id": youtube_video_id,
            "period_days": days,
            "views": int(row[1]),
            "avg_view_duration_s": round(float(row[2]), 1),
            "avg_view_percentage": round(float(row[3]), 1),
            "likes": int(row[4]),
            "comments": int(row[5]),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    except HttpError as e:
        logger.error(f"Erro ao buscar analytics de {youtube_video_id}: {e}")
        return None


def save_metrics(video_id: str, youtube_video_id: str, metrics: dict):
    """Salva métricas em data/metrics/{video_id}_{youtube_video_id}_metrics.json."""
    metrics_dir = Path("data/metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    path = metrics_dir / f"{video_id}_{youtube_video_id}_metrics.json"

    # Carregar histórico ou criar novo
    history = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)

    history.append(metrics)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    logger.info(f"   Métricas salvas em: {path}")
    return path


def generate_report(uploads_dir: Path = Path("data/uploads")):
    """
    Gera relatório de correlação entre campos de análise e performance real.
    Lê todos os uploads + métricas e salva em data/reports/performance_report.json.
    """
    metrics_dir = Path("data/metrics")
    reports_dir = Path("data/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for uploads_file in uploads_dir.glob("*_uploads.json"):
        video_id = uploads_file.stem.replace("_uploads", "")
        with open(uploads_file, "r", encoding="utf-8") as f:
            uploads = json.load(f)

        for upload in uploads:
            yt_id = upload.get("youtube_video_id")
            if not yt_id or yt_id == "DRY_RUN":
                continue

            # Buscar métricas salvas
            metrics_files = list(metrics_dir.glob(f"{video_id}_{yt_id}_metrics.json"))
            if not metrics_files:
                continue

            with open(metrics_files[0], "r", encoding="utf-8") as f:
                history = json.load(f)

            latest = history[-1] if history else {}

            rows.append(
                {
                    "video_id": video_id,
                    "youtube_video_id": yt_id,
                    "youtube_url": upload.get("youtube_url"),
                    "title": upload.get("title"),
                    "uploaded_at": upload.get("uploaded_at"),
                    # Campos de análise IA
                    "viral_score": upload.get("viral_score"),
                    "hook_strength": upload.get("hook_strength"),
                    "opening_pattern": upload.get("opening_pattern"),
                    # Performance real
                    "views": latest.get("views"),
                    "avg_view_duration_s": latest.get("avg_view_duration_s"),
                    "avg_view_percentage": latest.get("avg_view_percentage"),
                    "likes": latest.get("likes"),
                    "comments": latest.get("comments"),
                    "period_days": latest.get("period_days"),
                    "metrics_at": latest.get("fetched_at"),
                }
            )

    report_path = reports_dir / "performance_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'=' * 55}")
    logger.info(f"  RELATÓRIO GERADO: {report_path}")
    logger.info(f"  Total de shorts com dados: {len(rows)}")
    if rows:
        logger.info(f"\n  Top 5 por views:")
        for r in sorted(rows, key=lambda x: x.get("views") or 0, reverse=True)[:5]:
            logger.info(
                f"  [{r.get('views', '?')} views] "
                f"viral={r.get('viral_score', '?')} "
                f"hook={r.get('hook_strength', '?')} "
                f"ret={r.get('avg_view_percentage', '?')}% "
                f"— {r.get('title', '')[:40]}"
            )
    logger.info(f"{'=' * 55}")

    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Coleta métricas dos Shorts publicados"
    )
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="video_id do projeto (y9hwhoB9XTI). Padrão: todos os uploads registrados.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=28,
        help="Período de métricas analytics em dias (padrão: 28)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Gerar relatório de correlação IA x performance real",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Buscar apenas views/likes/comments (sem analytics de retenção)",
    )
    args = parser.parse_args()

    # Coletar uploads a processar
    uploads_dir = Path("data/uploads")
    if not uploads_dir.exists():
        logger.error(
            "Nenhum upload registrado em data/uploads/. Execute 6_upload.py primeiro."
        )
        sys.exit(1)

    if args.video_id:
        upload_files = list(uploads_dir.glob(f"{args.video_id}_uploads.json"))
    else:
        upload_files = list(uploads_dir.glob("*_uploads.json"))

    if not upload_files:
        logger.error("Nenhum arquivo de uploads encontrado.")
        sys.exit(1)

    # Autenticar
    creds = get_service(TOKEN_METRICS_PATH, SCOPES)
    youtube = build("youtube", "v3", credentials=creds)
    analytics = None
    if not args.stats_only:
        analytics = build("youtubeAnalytics", "v2", credentials=creds)

    total_fetched = 0

    for uploads_file in upload_files:
        video_id = uploads_file.stem.replace("_uploads", "")
        with open(uploads_file, "r", encoding="utf-8") as f:
            uploads = json.load(f)

        logger.info(f"\n--- {video_id} ({len(uploads)} short(s)) ---")

        for upload in uploads:
            yt_id = upload.get("youtube_video_id")
            if not yt_id or yt_id == "DRY_RUN":
                continue

            logger.info(f"  📊 {yt_id}")

            # Stats básicas (views, likes, comments)
            stats = fetch_video_stats(youtube, yt_id)
            if not stats:
                continue

            logger.info(
                f"     Views: {stats['views']} | Likes: {stats['likes']} | Comments: {stats['comments']}"
            )

            # Analytics de retenção
            if not args.stats_only and analytics:
                anal = fetch_analytics(analytics, yt_id, days=args.days)
                if anal:
                    stats.update(anal)
                    logger.info(
                        f"     Retenção: {anal.get('avg_view_percentage', '?')}% "
                        f"| Duração média: {anal.get('avg_view_duration_s', '?')}s"
                    )

            save_metrics(video_id, yt_id, stats)
            total_fetched += 1

    logger.info(f"\n{'=' * 55}")
    logger.info(f"  Métricas coletadas: {total_fetched} short(s)")
    logger.info(f"{'=' * 55}")

    if args.report:
        generate_report(uploads_dir)


if __name__ == "__main__":
    main()
