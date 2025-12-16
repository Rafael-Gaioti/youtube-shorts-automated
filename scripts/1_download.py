"""
Script 1: Download de Vídeos do YouTube
Baixa vídeos do YouTube usando yt-dlp com configurações otimizadas.
"""

import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

def load_config() -> dict:
    """Carrega configurações do arquivo YAML."""
    config_path = Path("config/settings.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
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
        output_dir = Path(config['paths']['raw_videos'])

    output_dir.mkdir(parents=True, exist_ok=True)

    # Extrair video_id da URL para nome do arquivo
    output_template = output_dir / "%(id)s.%(ext)s"

    download_cfg = config['download_config']

    cmd = [
        "yt-dlp",
        "-f", download_cfg['format'],
        "-o", str(output_template),
        "--merge-output-format", "mp4",
        url
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
        logger.error(f"Stderr: {e.stderr}")
        raise

def main():
    """Função principal."""
    if len(sys.argv) < 2:
        print("Uso: python 1_download.py <URL_DO_YOUTUBE>")
        sys.exit(1)

    url = sys.argv[1]

    try:
        video_path = download_video(url)
        print(f"\n✓ Vídeo baixado com sucesso: {video_path}")
        print(f"\nPróximo passo: python scripts/2_transcribe.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()