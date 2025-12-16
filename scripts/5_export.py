"""
Script 5: Exportação para Formato Shorts
Converte vídeos cortados para o formato otimizado de Shorts (9:16, vertical).
"""

import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional
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

def export_to_shorts(
    input_video: Path,
    output_dir: Optional[Path] = None,
    resolution: Optional[str] = None
) -> Path:
    """
    Exporta vídeo para formato Shorts (vertical 9:16).

    Args:
        input_video: Caminho para o vídeo de entrada
        output_dir: Diretório de saída (opcional)
        resolution: Resolução customizada, ex: "1080x1920" (opcional)

    Returns:
        Path do vídeo exportado

    Raises:
        FileNotFoundError: Se vídeo não existir
    """
    if not input_video.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {input_video}")

    config = load_config()
    video_cfg = config['video_config']

    if output_dir is None:
        output_dir = Path(config['paths']['output']) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)

    if resolution is None:
        resolution = video_cfg['resolution']

    width, height = map(int, resolution.split('x'))

    # Nome do arquivo de saída
    output_file = output_dir / f"{input_video.stem}_short.mp4"

    logger.info(f"Exportando: {input_video.name}")
    logger.info(f"Resolução: {resolution}")

    # FFmpeg command para conversão com reencoding
    # Aplica crop/scale para formato vertical mantendo aspect ratio
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
        "-c:v", video_cfg['video_codec'],
        "-preset", video_cfg['preset'],
        "-crf", str(video_cfg['crf']),
        "-b:v", video_cfg['video_bitrate'],
        "-r", str(video_cfg['fps']),
        "-c:a", video_cfg['audio_codec'],
        "-b:a", video_cfg['audio_bitrate'],
        "-movflags", "+faststart",  # Otimização para streaming
        str(output_file)
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"✓ Exportado: {output_file.name}")

        # Informações do arquivo
        size_mb = output_file.stat().st_size / (1024 * 1024)
        logger.info(f"Tamanho: {size_mb:.1f} MB")

        return output_file

    except subprocess.CalledProcessError as e:
        logger.error(f"Erro ao exportar vídeo: {e}")
        logger.error(f"Stderr: {e.stderr}")
        raise

def batch_export(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None
) -> List[Path]:
    """
    Exporta todos os vídeos cortados em lote.

    Args:
        input_dir: Diretório com vídeos cortados (opcional)
        output_dir: Diretório de saída (opcional)

    Returns:
        Lista de paths dos vídeos exportados
    """
    config = load_config()

    if input_dir is None:
        input_dir = Path(config['paths']['output'])

    # Buscar todos os vídeos cortados
    cut_videos = list(input_dir.glob("*_cut_*.mp4"))

    if not cut_videos:
        logger.warning(f"Nenhum vídeo cortado encontrado em {input_dir}")
        return []

    logger.info(f"Encontrados {len(cut_videos)} vídeos para exportar")

    output_files = []

    for video in cut_videos:
        try:
            output_file = export_to_shorts(video, output_dir)
            output_files.append(output_file)
        except Exception as e:
            logger.error(f"Erro ao exportar {video.name}: {e}")
            continue

    return output_files

def find_latest_cut() -> Path:
    """Encontra o vídeo cortado mais recente."""
    config = load_config()
    output_dir = Path(config['paths']['output'])

    cuts = list(output_dir.glob("*_cut_*.mp4"))
    if not cuts:
        raise FileNotFoundError(f"Nenhum vídeo cortado encontrado em {output_dir}")

    # Retorna o mais recente
    latest = max(cuts, key=lambda p: p.stat().st_mtime)
    return latest

def main():
    """Função principal."""
    # Modos de uso:
    # python 5_export.py              -> Exporta todos os cortes em lote
    # python 5_export.py <arquivo>    -> Exporta arquivo específico
    # python 5_export.py --latest     -> Exporta o corte mais recente

    if len(sys.argv) > 1:
        arg = sys.argv[1]

        if arg == "--latest":
            logger.info("Buscando corte mais recente...")
            video_path = find_latest_cut()
            videos_to_export = [video_path]
        elif arg == "--all":
            logger.info("Modo batch: exportando todos os cortes...")
            try:
                output_files = batch_export()
                print(f"\n✓ Exportação em lote concluída!")
                print(f"Total de Shorts criados: {len(output_files)}")

                for i, file in enumerate(output_files, 1):
                    size_mb = file.stat().st_size / (1024 * 1024)
                    print(f"{i}. {file.name} ({size_mb:.1f} MB)")

                print(f"\n✓ Pipeline completo finalizado!")
                print(f"Shorts prontos em: data/output/shorts/")
                return

            except Exception as e:
                logger.error(f"Erro fatal: {e}", exc_info=True)
                sys.exit(1)
        else:
            video_path = Path(arg)
            videos_to_export = [video_path]
    else:
        # Padrão: exportar todos
        logger.info("Modo padrão: exportando todos os cortes...")
        try:
            output_files = batch_export()
            print(f"\n✓ Exportação concluída!")
            print(f"Total de Shorts criados: {len(output_files)}")

            for i, file in enumerate(output_files, 1):
                size_mb = file.stat().st_size / (1024 * 1024)
                print(f"{i}. {file.name} ({size_mb:.1f} MB)")

            print(f"\n✓ Pipeline completo finalizado!")
            print(f"Shorts prontos em: data/output/shorts/")
            return

        except Exception as e:
            logger.error(f"Erro fatal: {e}", exc_info=True)
            sys.exit(1)

    # Exportar vídeos individuais
    try:
        for video_path in videos_to_export:
            logger.info(f"Processando: {video_path}")
            output_file = export_to_shorts(video_path)

            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"\n✓ Short criado com sucesso!")
            print(f"Arquivo: {output_file}")
            print(f"Tamanho: {size_mb:.1f} MB")

        print(f"\n✓ Exportação concluída!")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
