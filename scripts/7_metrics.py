"""
7_metrics.py — Coleta automática de métricas do YouTube e YouTube Analytics

Uso:
    python scripts/7_metrics.py [video_id]

Este script lê os registros na pasta data/uploads/ e consulta:
1. YouTube Data API v3 (Views, Likes, Comments)
2. YouTube Analytics API (Retenção, Duração Média da Visualização)
   Nota: A API de Analytics costuma ter delay de 24-48 horas.
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
        "❌ Dependências do Google não instaladas.\\n"
        "   Execute: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Os mesmos escopos definidos no 6_upload.py (Data API + Analytics API)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
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
    """Retorna os serviços youtube (v3) e youtubeAnalytics (v2)."""
    creds = None
    secrets_path = _find_client_secrets()
    if not secrets_path:
        logger.error(
            "❌ client_secrets.json não encontrado.\\n"
            "   Baixe as credenciais OAuth2 do Google Cloud Console e coloque na raiz do projeto."
        )
        sys.exit(1)

    TOKEN_PATH.parent.mkdir(exist_ok=True)
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Token expirado. Renovando...")
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(
                    f"Falha ao renovar token (possível mudança de escopos): {e}"
                )
                logger.info("Forçando re-autenticação...")
                creds = None

        if not creds:
            logger.info("Iniciando autenticação OAuth2 — o browser será aberto...")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
            logger.info(f"Token salvo em: {TOKEN_PATH}")

    youtube_service = build("youtube", "v3", credentials=creds)
    analytics_service = build("youtubeAnalytics", "v2", credentials=creds)

    return youtube_service, analytics_service


def fetch_basic_stats(youtube, video_ids: list[str]) -> dict:
    """Busca viewCount, likeCount, commentCount usando a Data API."""
    stats = {}
    if not video_ids:
        return stats

    # A API aceita até 50 IDs por vez
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
            logger.error(f"Erro ao buscar stats básicas: {e}")

    return stats


def fetch_retention_stats(analytics, video_id: str) -> dict:
    """Busca métricas de retenção via Analytics API. Espera-se delay de 24-48h no YouTube."""
    stats = {"averageViewDuration": None, "averageViewPercentage": None}

    try:
        # Analytics API requer range de datas. Buscar dos últimos 30 dias.
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

        # O formato da resposta é uma lista de colunas ['averageViewDuration', 'averageViewPercentage']
        # e uma lista vazia de `rows` se não houver dados ainda.
        if "rows" in response and response["rows"]:
            row = response["rows"][0]
            stats["averageViewDuration"] = float(row[0]) if len(row) > 0 else None
            stats["averageViewPercentage"] = float(row[1]) if len(row) > 1 else None

    except HttpError as e:
        # Erro comum: o vídeo é muito novo e o Analytics não consolidou
        if e.resp.status == 400 and "Invalid data provided" in str(e):
            logger.debug(
                f"[{video_id}] Analytics não disponível ainda (Delay 24h-48h)."
            )
        else:
            logger.error(f"Erro ao buscar analytics para {video_id}: {e}")

    return stats


def process_video_metrics(
    youtube, analytics, video_id: str, upload_records: list
) -> list:
    """Consolida as métricas para todos os shorts processados a partir do vídeo fonte."""

    yt_video_ids = [
        r["youtube_video_id"]
        for r in upload_records
        if "youtube_video_id" in r and r["youtube_video_id"] != "DRY_RUN"
    ]

    if not yt_video_ids:
        logger.info(
            f"[{video_id}] Nenhum short real encontrado (apenas DRY_RUN ou falhas). Ignorando."
        )
        return []

    logger.info(f"[{video_id}] Buscando Data API para {len(yt_video_ids)} shorts...")
    basic_stats = fetch_basic_stats(youtube, yt_video_ids)

    final_metrics = []

    for record in upload_records:
        vid = record.get("youtube_video_id")
        if not vid or vid == "DRY_RUN":
            continue

        b_stats = basic_stats.get(vid, {"views": 0, "likes": 0, "comments": 0})

        # Só vale a pena gastar request do Analytics se tiver view (para economizar cota e tempo)
        r_stats = {"averageViewDuration": None, "averageViewPercentage": None}
        if b_stats["views"] > 0:
            logger.info(f"[{video_id} -> {vid}] Buscando Analytics API...")
            r_stats = fetch_retention_stats(analytics, vid)
        else:
            logger.info(f"[{video_id} -> {vid}] 0 views, pulando Analytics API.")

        metrics_record = {
            "source_video_id": video_id,
            "cut_index": record["cut_index"],
            "youtube_video_id": vid,
            "youtube_url": record.get("youtube_url"),
            "uploaded_at": record.get("uploaded_at"),
            "metrics_updated_at": datetime.now().isoformat(),
            # IA Metadata para cruzamento no 8_correlate.py
            "viral_score": record.get("viral_score"),
            "hook_strength": record.get("hook_strength"),
            "opening_pattern": record.get("opening_pattern"),
            # YouTube Stats
            "views": b_stats["views"],
            "likes": b_stats["likes"],
            "comments": b_stats["comments"],
            "averageViewDuration": r_stats["averageViewDuration"],
            "averageViewPercentage": r_stats["averageViewPercentage"],
        }

        final_metrics.append(metrics_record)

    return final_metrics


def main():
    parser = argparse.ArgumentParser(description="Coleta de Métricas do YouTube Shorts")
    parser.add_argument(
        "video_id",
        type=str,
        nargs="?",
        help="ID do vídeo fonte original (opcional — usa todos em data/uploads se omitido)",
    )
    args = parser.parse_args()

    uploads_dir = Path("data/uploads")
    if not uploads_dir.exists():
        logger.error("Pasta data/uploads/ não encontrada. Rode o 6_upload.py primeiro.")
        sys.exit(1)

    # Identificar quais arquivos processar
    files_to_process = []
    if args.video_id:
        target_file = uploads_dir / f"{args.video_id}_uploads.json"
        if target_file.exists():
            files_to_process.append(target_file)
        else:
            logger.error(f"Arquivo não encontrado: {target_file}")
            sys.exit(1)
    else:
        files_to_process = list(uploads_dir.glob("*_uploads.json"))
        if not files_to_process:
            logger.info("Nenhum arquivo de upload encontrado.")
            sys.exit(0)

    # Autenticar apenas se tiver arquivos reais para processar
    youtube, analytics = get_authenticated_services()

    metrics_dir = Path("data/metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)

    total_processed = 0

    for upload_file in files_to_process:
        source_video_id = upload_file.name.replace("_uploads.json", "")

        with open(upload_file, "r", encoding="utf-8") as f:
            records = json.load(f)

        logger.info(f"\\n{'=' * 55}")
        logger.info(f" Processando métricas para: {source_video_id}")
        logger.info(f"{'=' * 55}")

        metrics = process_video_metrics(youtube, analytics, source_video_id, records)

        if metrics:
            # Salvar no arquivo de métricas
            output_file = metrics_dir / f"{source_video_id}_metrics.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Métricas atualizadas e salvas em {output_file.name}")
            for m in metrics:
                logger.info(
                    f"   [{m['youtube_video_id']}] Views: {m['views']} | V.Score: {m['viral_score']} | Retenção (segi): {m['averageViewDuration']}"
                )
            total_processed += len(metrics)

    logger.info(f"\\nResumo: {total_processed} shorts atualizados com sucesso.")


if __name__ == "__main__":
    main()
