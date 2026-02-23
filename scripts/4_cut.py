"""
Script 4: Corte de Vídeos
Extrai os segmentos identificados pela análise usando FFmpeg.
"""

import sys
import json
import logging
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from dotenv import load_dotenv

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


def cut_video(
    video_path: Path, analysis_path: Path, output_dir: Optional[Path] = None
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
        output_dir = Path(config["paths"]["output"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanetização: Remover cortes antigos deste vídeo para evitar desalinhamento com a nova análise
    video_id = video_path.stem
    old_cuts = list(output_dir.glob(f"{video_id}_cut_*.mp4"))
    if old_cuts:
        logger.info(
            f"Limpando {len(old_cuts)} cortes antigos de {video_id} em {output_dir}"
        )
        for old_cut in old_cuts:
            try:
                old_cut.unlink()
            except Exception as e:
                logger.warning(f"Não foi possível remover {old_cut}: {e}")

    # Carregar análise
    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    cuts = analysis_data.get("cuts", [])
    if not cuts:
        logger.warning("Nenhum corte encontrado na análise")
        return []

    logger.info(f"Processando {len(cuts)} cortes do vídeo: {video_path.name}")

    output_files = []

    for i, cut in enumerate(cuts, 1):
        start_time = cut["start"]
        end_time = cut["end"]
        duration = end_time - start_time

        # Nome do arquivo de saída
        output_file = output_dir / f"{video_path.stem}_cut_{i:02d}.mp4"

        logger.info(
            f"Corte {i}/{len(cuts)}: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s)"
        )

        # Comando FFmpeg para corte preciso com re-encode
        # O re-encode é necessário para garantir que o vídeo comece EXATAMENTE no start_time (frame-accurate)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time),
            "-i",
            str(video_path),
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_file),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"✓ Salvo (Re-encode preciso): {output_file.name}")
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
    analysis_dir = Path(config["paths"]["analysis"])
    raw_dir = Path(config["paths"]["raw_videos"])

    analyses = list(analysis_dir.glob("*_analysis.json"))
    if not analyses:
        raise FileNotFoundError(f"Nenhuma análise encontrada em {analysis_dir}")

    # Pega a análise mais recente
    latest_analysis = max(analyses, key=lambda p: p.stat().st_mtime)

    # Carrega para pegar o video_id
    with open(latest_analysis, "r", encoding="utf-8") as f:
        data = json.load(f)

    video_id = data["video_id"]

    # Procura o vídeo correspondente
    video_path = raw_dir / f"{video_id}.mp4"

    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    return video_path, latest_analysis


def run_autonomous_cuts():
    """Runs cuts for all pending cuts in Supabase autonomously."""
    from scripts.utils import supabase_client

    logger.info("Modo autônomo. Buscando todos os cortes pendentes no Supabase...")
    pending_cuts = supabase_client.get_cuts_by_status("pending")

    if not pending_cuts:
        logger.info("Nenhum corte pendente de edição ('pending') no banco.")
        return

    config = load_config()
    raw_dir = Path(config["paths"]["raw_videos"])
    output_dir = Path(config["paths"]["output"])
    output_dir.mkdir(parents=True, exist_ok=True)

    for cut in pending_cuts:
        video_code = cut.get("videos", {}).get("video_code")
        title = cut.get("videos", {}).get("title")
        cut_index = cut.get("cut_index")
        start_time = cut.get("start_time")
        end_time = cut.get("end_time")
        duration = end_time - start_time

        if not video_code:
            logger.warning(
                f"Corte {cut.get('id')} não possui relacionamento com vídeo associado."
            )
            continue

        video_path = raw_dir / f"{video_code}.mp4"
        if not video_path.exists():
            logger.error(f"Vídeo fonte não encontrado na raw_videos: {video_path}")
            continue

        output_file = output_dir / f"{video_code}_cut_{cut_index:02d}.mp4"
        logger.info(
            f"==> Iniciando corte automático: {title} ({video_code} - Corte {cut_index})"
        )
        logger.info(f"    Tempo: {float(start_time):.1f}s - {float(end_time):.1f}s")

        # Remove version antiga do cut para evitar sujeira
        if output_file.exists():
            output_file.unlink()

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(float(start_time)),
            "-i",
            str(video_path),
            "-t",
            str(float(duration)),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_file),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"[SUCCESS] Corte gerado: {output_file.name}")
            # Do NOT update status here, let 5_export do it.
        except subprocess.CalledProcessError as e:
            logger.error(f"Erro no FFmpeg ao gerar {output_file.name}: {e}")
            logger.error(f"Stderr: {e.stderr}")
            supabase_client.update_cut_status(video_code, cut_index, "failed")

    logger.info("\n✓ Fila de cortes concluída!")
    print(f"\nProximo passo: python scripts/5_export.py")
    sys.exit(0)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Corte de vídeos virais.")
    parser.add_argument("video_path", nargs="?", help="Caminho para o vídeo")
    parser.add_argument("analysis_path", nargs="?", help="Caminho para a análise")
    parser.add_argument(
        "--latest", action="store_true", help="Usa a análise mais recente"
    )
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil do usuário (SaaS)"
    )
    args = parser.parse_args()

    if args.latest:
        logger.info("Buscando análise e vídeo mais recentes (Modo Legacy)...")
        video_path, analysis_path = find_latest_analysis()
    elif args.video_path and args.analysis_path:
        video_path = Path(args.video_path)
        analysis_path = Path(args.analysis_path)
    elif args.analysis_path:  # Se passou apenas um, assume que é a análise
        analysis_path = Path(args.analysis_path)
        with open(analysis_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = load_config()
        raw_dir = Path(config["paths"]["raw_videos"])
        video_path = raw_dir / f"{data['video_id']}.mp4"
    else:
        run_autonomous_cuts()

    try:
        logger.info(f"Vídeo: {video_path}")
        logger.info(f"Análise: {analysis_path}")

        output_files = cut_video(video_path, analysis_path)

        # Se usou formato standalone, não atualizamos o BD mais daqui
        # O 5_export.py se encarrega disso.

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
