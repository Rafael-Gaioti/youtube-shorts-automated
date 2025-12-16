"""
Script 4: Corte de Vídeos
Extrai os segmentos identificados pela análise usando FFmpeg.
"""

import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
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

def cut_video(
    video_path: Path,
    analysis_path: Path,
    output_dir: Optional[Path] = None
) -> List[Path]:
    """
    Corta vídeo nos segmentos identificados.

    Args:
        video_path: Caminho para o vídeo original
        analysis_path: Caminho para o arquivo de análise JSON
        output_dir: Diretório de saída (opcional)

    Returns:
        Lista de paths dos vídeos cortados

    Raises:
        FileNotFoundError: Se arquivos não existirem
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    if not analysis_path.exists():
        raise FileNotFoundError(f"Análise não encontrada: {analysis_path}")

    config = load_config()

    if output_dir is None:
        output_dir = Path(config['paths']['output'])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Carregar análise
    with open(analysis_path, 'r', encoding='utf-8') as f:
        analysis_data = json.load(f)

    cuts = analysis_data.get('cuts', [])
    if not cuts:
        logger.warning("Nenhum corte encontrado na análise")
        return []

    logger.info(f"Processando {len(cuts)} cortes do vídeo: {video_path.name}")

    output_files = []

    for i, cut in enumerate(cuts, 1):
        start_time = cut['start']
        end_time = cut['end']
        duration = end_time - start_time

        # Nome do arquivo de saída
        output_file = output_dir / f"{video_path.stem}_cut_{i:02d}.mp4"

        logger.info(f"Corte {i}/{len(cuts)}: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s)")

        # Comando FFmpeg para corte preciso
        cmd = [
            "ffmpeg",
            "-y",  # Sobrescrever sem perguntar
            "-ss", str(start_time),  # Seek para início
            "-i", str(video_path),  # Input
            "-t", str(duration),  # Duração
            "-c", "copy",  # Copiar sem re-encode (rápido)
            "-avoid_negative_ts", "1",  # Evitar timestamps negativos
            str(output_file)
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"✓ Salvo: {output_file.name}")
            output_files.append(output_file)

        except subprocess.CalledProcessError as e:
            logger.error(f"Erro ao cortar segmento {i}: {e}")
            logger.error(f"Stderr: {e.stderr}")
            continue

    return output_files

def find_latest_analysis() -> tuple[Path, Path]:
    """
    Encontra a análise mais recente e o vídeo correspondente.

    Returns:
        Tupla (video_path, analysis_path)
    """
    config = load_config()
    analysis_dir = Path(config['paths']['analysis'])
    raw_dir = Path(config['paths']['raw_videos'])

    analyses = list(analysis_dir.glob("*_analysis.json"))
    if not analyses:
        raise FileNotFoundError(f"Nenhuma análise encontrada em {analysis_dir}")

    # Pega a análise mais recente
    latest_analysis = max(analyses, key=lambda p: p.stat().st_mtime)

    # Carrega para pegar o video_id
    with open(latest_analysis, 'r', encoding='utf-8') as f:
        data = json.load(f)

    video_id = data['video_id']

    # Procura o vídeo correspondente
    video_path = raw_dir / f"{video_id}.mp4"

    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    return video_path, latest_analysis

def main():
    """Função principal."""
    if len(sys.argv) > 2:
        video_path = Path(sys.argv[1])
        analysis_path = Path(sys.argv[2])
    elif len(sys.argv) > 1:
        analysis_path = Path(sys.argv[1])
        # Tenta inferir o vídeo a partir da análise
        with open(analysis_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        config = load_config()
        raw_dir = Path(config['paths']['raw_videos'])
        video_path = raw_dir / f"{data['video_id']}.mp4"
    else:
        logger.info("Buscando análise e vídeo mais recentes...")
        video_path, analysis_path = find_latest_analysis()

    try:
        logger.info(f"Vídeo: {video_path}")
        logger.info(f"Análise: {analysis_path}")

        output_files = cut_video(video_path, analysis_path)

        print(f"\n✓ Cortes concluídos!")
        print(f"Total de segmentos extraídos: {len(output_files)}")

        for i, file in enumerate(output_files, 1):
            size_mb = file.stat().st_size / (1024 * 1024)
            print(f"{i}. {file.name} ({size_mb:.1f} MB)")

        print(f"\nPróximo passo: python scripts/5_export.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
