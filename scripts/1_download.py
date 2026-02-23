"""
Script 1: Download de Vídeos do YouTube
Baixa vídeos do YouTube usando yt-dlp com configurações otimizadas.
"""

import sys
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_yt_dlp_path() -> str:
    """Retorna o caminho do yt-dlp, priorizando a pasta do executável atual (venv)."""
    # No Windows, em um venv, o yt-dlp.exe fica na mesma pasta que o python.exe (Scripts)
    python_dir = Path(sys.executable).parent
    yt_dlp_ext = ".exe" if sys.platform == "win32" else ""
    local_yt_dlp = python_dir / f"yt-dlp{yt_dlp_ext}"

    if local_yt_dlp.exists():
        return str(local_yt_dlp)

    # Fallback para o PATH global
    return shutil.which("yt-dlp") or "yt-dlp"


def check_yt_dlp() -> bool:
    """Verifica se yt-dlp está instalado."""
    path = get_yt_dlp_path()
    return shutil.which(path) is not None or Path(path).exists()


# Carregar variáveis de ambiente
load_dotenv()


def load_config() -> dict:
    """Carrega configurações do arquivo YAML."""
    config_path = Path("config/settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def download_video(url: str, output_dir: Optional[Path] = None) -> Path:
    """
    Baixa um vídeo do YouTube.

    Args:
        url: URL do vídeo do YouTube
        output_dir: Diretório de saída (opcional)

    Returns:
        Path do vídeo baixado

    Raises:
        subprocess.CalledProcessError: Se o download falhar
    """
    config = load_config()

    if output_dir is None:
        output_dir = Path(config["paths"]["raw_videos"])

    output_dir.mkdir(parents=True, exist_ok=True)

    # Extrair video_id da URL para nome do arquivo
    output_template = output_dir / "%(id)s.%(ext)s"

    download_cfg = config["download_config"]

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        download_cfg["format"],
        "-o",
        str(output_template),
        "--merge-output-format",
        "mp4",
        url,
    ]

    logger.info(f"Iniciando download de: {url}")
    logger.info(f"Salvando em: {output_dir}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Download concluído com sucesso!")

        # Encontrar arquivo baixado
        downloaded_files = list(output_dir.glob("*.mp4"))
        if downloaded_files:
            video_path = downloaded_files[-1]  # Pega o mais recente
            logger.info(f"Arquivo salvo: {video_path}")
            return video_path
        else:
            raise FileNotFoundError("Arquivo de vídeo não encontrado após download")

    except subprocess.CalledProcessError as e:
        logger.error(f"Erro no download: {e}")
        if e.stderr:
            logger.error(f"Detalhes: {e.stderr}")
        raise
    except FileNotFoundError as e:
        logger.error(str(e))
        raise


import argparse


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Download de vídeos do YouTube.")
    parser.add_argument("url", nargs="?", help="URL do vídeo do YouTube")
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil do usuário (SaaS)"
    )
    args = parser.parse_args()

    if not args.url:
        from scripts.utils import supabase_client

        logger.info("Nenhuma URL fornecida via CLI. Buscando fila no Supabase...")
        videos_pendentes = supabase_client.get_videos_by_stage("discovered")

        if not videos_pendentes:
            logger.info("Nenhum vídeo pendente de download ('discovered') no banco.")
            sys.exit(0)

        for v in videos_pendentes:
            url = v.get("url")
            video_code = v.get("video_code")
            logger.info(
                f"==> Iniciando download automático: {v.get('title')} ({video_code})"
            )
            try:
                video_path = download_video(url)
                logger.info(f"[SUCCESS] Video baixado com sucesso: {video_path}")
                supabase_client.update_video_stage(video_code, "downloaded")
                logger.info(f"Status no Supabase atualizado para 'downloaded'.")
            except Exception as e:
                logger.error(f"Erro ao baixar {url}: {e}", exc_info=True)
                supabase_client.update_video_stage(
                    video_code, "failed", error_log=str(e)
                )

        logger.info("\n✓ Fila de downloads concluída!")
        print(f"\nProximo passo: python scripts/2_transcribe.py")
        sys.exit(0)

    url = args.url

    try:
        video_path = download_video(url)
        print(f"\n[SUCCESS] Video baixado com sucesso: {video_path}")
        # Optionally extract video_code to update manual status
        import re

        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if match:
            from scripts.utils import supabase_client

            supabase_client.update_video_stage(match.group(1), "downloaded")

        print(f"\nProximo passo: python scripts/2_transcribe.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
