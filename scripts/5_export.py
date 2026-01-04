"""
Script 5: Exportação para Formato Shorts
Converte vídeos cortados para o formato otimizado de Shorts (9:16, vertical).
"""

import sys
import json
import logging
import subprocess
import argparse
from pathlib import Path
from typing import List, Optional
from datetime import timedelta
import yaml
from dotenv import load_dotenv
import os

# Adicionar o diretório raiz ao path para permitir imports de scripts.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils.settings_manager import settings_manager

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


def format_timestamp_ass(seconds: float) -> str:
    """Converte segundos para formato ASS (H:MM:SS.cc)."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    centiseconds = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def create_ass_for_cut(
    transcript_path: Path,
    start_time: float,
    end_time: float,
    ass_output: Path,
    speakers_data: Optional[List[dict]] = None,
    primary_color: str = "&H00FFFF",
    secondary_color: str = "&H00FFFF00",
    font_size: int = 18,
) -> bool:
    """Gera um arquivo ASS com efeito de karaoke (palavra por palavra)."""
    if not transcript_path.exists():
        logger.warning(f"Transcrição não encontrada: {transcript_path}")
        return False

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        return False

    # Header do arquivo ASS
    ass_header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial Black,{font_size},{primary_color},{secondary_color},&H00000000,&H4B000000,-1,0,0,0,100,100,0,0,1,6,2,2,10,10,250,1",
        f"Style: Speaker2,Arial Black,{font_size},{secondary_color},{primary_color},&H00000000,&H4B000000,-1,0,0,0,100,100,0,0,1,6,2,2,10,10,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events = []

    # Pré-processamento: Identificar todos os oradores únicos no intervalo do corte
    unique_speakers_set = set()
    if speakers_data:
        for s in speakers_data:
            sid = s.get("id") or s.get("speaker")
            if sid:
                unique_speakers_set.add(sid)
    else:
        # Scan segments to find speakers in range
        for seg in segments:
            if seg["end"] <= start_time or seg["start"] >= end_time:
                continue
            sid = seg.get("speaker")
            if sid:
                unique_speakers_set.add(sid)

    unique_speakers_list = sorted(list(unique_speakers_set))

    for seg in segments:
        s, e = seg["start"], seg["end"]

        # Verificar se o segmento está dentro do intervalo do corte
        if e <= start_time or s >= end_time:
            continue

        words = seg.get("words", [])
        if not words:
            # Fallback para segmento inteiro
            rel_start = max(0, s - start_time)
            rel_end = min(end_time - start_time, e - start_time)

            if rel_start < rel_end:
                line_text = seg["text"].strip().upper()
                events.append(
                    f"Dialogue: 0,{format_timestamp_ass(rel_start)},{format_timestamp_ass(rel_end)},Default,,0,0,0,,{line_text}"
                )
            continue

        # --- LOGICA DE AGRUPAMENTO E ANIMACAO ---
        # Agrupamos palavras curtas para melhorar a legilibidade
        grouped_words = []
        if words:
            current_group = []
            group_start = -1
            group_duration = 0

            for w in words:
                w_start, w_end = w["start"], w["end"]
                if w_end <= start_time or w_start >= end_time:
                    continue

                if not current_group:
                    current_group = [w]
                    group_start = w_start
                    group_duration = w_end - w_start
                else:
                    # Critérios MELHORADOS para agrupar:
                    # 1. Duração acumulada < 0.7s (antes era 0.4) = mais tempo de leitura
                    # 2. OU Comprimento do texto < 15 chars (evita quebrar frases curtas)
                    # 3. MAS força quebra se passar de 35 chars (evita linhas gigantes)

                    current_text_len = sum(len(x["word"]) + 1 for x in current_group)
                    gap_to_next = w_start - current_group[-1]["end"]

                    # Se houver pausa grande (>0.5s), quebra o grupo (ponto natural)
                    force_break = (gap_to_next > 0.5) or (current_text_len > 30)

                    should_group = group_duration < 0.7 or len(w["word"].strip()) <= 3

                    if not force_break and should_group:
                        current_group.append(w)
                        group_duration = w_end - group_start
                    else:
                        # ANTES DE FECHAR: Verificar GAP
                        # Se o gap para a próxima palavra for pequeno (<0.2s), estender o 'end' deste grupo
                        # para cobrir o buraco e evitar flicker.
                        last_end = current_group[-1]["end"]
                        if (w_start - last_end) < 0.2:
                            # Estender levemente o fim do grupo atual para tocar o próximo
                            # Mas cuidado para não atropelar
                            actual_end = w_start
                        else:
                            actual_end = last_end

                        grouped_words.append(
                            {
                                "text": " ".join(
                                    [x["word"].strip() for x in current_group]
                                ).upper(),
                                "start": group_start,
                                "end": actual_end,
                            }
                        )
                        current_group = [w]
                        group_start = w_start
                        group_duration = w_end - w_start

            # Adicionar último grupo
            if current_group:
                grouped_words.append(
                    {
                        "text": " ".join(
                            [x["word"].strip() for x in current_group]
                        ).upper(),
                        "start": group_start,
                        "end": current_group[-1]["end"],
                    }
                )

        # Estilo "Pop-up Animated": zoom effect {\fscx50\fscy50\t(0,100,\fscx100\fscy100)}
        for gw in grouped_words:
            w_abs_start = gw["start"]
            w_rel_start = max(0, w_abs_start - start_time)
            w_rel_end = min(end_time - start_time, gw["end"] - start_time)

            if w_rel_start >= w_rel_end:
                continue

            # Identificar o orador para este momento (usando o ponto médio do grupo para robustez)
            w_midpoint = (gw["start"] + gw["end"]) / 2
            style_name = "Default"

            # -- Lógica de Estilo Dinâmica baseada nos Oradores do Corte --
            style_name = "Default"

            # O 'seg' vem do loop externo 'for seg in segments'
            speaker_id = seg.get("speaker")

            # 1. Determinar quem está falando neste exato momento (word midpoint)
            current_speaker = speaker_id  # Fallback para o id do segmento

            if speakers_data:
                for s_info in speakers_data:
                    if (s_info["start"] - 0.1) <= w_midpoint <= (s_info["end"] + 0.1):
                        current_speaker = s_info.get("id") or s_info.get("speaker") or 1
                        break

            # 2. Mapear o ID para um Estilo (0 ou 1)
            # Usamos a lista pré-calculada unique_speakers_list

            # Se o orador atual estiver na lista, descobre o índice
            if current_speaker in unique_speakers_list:
                spk_idx = unique_speakers_list.index(current_speaker)
                # Alterna entre Default e Speaker2
                if spk_idx % 2 == 1:
                    style_name = "Speaker2"
                else:
                    style_name = "Default"
            else:
                # Fallback, tenta heurística antiga se algo falhou
                if str(current_speaker) in [
                    "2",
                    "3",
                    "4",
                    "SPEAKER_01",
                    "SPEAKER_02",
                    "SPEAKER_03",
                ]:
                    style_name = "Speaker2"

            # Efeito Zoom-Pop: inicia em 80% e vai para 100% em 100ms
            animation = "{\\fscx80\\fscy80\\t(0,100,\\fscx100\\fscy100)}"

            events.append(
                f"Dialogue: 0,{format_timestamp_ass(w_rel_start)},{format_timestamp_ass(w_rel_end)},{style_name},,0,0,0,,{animation}{gw['text']}"
            )

    if not events:
        return False

    with open(ass_output, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_header + events))

    return True


def export_to_shorts(
    input_video: Path,
    output_dir: Optional[Path] = None,
    resolution: Optional[str] = None,
    profile_settings: Optional[dict] = None,
) -> Path:
    logger.info(f"--- Exportando para Shorts: {input_video.name} ---")
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
    video_cfg = config["video_config"]

    if output_dir is None:
        # Usar um diretório dedicado fora de 'output' para evitar conflitos de handles
        output_dir = Path(config["paths"]["data_root"]) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)

    if resolution is None:
        resolution = video_cfg["resolution"]

    width, height = map(int, resolution.split("x"))

    # Nome do arquivo de saída
    output_file = output_dir / f"{input_video.stem}_short.mp4"

    # Tentar encontrar metadados da análise para legendas e headline
    # O nome do arquivo costuma ser: {video_id}_cut_{num}.mp4
    video_id = input_video.stem.split("_cut_")[0]
    analysis_file = Path(config["paths"]["analysis"]) / f"{video_id}_analysis.json"

    headline = ""
    ass_path = None

    # Carregar configurações de estilo do perfil SaaS se disponíveis
    caption_styles = (
        (profile_settings or {}).get("user_profile", {}).get("caption_styles", {})
    )
    primary_color = caption_styles.get("primary_color", "&H00FFFF")
    secondary_color = caption_styles.get("secondary_color", "&H0000FF")
    font_size = caption_styles.get("font_size", 18)

    if analysis_file.exists():
        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                analysis = json.load(f)

            # Encontrar o corte correspondente
            cut_index_str = input_video.stem.split("_cut_")[-1]
            idx = int(cut_index_str) - 1
            if 0 <= idx < len(analysis["cuts"]):
                cut_data = analysis["cuts"][idx]
                headline = cut_data.get("on_screen_text", "").upper()

                # Gerar ASS (Karaoke Style)
                transcript_path = Path(analysis["transcript_path"])
                temp_ass = Path(f"temp_captions_{idx}.ass")

                # Sspeakers data for the cut
                speakers_info = cut_data.get("speakers", [])

                if create_ass_for_cut(
                    transcript_path,
                    cut_data["start"],
                    cut_data["end"],
                    temp_ass,
                    speakers_info,
                    primary_color=primary_color,
                    secondary_color=secondary_color,
                    font_size=font_size,
                ):
                    ass_path = temp_ass
                    logger.info("Legendas ASS (Karaoke) geradas com sucesso.")
        except Exception as e:
            logger.warning(f"Erro ao carregar metadados de análise: {e}")

    logger.info(f"Exportando: {input_video.name}")
    logger.info(f"Resolução: {resolution}")

    # Montar filtros do FFmpeg básicos (Crop 9:16)
    video_filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]

    # Sanitizar headline para o FFmpeg drawtext
    # Remover aspas simples e colons que quebram o filtro
    safe_headline = headline.replace("'", "").replace(":", "").strip()

    # Adicionar Legendas ASS (Karaoke)
    if ass_path and ass_path.exists():
        # No Windows, o path do filtro subtitles precisa de escape especial para o ':'
        # E o caminho deve usar forward slashes
        ass_str = str(ass_path.absolute()).replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"subtitles='{ass_str}'")
        logger.info(f"Filtro de legendas aplicado: {ass_path.name}")

    # Adicionar Headline (Texto fixo no topo)
    if safe_headline:
        # Estilo: Fundo preto semi-transparente, texto branco, centralizado no topo
        # Usamos : em vez de = para os parâmetros internos do drawtext para evitar conflitos no vf
        drawtext_filter = (
            f"drawtext=text='{safe_headline}':fontcolor=white:fontsize=80:"
            f"box=1:boxcolor=black@0.6:boxborderw=20:"
            f"x=(w-text_w)/2:y=200"
        )
        video_filters.append(drawtext_filter)
        logger.info(f"Filtro de headline aplicado: {safe_headline}")

    # FFmpeg command para conversão com reencoding
    logger.info(f"DEBUG: video_filters={video_filters}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video.absolute()),
        "-vf",
        ",".join(video_filters),
        "-c:v",
        video_cfg["video_codec"],
        "-preset",
        video_cfg["preset"],
        "-crf",
        str(video_cfg["crf"]),
        "-b:v",
        video_cfg["video_bitrate"],
        "-r",
        str(video_cfg["fps"]),
        "-c:a",
        video_cfg["audio_codec"],
        "-b:a",
        video_cfg["audio_bitrate"],
        "-movflags",
        "+faststart",
        str(output_file.absolute()),
    ]

    import json as json_lib

    logger.info(f"DEBUG_CMD: {json_lib.dumps(cmd)}")
    logger.info(f"Executando FFmpeg: {' '.join(cmd)}")
    try:
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            with open("ffmpeg_error.txt", "w", encoding="utf-8") as err_f:
                err_f.write(process.stderr)
            logger.error(
                f"FFmpeg falhou (ver ffmpeg_error.txt). Código: {process.returncode}"
            )
            raise RuntimeError(f"FFmpeg falhou com código {process.returncode}")

        logger.info(f"✓ Exportado: {output_file.name}")

        # Informações do arquivo
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024 * 1024)
            logger.info(f"Tamanho: {size_mb:.1f} MB")

        return output_file

    except Exception as e:
        logger.error(f"Erro ao exportar vídeo: {e}")
        raise


def batch_export(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    profile_settings: Optional[dict] = None,
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
        input_dir = Path(config["paths"]["output"])

    # Buscar todos os vídeos cortados
    cut_videos = list(input_dir.glob("*_cut_*.mp4"))

    if not cut_videos:
        logger.warning(f"Nenhum vídeo cortado encontrado em {input_dir}")
        return []

    logger.info(f"Encontrados {len(cut_videos)} vídeos para exportar")

    output_files = []

    for video in cut_videos:
        try:
            output_file = export_to_shorts(
                video, output_dir, profile_settings=profile_settings
            )
            output_files.append(output_file)
        except Exception as e:
            logger.error(f"Erro ao exportar {video.name}: {e}")
            continue

    return output_files


def find_latest_cut() -> Path:
    """Encontra o vídeo cortado mais recente."""
    config = load_config()
    output_dir = Path(config["paths"]["output"])

    cuts = list(output_dir.glob("*_cut_*.mp4"))
    if not cuts:
        raise FileNotFoundError(f"Nenhum vídeo cortado encontrado em {output_dir}")

    # Retorna o mais recente
    latest = max(cuts, key=lambda p: p.stat().st_mtime)
    return latest


def main():
    """Função principal."""
    # Garantir UTF-8 no terminal Windows
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Exportação de Shorts.")
    parser.add_argument("video", nargs="?", help="Caminho para o vídeo")
    parser.add_argument(
        "--latest", action="store_true", help="Usa o corte mais recente"
    )
    parser.add_argument("--all", action="store_true", help="Exporta todos os cortes")
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil do usuário (SaaS)"
    )
    args = parser.parse_args()

    # Carregar configurações do Perfil
    settings = settings_manager.get_settings(args.profile)

    if args.latest:
        logger.info("Buscando corte mais recente...")
        video_path = find_latest_cut()
        videos_to_export = [video_path]
    elif args.all:
        logger.info(
            f"Modo batch com perfil '{args.profile}': exportando todos os cortes..."
        )
        try:
            output_files = batch_export(profile_settings=settings)
            return
        except Exception as e:
            logger.error(f"Erro fatal: {e}", exc_info=True)
            sys.exit(1)
    elif args.video and args.video.endswith(".json"):
        logger.info(
            f"Detectado arquivo de análise: {args.video}. Extraindo cortes via Batch..."
        )
        try:
            output_files = batch_export(profile_settings=settings)
            return
        except Exception as e:
            logger.error(f"Erro fatal: {e}", exc_info=True)
            sys.exit(1)
    elif args.video:
        video_path = Path(args.video)
        videos_to_export = [video_path]
    else:
        # Padrão: exportar todos
        logger.info(
            f"Modo padrão com perfil '{args.profile}': exportando todos os cortes..."
        )
        try:
            output_files = batch_export(profile_settings=settings)
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
            logger.info(f"Processando com perfil '{args.profile}': {video_path}")
            output_file = export_to_shorts(video_path, profile_settings=settings)

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
