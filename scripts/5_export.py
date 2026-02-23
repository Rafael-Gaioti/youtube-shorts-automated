"""
Script 5: Exportação para Formato Shorts
Converte vídeos cortados para o formato otimizado de Shorts (9:16, vertical).
"""

import sys
import json
import logging
import subprocess
import argparse
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import timedelta
import yaml
from dotenv import load_dotenv
import os

# Adicionar o diretório raiz ao path para permitir imports de scripts.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.utils.settings_manager import settings_manager
from scripts.tools.thumbnail_generator import generate_thumbnail
from scripts.tools.frame_selector import extract_best_frame
from scripts.tools.design_auditor import DesignAuditor
from scripts.tools.video_quarantine import quarantine_video

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
        f"Style: Default,Arial Black,{font_size},{primary_color},{secondary_color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,10,2,2,10,10,250,1",
        f"Style: Speaker2,Arial Black,{font_size},{secondary_color},{primary_color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,10,2,2,10,10,150,1",
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

            # -- Lógica de Estilo Robusta (Híbrida) --
            # Problema: IDs variam (1, 3, SPEAKER_00...). Hardcoding falha.
            # Solução: Usar índice relativo. O 1º ID da lista (sorted) é Default. O resto é Speaker2.

            style_name = "Default"

            # Tentar identificar o orador atual com precisão temporal
            current_speaker = seg.get("speaker")
            midpoint = (gw["start"] + gw["end"]) / 2

            if speakers_data:
                for s_info in speakers_data:
                    if (s_info["start"] - 0.1) <= midpoint <= (s_info["end"] + 0.1):
                        current_speaker = s_info.get("id") or s_info.get("speaker")
                        break

            # Se identificou um orador e ele NÃO é o primeiro da lista, aplica Speaker2
            if current_speaker is not None and unique_speakers_list:
                # Se for o primeiro da lista ordenada (ex: 1), mantém Default (Amarelo)
                # Se for qualquer outro (ex: 3), aplica Speaker2 (Ciano)
                if current_speaker != unique_speakers_list[0]:
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

    # O nome definitivo será definido após carregar a análise (para usar o Hook como nome)
    output_file = None

    # Tentar encontrar metadados da análise para legendas e headline
    # O nome do arquivo costuma ser: {video_id}_cut_{num}.mp4
    video_id = input_video.stem.split("_cut_")[0]
    analysis_file = Path(config["paths"]["analysis"]) / f"{video_id}_analysis.json"

    headline = ""
    ass_path = None
    transcript_path = None
    youtube_title = ""
    thumb_hook = ""

    # Carregar configurações de estilo do perfil SaaS se disponíveis
    caption_styles = (
        (profile_settings or {}).get("user_profile", {}).get("caption_styles", {})
    )
    primary_color = caption_styles.get("primary_color", "&H00FFFF")
    secondary_color = caption_styles.get("secondary_color", "&H0000FF")
    # Aumentar font_size padrão de 18 para 75 para escala 1080p
    font_size = caption_styles.get("font_size", 75)

    if analysis_file.exists():
        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                analysis = json.load(f)

            # Encontrar o corte correspondente (ex: canal_cut_01_short -> 1)
            cut_part = input_video.stem.split("_cut_")[-1]
            import re

            match = re.search(r"(\d+)", cut_part)
            idx = int(match.group(1)) - 1 if match else 0

            # Default colors
            th_primary = "#FFFF00"
            th_secondary = "#FF0000"
            cut_data = {}

            if 0 <= idx < len(analysis["cuts"]):
                cut_data = analysis["cuts"][idx]
                logger.info(f"DEBUG: Usando cut_data no indice {idx}")
                logger.info(
                    f"DEBUG: Range nominal: {cut_data['start']}s - {cut_data['end']}s"
                )
                logger.info(f"DEBUG: Thumbnail Hook: {cut_data.get('thumbnail_hook')}")
                headline = cut_data.get("on_screen_text", "").upper()
                thumb_hook = cut_data.get("thumbnail_hook", headline).upper()
                youtube_title = cut_data.get("youtube_title", "").upper()

                # -- Engenharia de Atenção: Cores Dinâmicas --
                content_type = cut_data.get("content_type", "unknown").lower()
                if (
                    "fear" in content_type
                    or "mistake" in content_type
                    or "danger" in content_type
                ):
                    th_primary, th_secondary = "#FFFFFF", "#FF0000"
                elif (
                    "success" in content_type
                    or "money" in content_type
                    or "wealth" in content_type
                ):
                    th_primary, th_secondary = "#FFFF00", "#00FF00"
                elif (
                    "mystery" in content_type
                    or "secret" in content_type
                    or "revelation" in content_type
                ):
                    th_primary, th_secondary = "#00FFFF", "#FF00FF"

                # Gerar ASS (Karaoke Style)
                transcript_path = Path(analysis["transcript_path"])
                # Usar UUID para evitar colisões em processamento paralelo ou retries
                temp_ass = Path(f"temp_{uuid.uuid4().hex[:8]}.ass")
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

    # Guard de Sincronização: Verificar se o vídeo é MAIS ANTIGO que a análise
    # Se a análise foi refeita mas o corte não, temos um risco alto de desalinhamento
    if analysis_file.exists() and input_video.exists():
        analysis_mtime = analysis_file.stat().st_mtime
        video_mtime = input_video.stat().st_mtime

        # Se a diferença for significativa (>5 segundos) e o vídeo for mais antigo
        if (analysis_mtime - video_mtime) > 5:
            logger.warning(
                "! WARNING: O vídeo de entrada é mais antigo que o arquivo de análise !"
            )
            logger.warning(
                f"! Isso pode causar legendas desalinhadas. Re-execute 'scripts/4_cut.py' para sincronizar."
            )
    # Prioridade: Hook do conteúdo (Thumbnail Hook) -> Headline -> Nome original
    if "thumb_hook" in locals() and thumb_hook:
        base_name = (
            thumb_hook.replace(" ", "-")
            .replace("?", "")
            .replace("!", "")
            .replace(".", "")
            .upper()
        )
    elif safe_headline:
        base_name = (
            safe_headline.replace(" ", "-")
            .replace("?", "")
            .replace("!", "")
            .replace(".", "")
            .upper()
        )
    else:
        base_name = f"{input_video.stem}_V4_3"

    # Garantir unicidade (caso dois cortes tenham o mesmo hook)
    video_id_seed = input_video.stem.split("_cut_")[-1]
    final_name = f"{base_name}_C{video_id_seed}"
    output_file = output_dir / f"{final_name}.mp4"
    thumb_path = output_dir / f"{final_name}_thumb.jpg"

    # Sanitizar headline para o FFmpeg drawtext
    safe_headline = headline.replace("'", "").replace(":", "").strip()

    attempts = 0
    max_attempts = 3  # Aumentado para permitir múltiplos fixes (Thumb + Headline)
    auditor = DesignAuditor()
    current_font_size_override = None
    current_headline_fontsize = 95 if len(safe_headline) <= 15 else 70
    audit_results = {}
    output_file = None

    # Gerar nome base uma vez
    if "thumb_hook" in locals() and thumb_hook:
        base_name = (
            thumb_hook.replace(" ", "-")
            .replace("?", "")
            .replace("!", "")
            .replace(".", "")
            .upper()
        )
    elif safe_headline:
        base_name = (
            safe_headline.replace(" ", "-")
            .replace("?", "")
            .replace("!", "")
            .replace(".", "")
            .upper()
        )
    else:
        base_name = f"{input_video.stem}_V4_3"

    video_id_seed = input_video.stem.split("_cut_")[-1]
    final_name = f"{base_name}_C{video_id_seed}"
    output_file = output_dir / f"{final_name}.mp4"
    thumb_path = output_dir / f"{final_name}_thumb.jpg"

    while attempts < max_attempts:
        logger.info(f"--- Tentativa {attempts + 1} de exportação: {final_name} ---")

        # Re-montar filtros do FFmpeg para permitir mudanças de fonte na Headline
        video_filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
        ]

        # Adicionar Legendas ASS (Karaoke)
        if ass_path and ass_path.exists():
            ass_str = str(ass_path).replace("\\", "/")
            video_filters.append(f"subtitles={ass_str}")

        # Adicionar Headline com fonte atual (pode ser reduzida no auto-fix)
        if safe_headline:
            drawtext_filter = (
                f"drawtext=text='{safe_headline}':fontcolor=white:fontsize={current_headline_fontsize}:font='Arial Black':"
                f"borderw=4:bordercolor=black@0.8:shadowx=6:shadowy=6:shadowcolor=black@0.8:"
                f"x=(w-text_w)/2:y=220"
            )
            video_filters.append(drawtext_filter)

            watermark_filter = (
                "drawtext=text='v4.3':fontcolor=white@0.5:fontsize=32:font='Arial':"
                "x=w-text_w-40:y=40:borderw=1:bordercolor=black@0.3"
            )
            video_filters.append(watermark_filter)

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

        try:
            # 1. Exportar Vídeo (Forçar se for uma tentativa de Auto-Fix)
            if attempts > 0 or not output_file.exists():
                process = subprocess.run(cmd, capture_output=True, text=True)
                if process.returncode != 0:
                    raise RuntimeError(f"FFmpeg falhou: {process.stderr}")

            # 2. Lógica de Thumbnail
            dynamic_timestamp = "00:00:01"
            th_zoom_level = 1.0
            th_vignette = False
            best_frame_path = None

            if "cut_data" in locals() and cut_data.get("speakers"):
                relative_start = max(
                    0, cut_data["speakers"][0]["start"] - cut_data["start"]
                )
                th_strategy = cut_data.get("thumbnail_strategy", {})
                peak_offset = float(th_strategy.get("peak_action_offset", 1.5))
                th_zoom_level = float(th_strategy.get("zoom_level", 1.0))
                th_vignette = bool(th_strategy.get("vignette", False))

                target_time = min(
                    cut_data["duration"] * 0.9, relative_start + peak_offset
                )

                # Computer Vision Frame Selection
                candidate_frame = output_dir / f"{output_file.stem}_cv_temp.jpg"
                if extract_best_frame(output_file, candidate_frame, target_time):
                    best_frame_path = candidate_frame

                td = timedelta(seconds=target_time)
                dynamic_timestamp = f"{int(td.total_seconds() // 3600):02d}:{int((td.total_seconds() % 3600) // 60):02d}:{int(td.total_seconds() % 60):02d}.{int(td.microseconds / 1000):03d}"

            generate_thumbnail(
                output_file,
                thumb_path,
                text=thumb_hook if "thumb_hook" in locals() else headline,
                extraction_timestamp=dynamic_timestamp,
                zoom_level=th_zoom_level,
                vignette=th_vignette,
                bg_image_path=best_frame_path,
                primary_color=th_primary if "th_primary" in locals() else "#FFFF00",
                secondary_color=th_secondary
                if "th_secondary" in locals()
                else "#FF0000",
                font_size_override=current_font_size_override,
            )

            audit_results = auditor.run_audit(
                video_id=output_file.stem,
                video_path=output_file,
                thumb_path=thumb_path,
                ass_path=ass_path,
                headline=safe_headline,
                headline_fontsize=current_headline_fontsize,
                transcript_path=transcript_path,
                youtube_title=youtube_title,
                thumb_hook=thumb_hook,
                cut_start=cut_data["start"],
            )

            if audit_results.get("is_approved"):
                logger.info(
                    f"✅ Short APROVADO (Score: {audit_results['overall_score']})"
                )
                break
            else:
                logger.warning(
                    f"❌ Short REPROVADO (Score: {audit_results['overall_score']}) - Motivo: {audit_results.get('recommendations', ['Erro desconhecido'])[0]}"
                )

            # Auto-Fix
            if attempts < max_attempts - 1:
                thumb_data = audit_results.get("thumbnail", {})
                thumb_score = thumb_data.get("score", 0)
                thumb_collision = thumb_data.get("has_collision", False)

                graphics_issues = audit_results.get("graphics", {}).get("issues", [])
                graphics_collision = any(
                    "colis" in issue.lower() for issue in graphics_issues
                )

                logger.info(
                    f"DEBUG AUTO-FIX: thumb_collision={thumb_collision}, graphics_collision={graphics_collision}, graphics_issues={graphics_issues}"
                )

                # 1. Prioridade: Corrigir Colisões (Textos que vazam)
                fixed_something = False

                if thumb_collision:
                    # Se não há override, o padrão é 230/200. Começamos reduzindo.
                    if current_font_size_override is None:
                        current_font_size_override = (
                            190 if len(safe_headline) <= 12 else 170
                        )
                    else:
                        current_font_size_override = int(
                            current_font_size_override * 0.85
                        )
                    logger.info(
                        f"Auto-Fix: Colisão na thumbnail. Reduzindo fonte para {current_font_size_override}"
                    )
                    fixed_something = True

                # 2. Secundário: Aumentar visibilidade APENAS se o problema for falta clara de área de texto
                # e nunca revertendo um encolhimento de colisão (Evita Pingue-Pongue de 170 -> 260)
                elif thumb_data.get("text_area_score", 10) < 5 and not thumb_collision:
                    if (
                        current_font_size_override is None
                        or current_font_size_override < 200
                    ):
                        current_font_size_override = 230
                        logger.info(
                            "Auto-Fix: Aumentando fonte da thumbnail para 230 (score de área baixo)"
                        )
                        fixed_something = True

                # Checar Graphic Collision independente da Thumbnail
                if graphics_collision:
                    # Reduzir fonte da headline em 15%
                    current_headline_fontsize = int(current_headline_fontsize * 0.85)
                    logger.info(
                        f"Auto-Fix: Headline muito larga. Reduzindo para {current_headline_fontsize}px"
                    )
                    fixed_something = True

                if not fixed_something:
                    logger.warning(
                        "Não há auto-fix óbvio para as falhas detectadas (Provavelmente falta rosto na imagem)."
                    )
                    break

            attempts += 1
        except Exception as e:
            logger.error(f"Erro no loop de exportação: {e}")
            break

    # Cleanup
    if ass_path and ass_path.exists():
        try:
            ass_path.unlink()
        except:
            pass
    if best_frame_path and best_frame_path.exists():
        try:
            best_frame_path.unlink()
        except:
            pass

    return output_file, audit_results


