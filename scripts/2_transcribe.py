"""
Script 2: Transcrição de Vídeos
Transcreve áudio de vídeos usando Whisper (GPU accelerated).
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from dotenv import load_dotenv
from faster_whisper import WhisperModel

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

def transcribe_video(
    video_path: Path,
    output_dir: Optional[Path] = None
) -> Dict:
    """
    Transcreve um vídeo usando Whisper.

    Args:
        video_path: Caminho para o arquivo de vídeo
        output_dir: Diretório de saída para transcrição (opcional)

    Returns:
        Dicionário com a transcrição e metadados

    Raises:
        FileNotFoundError: Se o vídeo não existir
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    config = load_config()
    whisper_cfg = config['whisper_config']

    if output_dir is None:
        output_dir = Path(config['paths']['transcripts'])
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Carregando modelo Whisper...")
    logger.info(f"Modelo: {whisper_cfg['model_size']}")
    logger.info(f"Device: {whisper_cfg['device']}")
    logger.info(f"Compute type: {whisper_cfg['compute_type']}")

    # Carregar modelo
    model = WhisperModel(
        whisper_cfg['model_size'],
        device=whisper_cfg['device'],
        compute_type=whisper_cfg['compute_type'],
        download_root=config['paths']['models']
    )

    logger.info(f"Transcrevendo: {video_path.name}")

    # Transcrever
    segments, info = model.transcribe(
        str(video_path),
        beam_size=whisper_cfg['beam_size'],
        language=whisper_cfg.get('language'),
        task=whisper_cfg['task'],
        vad_filter=whisper_cfg['vad_filter'],
        vad_parameters=whisper_cfg.get('vad_parameters')
    )

    logger.info(f"Idioma detectado: {info.language} (probabilidade: {info.language_probability:.2f})")

    # Processar segmentos
    transcript_data = {
        "video_id": video_path.stem,
        "video_path": str(video_path),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": []
    }

    logger.info("Processando segmentos...")
    for segment in segments:
        segment_data = {
            "id": segment.id,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "avg_logprob": segment.avg_logprob,
            "no_speech_prob": segment.no_speech_prob
        }
        transcript_data["segments"].append(segment_data)

    logger.info(f"Total de segmentos: {len(transcript_data['segments'])}")

    # Salvar transcrição
    output_file = output_dir / f"{video_path.stem}_transcript.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Transcrição salva em: {output_file}")

    return transcript_data

def find_latest_video() -> Path:
    """Encontra o vídeo mais recente na pasta raw."""
    config = load_config()
    raw_dir = Path(config['paths']['raw_videos'])

    videos = list(raw_dir.glob("*.mp4"))
    if not videos:
        raise FileNotFoundError(f"Nenhum vídeo encontrado em {raw_dir}")

    # Retorna o mais recente
    latest = max(videos, key=lambda p: p.stat().st_mtime)
    return latest

def main():
    """Função principal."""
    if len(sys.argv) > 1:
        video_path = Path(sys.argv[1])
    else:
        logger.info("Nenhum vídeo especificado, buscando o mais recente...")
        video_path = find_latest_video()

    try:
        logger.info(f"Processando: {video_path}")
        transcript = transcribe_video(video_path)

        print(f"\n✓ Transcrição concluída!")
        print(f"Segmentos: {len(transcript['segments'])}")
        print(f"Duração: {transcript['duration']:.2f}s")
        print(f"Idioma: {transcript['language']}")
        print(f"\nPróximo passo: python scripts/3_analyze.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
