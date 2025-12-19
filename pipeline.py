import os
import sys
import subprocess
import json
import logging
from pathlib import Path

# Configuração de Logging para a Pipeline
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - 🚀 PIPELINE - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pipeline_execution.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def run_script(script_name: str, args: list = []) -> bool:
    """Executa um script Python da pasta 'scripts' e retorna se teve sucesso."""
    script_path = Path("scripts") / script_name
    cmd = [sys.executable, str(script_path)] + args

    logger.info(f"Executando: {' '.join(cmd)}")
    try:
        # Usamos check=True para que ele lance exceção em caso de erro
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Erro ao executar {script_name}: {e}")
        return False


def main():
    logger.info("=== INICIANDO PIPELINE DE AUTOMAÇÃO DE SHORTS ===")

    # 1. DESCOBERTA (0_discover.py)
    # Sempre busca o que há de novo nos canais monitorados
    if not run_script("0_discover.py"):
        logger.error("Falha na etapa de descoberta. Abortando.")
        return

    # Carregar a fila de vídeos encontrados
    queue_path = Path("data/discovery_queue.json")
    if not queue_path.exists():
        logger.info("Nenhum vídeo novo para processar.")
        return

    with open(queue_path, "r", encoding="utf-8") as f:
        video_queue = json.load(f)

    if not video_queue:
        logger.info("Fila de descoberta está vazia.")
        return

    logger.info(f"Encontrados {len(video_queue)} vídeos para processar.")

    # 2. PROCESSAMENTO INDIVIDUAL
    # Processamos um por um para evitar sobrecarga e garantir logs limpos
    processed_count = 0

    # Vamos trabalhar em uma cópia da fila para poder remover os processados
    queue_to_process = list(video_queue)

    for video in queue_to_process:
        url = video["url"]
        video_id = video["id"]
        logger.info(
            f"[{processed_count + 1}/{len(video_queue)}] Processando: {video['title']} ({video_id})"
        )

        try:
            # Etapa 1: Download
            if not run_script("1_download.py", [url]):
                continue

            # Etapa 2: Transcrição (Whisper)
            # O download_path é data/raw/{video_id}.mp4 conforme settings.yaml
            if not run_script("2_transcribe.py", [f"data/raw/{video_id}.mp4"]):
                continue

            # Etapa 3: Análise de Viralidade (Llama 3/Ollama)
            if not run_script(
                "3_analyze.py", [f"data/transcripts/{video_id}_transcript.json"]
            ):
                continue

            # Etapa 4: Corte Automático
            if not run_script("4_cut.py", ["--latest"]):
                continue

            # Etapa 5: Exportação para Shorts (Crop 9:16 + Headlines + Legendas)
            if not run_script("5_export.py", ["--latest"]):
                continue

            logger.info(f"✅ Sucesso total para o vídeo: {video_id}")
            processed_count += 1

        except Exception as e:
            logger.error(f"Erro crítico no processamento do vídeo {video_id}: {e}")
            continue

    # Limpar a fila após o processamento (opcional, já que o DB de descoberta evita duplicatas)
    # Mas é bom para manter a pasta 'data' organizada
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    logger.info(
        f"=== PIPELINE FINALIZADA. {processed_count} vídeos processados com sucesso! ==="
    )


if __name__ == "__main__":
    main()
