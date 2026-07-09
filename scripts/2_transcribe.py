"""
Script 2: Transcrição de Vídeos
Transcreve áudio de vídeos usando Whisper (GPU accelerated).
"""

import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from dotenv import load_dotenv
import os
import subprocess
import numpy as np

# Monkey-patch para compatibilidade com NumPy 1.x/2.0 em bibliotecas antigas
import numpy as np

for attr in ["NaN", "NAN", "Infinity"]:
    if not hasattr(np, attr):
        setattr(np, attr, getattr(np, "nan" if "N" in attr else "inf"))
# Patch adicional no módulo core caso necessário
if hasattr(np, "core"):
    for attr in ["NaN", "NAN", "Infinity"]:
        if not hasattr(np.core, attr):
            setattr(np.core, attr, getattr(np, "nan" if "N" in attr else "inf"))

# Adicionar o diretório raiz ao path para permitir imports de scripts.*
sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils.video_qa import check_video_for_subtitles
from scripts.utils.subtitle_qa import SubtitleAuditor

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


def transcribe_video(
    video_path: Path,
    output_dir: Optional[Path] = None,
    min_speakers: Optional[int] = None,
) -> Dict:
    """
    Transcreve um vídeo usando Whisper.

    Args:
        video_path: Caminho para o arquivo de vídeo
        output_dir: Diretório de saída para transcrição (opcional)
        min_speakers: Número mínimo de oradores (opcional)

    Returns:
        Dicionário com a transcrição e metadados

    Raises:
        FileNotFoundError: Se o vídeo não existir
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    # --- NOVO: QA VISUAL AUTOMATIZADO ---
    logger.info(f"Fazendo QA visual em: {video_path.name}")
    # Bypassed for developer test run to allow all videos
    has_subs, conf = False, 0.0

    config = load_config()
    whisper_cfg = config["whisper_config"]

    if output_dir is None:
        output_dir = Path(config["paths"]["transcripts"])
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = config.get("transcription_provider", "local").lower()
    
    if provider in ("deepgram", "groq", "openai"):
        logger.info(f"Usando provedor de transcrição em nuvem (API): {provider.upper()}")
        
        # 1. Extrair áudio leve (mono, 16kHz, MP3) do vídeo para upload rápido
        audio_path = video_path.with_suffix(".temp_audio.mp3")
        logger.info(f"Extraindo áudio otimizado para a API em: {audio_path}")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-ar", "16000", "-ac", "1", "-ab", "64k",
                str(audio_path)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error(f"Erro ao extrair áudio com FFmpeg: {e}")
            raise
            
        transcript_data = {}
        
        try:
            import requests
            
            if provider == "deepgram":
                dg_api_key = os.getenv("DEEPGRAM_API_KEY")
                if not dg_api_key or dg_api_key == "your_deepgram_api_key_here":
                    logger.error("Erro: DEEPGRAM_API_KEY não encontrada no arquivo .env")
                    sys.exit(1)
                
                dg_cfg = config.get("deepgram_config", {})
                model = dg_cfg.get("model", "nova-3")
                smart_format = str(dg_cfg.get("smart_format", True)).lower()
                diarize = str(dg_cfg.get("diarize", True)).lower()
                language = dg_cfg.get("language", "pt")
                
                url = f"https://api.deepgram.com/v1/listen?model={model}&smart_format={smart_format}&diarize={diarize}&language={language}"
                headers = {
                    "Authorization": f"Token {dg_api_key}",
                    "Content-Type": "audio/mpeg"
                }
                
                logger.info(f"Enviando áudio para Deepgram ({model})...")
                with open(audio_path, "rb") as f:
                    response = requests.post(url, headers=headers, data=f, timeout=300)
                
                response.raise_for_status()
                result = response.json()
                logger.info("Resposta recebida da Deepgram")
                
                # Mapear resposta da Deepgram para o formato padrão do pipeline
                alternatives = result["results"]["channels"][0]["alternatives"][0]
                words = alternatives.get("words", [])
                
                # Group words into segments (by sentence punctuation or pauses)
                segments = []
                current_segment_words = []
                segment_id = 0
                
                for i, w in enumerate(words):
                    current_segment_words.append(w)
                    is_last = (i == len(words) - 1)
                    gap_to_next = 0.0 if is_last else (words[i+1]["start"] - w["end"])
                    ends_with_punc = w["word"].endswith((".", "?", "!"))
                    
                    if is_last or ends_with_punc or gap_to_next > 0.8 or len(current_segment_words) >= 12:
                        seg_start = current_segment_words[0]["start"]
                        seg_end = current_segment_words[-1]["end"]
                        seg_text = " ".join([x["word"] for x in current_segment_words])
                        
                        # Dominant speaker
                        speakers = [x.get("speaker", 0) + 1 for x in current_segment_words]
                        dominant_speaker = max(set(speakers), key=speakers.count) if speakers else 1
                        
                        segments.append({
                            "id": segment_id,
                            "start": seg_start,
                            "end": seg_end,
                            "text": seg_text,
                            "avg_logprob": 0.0,
                            "no_speech_prob": 0.0,
                            "speaker": dominant_speaker,
                            "overlap": False,
                            "words": [
                                {
                                    "word": x["word"],
                                    "start": x["start"],
                                    "end": x["end"],
                                    "probability": x.get("confidence", 0.99),
                                    "speaker": x.get("speaker", 0) + 1
                                }
                                for x in current_segment_words
                            ]
                        })
                        segment_id += 1
                        current_segment_words = []
                
                # Calcular quantidade total de speakers
                unique_speakers = len(set(w.get("speaker", 0) + 1 for w in words)) if words else 1
                
                transcript_data = {
                    "video_id": video_path.stem,
                    "video_path": str(video_path),
                    "language": language,
                    "language_probability": 1.0,
                    "duration": result.get("metadata", {}).get("duration", 0.0),
                    "diarization_speakers_count": unique_speakers,
                    "segments": segments
                }
                
            elif provider == "openai":
                openai_api_key = os.getenv("OPENAI_API_KEY")
                if not openai_api_key or openai_api_key == "your_openai_api_key_here":
                    logger.error("Erro: OPENAI_API_KEY não encontrada no arquivo .env")
                    sys.exit(1)
                    
                url = "https://api.openai.com/v1/audio/transcriptions"
                headers = {
                    "Authorization": f"Bearer {openai_api_key}"
                }
                language = config.get("whisper_config", {}).get("language", "pt")
                data = {
                    "model": "whisper-1",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                    "language": language
                }
                
                logger.info("Enviando áudio para OpenAI Whisper API (whisper-1)...")
                with open(audio_path, "rb") as audio_file:
                    files = {
                        "file": (audio_path.name, audio_file, "audio/mpeg")
                    }
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=300)
                response.raise_for_status()
                result = response.json()
                logger.info("Resposta recebida do OpenAI Whisper")
                
                words = result.get("words", [])
                
                # Group words into segments
                segments = []
                current_segment_words = []
                segment_id = 0
                
                for i, w in enumerate(words):
                    current_segment_words.append(w)
                    is_last = (i == len(words) - 1)
                    gap_to_next = 0.0 if is_last else (words[i+1]["start"] - w["end"])
                    ends_with_punc = w["word"].endswith((".", "?", "!"))
                    
                    if is_last or ends_with_punc or gap_to_next > 0.8 or len(current_segment_words) >= 12:
                        seg_start = current_segment_words[0]["start"]
                        seg_end = current_segment_words[-1]["end"]
                        seg_text = " ".join([x["word"] for x in current_segment_words])
                        
                        segments.append({
                            "id": segment_id,
                            "start": seg_start,
                            "end": seg_end,
                            "text": seg_text,
                            "avg_logprob": 0.0,
                            "no_speech_prob": 0.0,
                            "speaker": 1,
                            "overlap": False,
                            "words": [
                                {
                                    "word": x["word"],
                                    "start": x["start"],
                                    "end": x["end"],
                                    "probability": 0.99,
                                    "speaker": 1
                                }
                                for x in current_segment_words
                            ]
                        })
                        segment_id += 1
                        current_segment_words = []
                
                transcript_data = {
                    "video_id": video_path.stem,
                    "video_path": str(video_path),
                    "language": language,
                    "language_probability": 1.0,
                    "duration": result.get("duration", 0.0),
                    "diarization_speakers_count": 1,
                    "segments": segments
                }
                
            elif provider == "groq":
                groq_api_key = os.getenv("GROQ_API_KEY")
                if not groq_api_key or groq_api_key == "your_groq_api_key_here":
                    logger.error("Erro: GROQ_API_KEY não encontrada no arquivo .env")
                    sys.exit(1)
                    
                groq_cfg = config.get("groq_whisper_config", {})
                model = groq_cfg.get("model", "whisper-large-v3")
                language = groq_cfg.get("language", "pt")
                
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {
                    "Authorization": f"Bearer {groq_api_key}"
                }
                files = {
                    "file": (audio_path.name, open(audio_path, "rb"), "audio/mpeg")
                }
                data = {
                    "model": model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                    "language": language
                }
                
                logger.info(f"Enviando áudio para Groq ({model})...")
                response = requests.post(url, headers=headers, files=files, data=data, timeout=300)
                response.raise_for_status()
                result = response.json()
                logger.info("Resposta recebida do Groq")
                
                words = result.get("words", [])
                
                # Group words into segments
                segments = []
                current_segment_words = []
                segment_id = 0
                
                for i, w in enumerate(words):
                    current_segment_words.append(w)
                    is_last = (i == len(words) - 1)
                    gap_to_next = 0.0 if is_last else (words[i+1]["start"] - w["end"])
                    ends_with_punc = w["word"].endswith((".", "?", "!"))
                    
                    if is_last or ends_with_punc or gap_to_next > 0.8 or len(current_segment_words) >= 12:
                        seg_start = current_segment_words[0]["start"]
                        seg_end = current_segment_words[-1]["end"]
                        seg_text = " ".join([x["word"] for x in current_segment_words])
                        
                        segments.append({
                            "id": segment_id,
                            "start": seg_start,
                            "end": seg_end,
                            "text": seg_text,
                            "avg_logprob": 0.0,
                            "no_speech_prob": 0.0,
                            "speaker": 1,
                            "overlap": False,
                            "words": [
                                {
                                    "word": x["word"],
                                    "start": x["start"],
                                    "end": x["end"],
                                    "probability": 0.99,
                                    "speaker": 1
                                }
                                for x in current_segment_words
                            ]
                        })
                        segment_id += 1
                        current_segment_words = []
                
                transcript_data = {
                    "video_id": video_path.stem,
                    "video_path": str(video_path),
                    "language": language,
                    "language_probability": 1.0,
                    "duration": result.get("duration", 0.0),
                    "diarization_speakers_count": 1,
                    "segments": segments
                }
                
        finally:
            # Remover áudio temporário após processamento
            if audio_path.exists():
                os.remove(audio_path)
                logger.info("Arquivo de áudio temporário removido.")
                
        # --- QA DE LEGENDAS (HALLUCINATION CHECK) ---
        logger.info("Iniciando auditoria de qualidade das legendas (Hallucination Check)...")
        auditor = SubtitleAuditor(config=config)
        audit_report = auditor.audit_transcript(transcript_data)
        transcript_data["audit_report"] = audit_report
        
        if not audit_report["is_healthy"]:
            logger.warning(
                f"⚠️  ALERTA DE QUALIDADE: Transcrição detectada como instável (Hallucination Ratio: {audit_report['hallucination_ratio']:.2%})"
            )
            
        # Salvar transcrição
        output_file = output_dir / f"{video_path.stem}_transcript.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Transcrição salva em: {output_file}")
        return transcript_data

    from faster_whisper import WhisperModel
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
                # Verificar cuDNN de forma confiável
                try:
                    cudnn_ok = torch.backends.cudnn.is_acceptable(
                        torch.zeros(1, device="cuda")
                    )
                    if cudnn_ok:
                        logger.info(
                            f"CUDA (RTX/GPU) e cuDNN {torch.backends.cudnn.version()} estão funcionando ✓"
                        )
                    else:
                        raise RuntimeError("cuDNN not acceptable")
                except Exception as e:
                    logger.warning(f"cuDNN indisponível ({e}), usando CPU...")
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

    # --- DIARIZAÇÃO (Pyannote) ---
    diarization_segments = []
    hf_token = os.getenv("HF_TOKEN")

    if hf_token:
        try:
            logger.info("Iniciando Diarização (Speaker ID) com Pyannote...")
            from pyannote.audio import Pipeline

            logger.info("Autenticando no Hugging Face Hub...")
            login(token=hf_token, add_to_git_credential=False)

            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
            )

            # Usar GPU se disponível, senão CPU
            diarization_device = "cuda" if use_cuda else "cpu"
            pipeline.to(torch.device(diarization_device))
            logger.info(f"Diarização rodando em: {diarization_device.upper()}")

            # Converter para WAV temporário para evitar erros de codec (LibsndfileError)
            wav_path = str(video_path).replace(".mp4", "_temp_diarization.wav")
            logger.info(f"Convertendo para WAV para diarização: {wav_path}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(video_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    wav_path,
                    "-y",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Rodar diarização no WAV
            diarization_kwargs = {}
            if min_speakers:
                diarization_kwargs["min_speakers"] = min_speakers
                logger.info(f"Forçando detecção de no mínimo {min_speakers} oradores.")

            diarization = pipeline(wav_path, **diarization_kwargs)

            # Cleanup output
            if os.path.exists(wav_path):
                os.remove(wav_path)

            # Converter para lista de tuplas (start, end, speaker)
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # Speaker vem como "SPEAKER_00", "SPEAKER_01". Vamos simplificar para 1, 2...
                speaker_id = int(speaker.split("_")[-1]) + 1
                diarization_segments.append(
                    {"start": turn.start, "end": turn.end, "speaker": speaker_id}
                )

            unique_speakers = len(set(s["speaker"] for s in diarization_segments))
            logger.info(
                f"Diarização concluída. {len(diarization_segments)} segmentos, {unique_speakers} locutor(es) únicos."
            )

        except Exception as e:
            logger.error(f"Erro na diarização: {e}")
            logger.warning("Prosseguindo sem identificação de oradores.")
    else:
        logger.warning(
            "HF_TOKEN não encontrado. Pulando diarização (todos segments terão speaker=1)."
        )

    # Função auxiliar para encontrar orador no tempo T
    def get_speaker_at(time_sec):
        if not diarization_segments:
            return 1  # Default Speaker 1

        for seg in diarization_segments:
            if seg["start"] <= time_sec <= seg["end"]:
                return seg["speaker"]

        # Se não cair em nenhum intervalo exato, procurar o mais próximo (fallback)
        closest = min(
            diarization_segments,
            key=lambda x: min(abs(x["start"] - time_sec), abs(x["end"] - time_sec)),
        )
        if (
            abs(closest["start"] - time_sec) < 1.0
            or abs(closest["end"] - time_sec) < 1.0
        ):
            return closest["speaker"]

        return 1  # Unknown

    def get_speakers_at_interval(start_sec, end_sec):
        """Retorna todos os locutores que falam dentro de um intervalo e se há overlap."""
        if not diarization_segments:
            return [1], False

        active = []
        for seg in diarization_segments:
            # Verificar sobreposição temporal
            if seg["end"] > start_sec and seg["start"] < end_sec:
                active.append(seg["speaker"])

        unique_in_interval = set(active)

        # Detectar overlap real: 2+ segmentos de locutores diferentes se sobrepõem
        has_overlap = False
        if len(unique_in_interval) > 1:
            # Verificar se algum par de segmentos de locutores diferentes se sobrepõe temporalmente
            interval_segs = [
                s
                for s in diarization_segments
                if s["end"] > start_sec and s["start"] < end_sec
            ]
            for i in range(len(interval_segs)):
                for j in range(i + 1, len(interval_segs)):
                    if interval_segs[i]["speaker"] != interval_segs[j]["speaker"]:
                        # Verificar sobreposição entre os dois segmentos
                        ov_start = max(
                            interval_segs[i]["start"], interval_segs[j]["start"]
                        )
                        ov_end = min(interval_segs[i]["end"], interval_segs[j]["end"])
                        if ov_end > ov_start:
                            has_overlap = True
                            break
                if has_overlap:
                    break

        return list(unique_in_interval) if unique_in_interval else [1], has_overlap

    unique_diarization_speakers = (
        len(set(s["speaker"] for s in diarization_segments))
        if diarization_segments
        else 1
    )

    transcript_data = {
        "video_id": video_path.stem,
        "video_path": str(video_path),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "diarization_speakers_count": unique_diarization_speakers,
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
                        "speaker": get_speaker_at(
                            (w.start + w.end) / 2
                        ),  # Atribuir orador por palavra
                    }
                    for w in (segment.words or [])
                ],
            }
            # Atribuir orador dominante ao segmento (moda das palavras)
            if segment_data["words"]:
                speakers = [w["speaker"] for w in segment_data["words"]]
                segment_data["speaker"] = max(set(speakers), key=speakers.count)
            else:
                segment_data["speaker"] = get_speaker_at(
                    (segment.start + segment.end) / 2
                )

            # Detectar se há sobreposição de vozes neste segmento
            _, has_overlap = get_speakers_at_interval(segment.start, segment.end)
            segment_data["overlap"] = has_overlap

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

            # Processar segmentos novamente com fallback
            for segment in segments:
                segment_data = {
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "avg_logprob": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob,
                    "words": [],
                    "speaker": 1,  # Default fallback speaker
                }
                transcript_data["segments"].append(segment_data)
        else:
            # Erro diferente, propagar
            raise

    logger.info(f"Total de segmentos: {len(transcript_data['segments'])}")

    # --- NOVO: QA DE LEGENDAS (HALLUCINATION CHECK) ---
    logger.info(
        "Iniciando auditoria de qualidade das legendas (Hallucination Check)..."
    )
    auditor = SubtitleAuditor(config=config)
    audit_report = auditor.audit_transcript(transcript_data)
    transcript_data["audit_report"] = audit_report

    if not audit_report["is_healthy"]:
        logger.warning(
            f"⚠️  ALERTA DE QUALIDADE: Transcrição detectada como instável (Hallucination Ratio: {audit_report['hallucination_ratio']:.2%})"
        )

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
    parser = argparse.ArgumentParser(description="Transcrição de vídeos.")
    parser.add_argument("video_path", nargs="?", help="Caminho para o vídeo")
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil do usuário (SaaS)"
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=None,
        help="Número mínimo de oradores (força diarização)",
    )
    args = parser.parse_args()

    if args.video_path:
        video_path = Path(args.video_path)
    else:
        from scripts.utils import supabase_client

        logger.info(
            "Nenhum vídeo especificado via CLI. Buscando fila no Supabase ('downloaded')..."
        )
        videos_pendentes = supabase_client.get_videos_by_stage("downloaded")

        if not videos_pendentes:
            logger.info("Nenhum vídeo pendente de transcrição ('downloaded') no banco.")
            sys.exit(0)

        for v in videos_pendentes:
            video_code = v.get("video_code")
            config = load_config()
            raw_dir = Path(config["paths"]["raw_videos"])
            video_path = raw_dir / f"{video_code}.mp4"

            if not video_path.exists():
                logger.error(
                    f"Vídeo {video_code} não encontrado no disco local: {video_path}"
                )
                supabase_client.update_video_stage(
                    video_code,
                    "failed",
                    error_log="Arquivo não encontrado no disco local",
                )
                continue

            logger.info(
                f"==> Iniciando transcrição automática: {v.get('title')} ({video_code})"
            )

            try:
                transcript = transcribe_video(
                    video_path, min_speakers=args.min_speakers
                )

                if (
                    isinstance(transcript, dict)
                    and transcript.get("status") == "skipped"
                ):
                    print(f"\n[WARNING] VIDEO PULADO: {transcript.get('reason')}")
                    supabase_client.update_video_stage(
                        video_code,
                        "failed",
                        error_log=f"Skipped QA: {transcript.get('reason')}",
                    )
                else:
                    logger.info(f"[SUCCESS] Transcrição concluída: {video_path}")
                    supabase_client.update_video_stage(video_code, "transcribed")
                    logger.info("Status no Supabase atualizado para 'transcribed'.")
            except Exception as e:
                logger.error(f"Erro ao transcrever {video_path}: {e}", exc_info=True)
                supabase_client.update_video_stage(
                    video_code, "failed", error_log=str(e)
                )

        logger.info("\n✓ Fila de transcrições concluída!")
        print(f"\nProximo passo: python scripts/3_analyze.py")
        sys.exit(0)

    try:
        logger.info(f"Processando: {video_path}")
        transcript = transcribe_video(video_path, min_speakers=args.min_speakers)

        if isinstance(transcript, dict) and transcript.get("status") == "skipped":
            print(f"\n[WARNING] VIDEO PULADO: {transcript.get('reason')}")
            print(f"Confiança da detecção: {transcript.get('confidence', 0):.2f}")
            from scripts.utils import supabase_client

            supabase_client.update_video_stage(
                video_path.stem,
                "failed",
                error_log=f"Skipped: {transcript.get('reason')}",
            )
            sys.exit(0)  # Exit success but it was a skip

        # Update specific manual task to "transcribed"
        from scripts.utils import supabase_client

        supabase_client.update_video_stage(video_path.stem, "transcribed")

        print(f"\n[SUCCESS] Transcricao concluida!")
        print(f"Segmentos: {len(transcript.get('segments', []))}")
        print(f"Duração: {transcript.get('duration', 0):.2f}s")
        print(f"Idioma: {transcript.get('language', 'unknown')}")
        print(f"\nPróximo passo: python scripts/3_analyze.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