def batch_export(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    profile_settings: Optional[dict] = None,
    target_count: int = 3,
) -> List[Path]:
    """Exporta vídeos garantindo uma cota de aprovados."""
    config = load_config()
    if input_dir is None:
        input_dir = Path(config["paths"]["output"])

    cut_videos = list(input_dir.glob("*_cut_*.mp4"))
    if not cut_videos:
        logger.warning(f"Nenhum vídeo cortado encontrado em {input_dir}")
        return []

    # Ordenar por Score de IA se disponível ou apenas processar
    logger.info(
        f"Iniciando Batch Export com Gatekeeper. Meta: {target_count} aprovados."
    )

    approved_files = []

    for video in cut_videos:
        if len(approved_files) >= target_count:
            logger.info(f"Meta de {target_count} shorts atingida. Pulando restantes.")
            break

        try:
            output_file, audit = export_to_shorts(
                video, output_dir, profile_settings=profile_settings
            )

            if audit.get("is_approved"):
                approved_files.append(output_file)
                logger.info(f"Produção Progress: {len(approved_files)}/{target_count}")
                logger.info(f"✅ VÍDEO APROVADO NO GATEKEEPER: {output_file.name}")
            else:
                logger.error(f"❌ VÍDEO REPROVADO NO GATEKEEPER: {output_file.name}")
                logger.error(
                    f"Razão: {audit.get('reasons', ['Audit score below threshold'])}"
                )

                # MOVER PARA QUARENTENA
                q_dir = quarantine_video(
                    output_file, reason=" | ".join(audit.get("reasons", []))
                )
                if q_dir:
                    logger.warning(f"⚠️  Vídeo movido para QUARENTENA: {q_dir}")

                if "recommendations" in audit:
                    print(f"\n💡 RECOMENDAÇÕES:\n{audit['recommendations']}")
        except Exception as e:
            logger.error(f"Erro ao processar {video.name}: {e}")
            continue

    return approved_files


