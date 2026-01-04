import sys
import subprocess
import json
import logging
import argparse
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
    parser = argparse.ArgumentParser(description="Pipeline de Automação de Shorts")
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil de usuário (SaaS)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limite total de vídeos a processar"
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=None,
        help="Duração máxima em MINUTOS (override)",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=None,
        help="Forçar número mínimo de oradores (Diarização)",
    )
    args_parsed = parser.parse_args()

    # Inicializar Logger
    logger = logging.getLogger("PIPELINE")

    # --- AUTO-VENV FIX ---
    # Se não estiver rodando no venv, tenta re-executar usando o python do .venv
    if sys.prefix == sys.base_prefix:
        venv_python = Path.cwd() / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            logger.info(
                f"Detectado execução fora do venv. Reiniciando com: {venv_python}"
            )
            # Re-executar o script atual com o python do venv
            # Passamos todos os argumentos originais
            subprocess.call([str(venv_python), __file__] + sys.argv[1:])
            sys.exit(0)
        else:
            logger.warning(
                "Venv não detectado em .venv/Scripts/python.exe. Pode haver erros de dependência."
            )

    logger.info(
        f"=== INICIANDO PIPELINE DE AUTOMAÇÃO DE SHORTS (PERFIL: {args_parsed.profile}) ==="
    )

    # Carregar Profile
    # The instruction implies a refactor to a settings_manager module.
    # To maintain functionality without introducing new undefined modules,
    # I will adapt the existing profile loading logic to match the structure implied by the instruction.
    # This means keeping the file-based loading but assigning to profile_data and handling errors similarly.
    profile_name = args_parsed.profile
    profiles_path = Path("config/user_profiles.json")

    try:
        if not profiles_path.exists():
            raise FileNotFoundError(
                f"Arquivo de perfis não encontrado em {profiles_path}"
            )

        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)

        if profile_name not in profiles:
            raise ValueError(f"Perfil '{profile_name}' não encontrado.")

        profile_data = profiles[profile_name]
        logger.info(
            f"Configurações carregadas: {profile_data.get('name', 'Desconhecido')}"
        )
    except Exception as e:
        logger.error(f"Erro ao carregar perfil: {e}")
        return

    # 1. DESCOBERTA DE VÍDEOS
    # Sempre busca o que há de novo nos canais monitorados
    discover_args = ["--profile", profile_name]
    if args_parsed.limit:
        discover_args += ["--limit", str(args_parsed.limit)]
    if args_parsed.max_duration:
        discover_args += ["--max-duration", str(args_parsed.max_duration)]

    if not run_script("0_discover.py", discover_args):
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

    # Limitar a fila conforme o argumento --limit
    if args_parsed.limit:
        video_queue = video_queue[: args_parsed.limit]
        logger.info(f"Fila limitada a {args_parsed.limit} vídeos.")

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
            transcribe_args = [f"data/raw/{video_id}.mp4", "--profile", profile_name]
            if args_parsed.min_speakers:
                transcribe_args += ["--min-speakers", str(args_parsed.min_speakers)]

            if not run_script("2_transcribe.py", transcribe_args):
                continue

            # Verificar se a transcrição realmente existe
            transcript_path = Path(f"data/transcripts/{video_id}_transcript.json")
            if not transcript_path.exists():
                continue

            # Etapa 3: Análise de Viralidade
            if not run_script(
                "3_analyze.py", [str(transcript_path), "--profile", profile_name]
            ):
                continue

            # Etapa 4: Corte Automático
            if not run_script("4_cut.py", ["--latest", "--profile", profile_name]):
                continue

            # Etapa 5: Exportação para Shorts (Passamos o JSON para forçar processamento de TODOS os cortes deste vídeo)
            analysis_json = Path(f"data/analysis/{video_id}_analysis.json")
            if not run_script(
                "5_export.py", [str(analysis_json), "--profile", profile_name]
            ):
                continue

            # ETAPA EXTRA: LIMPEZA DE ESPAÇO
            raw_video = Path(f"data/raw/{video_id}.mp4")
            if raw_video.exists():
                logger.info(f"🧹 Limpando espaço: Deletando vídeo bruto {video_id}.mp4")
                raw_video.unlink()

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
