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
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()


def load_config() -> dict:
    """Carrega configurações do arquivo YAML."""
    config_path = Path("config/settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def transcribe_video(video_path: Path, output_dir: Optional[Path] = None) -> Dict:
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
    whisper_cfg = config["whisper_config"]

    if output_dir is None:
        output_dir = Path(config["paths"]["transcripts"])
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Carregando modelo Whisper...")
    logger.info(f"Modelo: {whisper_cfg['model_size']}")
    logger.info(f"Device: {whisper_cfg['device']}")
    logger.info(f"Compute type: {whisper_cfg['compute_type']}")

    # Verificar se CUDA está disponível e se cuDNN está instalado
    use_cuda = whisper_cfg["device"] == "cuda"

    if use_cuda:
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning("CUDA não disponível, usando CPU...")
                use_cuda = False
            else:
                # Tentar verificar cuDNN
                try:
                    # Teste rápido para ver se cuDNN está funcionando
                    torch.nn.functional.conv2d(
                        torch.zeros(1, 1, 1, 1, device="cuda"),
                        torch.zeros(1, 1, 1, 1, device="cuda"),
                    )
                    logger.info("CUDA e cuDNN estão funcionando")
                except Exception as e:
                    logger.warning(f"Erro ao testar cuDNN: {e}")
                    logger.warning(
                        "Fazendo fallback para CPU (processamento será mais lento)..."
                    )
                    logger.info(
                        "Dica: Para usar GPU, instale cuDNN de https://developer.nvidia.com/cudnn-downloads"
                    )
                    use_cuda = False
        except ImportError:
            logger.warning("PyTorch não encontrado, usando CPU...")
            use_cuda = False

    # Carregar modelo com device apropriado
    device = "cuda" if use_cuda else "cpu"
    compute_type = whisper_cfg["compute_type"] if use_cuda else "int8"

    logger.info(
        f"Carregando modelo em {device.upper()} com compute_type={compute_type}..."
    )

    model = WhisperModel(
        whisper_cfg["model_size"],
        device=device,
        compute_type=compute_type,
        download_root=config["paths"]["models"],
    )

    logger.info(f"Modelo carregado com sucesso em {device.upper()}")

    logger.info(f"Transcrevendo: {video_path.name}")

    # Transcrever com fallback para CPU se cuDNN falhar durante a execução
    try:
        segments, info = model.transcribe(
            str(video_path),
            beam_size=whisper_cfg["beam_size"],
            language=whisper_cfg.get("language"),
            task=whisper_cfg["task"],
            vad_filter=whisper_cfg["vad_filter"],
            vad_parameters=whisper_cfg.get("vad_parameters"),
            word_timestamps=True,  # Habilita timestamps por palavra
        )
    except Exception as e:
        error_msg = str(e).lower()
        if ("cudnn" in error_msg or "cuda" in error_msg) and whisper_cfg[
            "device"
        ] == "cuda":
            logger.warning(f"Erro CUDA/cuDNN durante transcrição: {e}")
            logger.warning(
                "Fazendo fallback para CPU (processamento será mais lento)..."
            )
            logger.info(
                "Dica: Para usar GPU, instale cuDNN de https://developer.nvidia.com/cudnn-downloads"
            )

            # Recarregar modelo em CPU
            model = WhisperModel(
                whisper_cfg["model_size"],
                device="cpu",
                compute_type="int8",  # CPU não suporta float16
                download_root=config["paths"]["models"],
            )
            logger.info("Modelo recarregado em CPU, retomando transcrição...")

            # Tentar novamente com CPU
            segments, info = model.transcribe(
                str(video_path),
                beam_size=whisper_cfg["beam_size"],
                language=whisper_cfg.get("language"),
                task=whisper_cfg["task"],
                vad_filter=whisper_cfg["vad_filter"],
                vad_parameters=whisper_cfg.get("vad_parameters"),
            )
        else:
            # Erro diferente, propagar
            raise

    logger.info(
        f"Idioma detectado: {info.language} (probabilidade: {info.language_probability:.2f})"
    )

    # Processar segmentos (com fallback para CPU se cuDNN falhar durante iteração)
    transcript_data = {
        "video_id": video_path.stem,
        "video_path": str(video_path),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": [],
    }

    logger.info("Processando segmentos...")
    try:
        for segment in segments:
            segment_data = {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "avg_logprob": segment.avg_logprob,
                "no_speech_prob": segment.no_speech_prob,
                "words": [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    }
                    for w in (segment.words or [])
                ],
            }
            transcript_data["segments"].append(segment_data)
    except Exception as e:
        error_msg = str(e).lower()
        if ("cudnn" in error_msg or "cuda" in error_msg) and whisper_cfg[
            "device"
        ] == "cuda":
            logger.warning(f"Erro CUDA/cuDNN durante processamento de segmentos: {e}")
            logger.warning("Fazendo fallback para CPU e reprocessando...")
            logger.info(
                "Dica: Para usar GPU, instale cuDNN de https://developer.nvidia.com/cudnn-downloads"
            )

            # Recarregar modelo em CPU
            model = WhisperModel(
                whisper_cfg["model_size"],
                device="cpu",
                compute_type="int8",
                download_root=config["paths"]["models"],
            )
            logger.info("Modelo recarregado em CPU, retomando transcrição completa...")

            # Retranscrever tudo em CPU
            segments, info = model.transcribe(
                str(video_path),
                beam_size=whisper_cfg["beam_size"],
                language=whisper_cfg.get("language"),
                task=whisper_cfg["task"],
                vad_filter=whisper_cfg["vad_filter"],
                vad_parameters=whisper_cfg.get("vad_parameters"),
            )

            # Atualizar transcript_data com info da CPU
            transcript_data["language"] = info.language
            transcript_data["language_probability"] = info.language_probability
            transcript_data["duration"] = info.duration
            transcript_data["segments"] = []

            # Processar segmentos novamente
            for segment in segments:
                segment_data = {
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "avg_logprob": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob,
                }
                transcript_data["segments"].append(segment_data)
        else:
            # Erro diferente, propagar
            raise

    logger.info(f"Total de segmentos: {len(transcript_data['segments'])}")

    # Salvar transcrição
    output_file = output_dir / f"{video_path.stem}_transcript.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Transcrição salva em: {output_file}")

    return transcript_data


def find_latest_video() -> Path:
    """Encontra o vídeo mais recente na pasta raw."""
    config = load_config()
    raw_dir = Path(config["paths"]["raw_videos"])

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