def run_autonomous_export(profile_settings: Optional[dict] = None) -> List[Path]:
    """Exporta cortes pendentes usando o banco de dados Supabase."""
    from scripts.utils import supabase_client

    config = load_config()
    input_dir = Path(config["paths"]["output"])

    logger.info("Modo autônomo. Buscando cortes pendentes no Supabase...")
    pending_cuts = supabase_client.get_cuts_by_status("pending")

    if not pending_cuts:
        logger.info("Nenhum corte 'pending' aguardando exportação no banco.")
        return []

    approved_files = []

    for cut in pending_cuts:
        video_code = cut.get("videos", {}).get("video_code")
        cut_index = cut.get("cut_index")

        if not video_code:
            continue

        video = input_dir / f"{video_code}_cut_{cut_index:02d}.mp4"
        if not video.exists():
            logger.warning(
                f"Arquivo físico não encontrado para o corte {video_code}_{cut_index:02d}. mp4 ausente em {input_dir}"
            )
            continue

        logger.info(f"Processando corte pendente: {video.name}")

        try:
            output_file, audit = export_to_shorts(
                video, profile_settings=profile_settings
            )

            if audit and not audit.get("is_approved", False):
                logger.error(f"❌ VÍDEO REPROVADO NO GATEKEEPER: {output_file.name}")
                q_dir = quarantine_video(
                    output_file,
                    reason=" | ".join(
                        audit.get("reasons", audit.get("recommendations", []))
                    ),
                )
                supabase_client.update_cut_status(video_code, cut_index, "quarantined")
                if q_dir:
                    logger.warning(f"⚠️  Vídeo movido para QUARENTENA: {q_dir}")
                if "recommendations" in audit:
                    print(f"\n💡 RECOMENDAÇÕES:\n{audit['recommendations']}")
            else:
                approved_files.append(output_file)
                overall_score = audit.get("overall_score") if audit else None
                viral_potential = audit.get("viral_potential") if audit else None

                # Marca como exportado
                supabase_client.update_cut_status(video_code, cut_index, "exported")
                supabase_client.register_export(
                    video_code=video_code,
                    cut_index=cut_index,
                    filepath=str(output_file.absolute()),
                    overall_score=overall_score,
                    viral_potential=viral_potential,
                    gatekeeper_approved=True,
                )
                logger.info(
                    f"✅ Exportação registrada no Supabase e finalizada: {output_file.name}"
                )

        except Exception as e:
            logger.error(f"Erro ao processar autonômo {video.name}: {e}")
            supabase_client.update_cut_status(video_code, cut_index, "failed")
            continue

    return approved_files


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
            f"Detectado arquivo de análise: {args.video}. Exportando cortes do vídeo..."
        )
        try:
            import json as _json

            analysis_path = Path(args.video)
            with open(analysis_path, "r", encoding="utf-8") as _f:
                _analysis = _json.load(_f)

            video_id = _analysis["video_id"]
            config = load_config()
            output_dir = Path(config["paths"]["output"])
            shorts_dir = Path(config["paths"]["data_root"]) / "shorts"

            # Buscar cortes do video_id em data/output/
            cut_files = sorted(output_dir.glob(f"{video_id}_cut_*.mp4"))
            if not cut_files:
                logger.error(f"Nenhum corte encontrado em {output_dir} para {video_id}")
                sys.exit(1)

            logger.info(f"Encontrados {len(cut_files)} corte(s) para {video_id}")
            output_files = []
            for cut in cut_files:
                out_file, audit = export_to_shorts(
                    cut, output_dir=shorts_dir, profile_settings=settings
                )
                output_files.append(out_file)

            logger.info(f"Exportação concluída: {len(output_files)} short(s) gerados.")
            return
        except Exception as e:
            logger.error(f"Erro fatal: {e}", exc_info=True)
            sys.exit(1)
    elif args.video:
        video_path = Path(args.video)
        videos_to_export = [video_path]
    else:
        # Padrão: autônomo baseado no Supabase
        logger.info(
            f"Modo padrão com perfil '{args.profile}': exportando cortes pendentes no Supabase..."
        )
        try:
            output_files = run_autonomous_export(profile_settings=settings)
            print(f"\n✓ Processamento autônomo concluído!")
            print(f"Total de Shorts aprovados: {len(output_files)}")

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
        from scripts.tools.video_quarantine import quarantine_video

        for video_path in videos_to_export:
            logger.info(f"Processando com perfil '{args.profile}': {video_path}")
            output_file, audit = export_to_shorts(video_path, profile_settings=settings)

            size_mb = output_file.stat().st_size / (1024 * 1024)

            if audit and not audit.get("is_approved", False):
                logger.error(f"❌ VÍDEO REPROVADO NO GATEKEEPER: {output_file.name}")
                q_dir = quarantine_video(
                    output_file,
                    reason=" | ".join(
                        audit.get("reasons", audit.get("recommendations", []))
                    ),
                )
                print(f"\n❌ Short REPROVADO e enviado para quarentena!")
                if q_dir:
                    print(f"Quarentena: {q_dir}")
            else:
                print(f"\n✓ Short criado com sucesso!")
                print(f"Arquivo: {output_file}")
                print(f"Tamanho: {size_mb:.1f} MB")

        print(f"\n✓ Processamento de vídeos individuais concluído!")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
