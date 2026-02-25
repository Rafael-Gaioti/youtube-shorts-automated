"""
Master Orchestrator: master_pipeline.py
Executa a esteira COMPLETA: Discovery -> Download -> Pipeline (Transcribe/Analyze/Cut/Export).
"""

import subprocess
import logging
import sys
import os
from scripts.utils.supabase_client import get_videos_by_stage

# Garantir pasta de logs antes do logging iniciar
os.makedirs("data/logs", exist_ok=True)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/logs/master_pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("MASTER_PIPELINE")


def run_script(script_name: str, args: list = None):
    """Executa um script Python na pasta scripts/."""
    logger.info(f"\n{'=' * 20} INICIANDO: {script_name} {'=' * 20}")

    script_path = os.path.join("scripts", script_name)

    # Resolve interpretador
    python_exe = sys.executable

    cmd = [python_exe, script_path]
    if args:
        cmd.extend(args)

    # Configurar ambiente com PYTHONPATH para resolver scripts.utils
    env = os.environ.copy()
    root_dir = os.getcwd()
    env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            universal_newlines=True,
            env=env,
        )

        # Stream output em tempo real para o log
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                logger.info(f"[{script_name}] {clean_line}")
                print(f"[{script_name}] {clean_line}")

        process.wait()

        if process.returncode != 0:
            logger.error(f"❌ Erro em {script_name} (Exit Code: {process.returncode})")
            return False

        logger.info(f"✅ Sucesso: {script_name}")
        return True
    except Exception as e:
        logger.error(f"💥 Exceção ao rodar {script_name}: {e}")
        return False


def main():
    # Garantir pasta de logs
    os.makedirs("data/logs", exist_ok=True)

    logger.info("🚀 Iniciando Master Pipeline Autônomo...")

    # 1. Discovery (Encontra vídeos virais)
    if not run_script("0_discover.py"):
        sys.exit(1)

    # 2. Download (Baixa o que foi descoberto)
    if not run_script("1_download.py"):
        sys.exit(1)

    # 3. Transcrição (Whisper GPU)
    transcripts_to_process = get_videos_by_stage("downloaded")
    from scripts.utils.supabase_client import update_video_stage

    for video in transcripts_to_process:
        logger.info(f"🎤 [Master] Transcrevendo: {video['video_code']}...")
        update_video_stage(video["video_code"], "transcribing")
        if run_script("2_transcribe.py", ["--video_id", video["video_code"]]):
            # 2_transcribe.py internally updates to transcribed
            pass
        else:
            update_video_stage(video["video_code"], "failed", "Erro na transcrição")

    # 4. Análise com IA (Filtro JIT - Just In Time)
    transcribed_videos = get_videos_by_stage("transcribed")
    if transcribed_videos:
        logger.info(f"🧠 [Master] {len(transcribed_videos)} vídeos aguardando análise.")

        analyzed_count = 0
        DAILY_ANALYSIS_QUOTA = 3  # Limite de vídeos "caros" por ciclo

        for video in transcribed_videos:
            if analyzed_count >= DAILY_ANALYSIS_QUOTA:
                logger.info(
                    f"⏸️ Cota de análise atingida. {video['video_code']} aguardará."
                )
                break

            logger.info(f"🔍 [Master] Analisando (JIT): {video['video_code']}...")
            if run_script("3_analyze.py", ["--video_id", video["video_code"]]):
                # 3_analyze.py updates to analyzed
                analyzed_count += 1
            else:
                update_video_stage(video["video_code"], "failed", "Erro na análise")

    # 5. Corte e Exportação
    for step in ["4_cut.py", "5_export.py"]:
        if not run_script(step):
            logger.error(f"🛑 Interrompendo Master Pipeline em {step}")
            sys.exit(1)

    logger.info("🏆 MASTER PIPELINE FINALIZADO COM SUCESSO!")
    logger.info("#" * 60)

    # 4. Smart Hibernate (Optional - only if woken by timer)
    run_script("utils/smart_hibernate.py")


if __name__ == "__main__":
    main()
