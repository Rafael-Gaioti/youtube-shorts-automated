import sys
import subprocess
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# O log por vídeo é configurado dentro do main() após extrair o video_id
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - PIPELINE - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
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
        "--url",
        type=str,
        default=None,
        help="URL do YouTube para processar diretamente",
    )
    parser.add_argument(
        "--urls-file",
        type=str,
        default=None,
        help="Arquivo de texto com uma URL por linha para processar em batch",
    )
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
    parser.add_argument(
        "--force-analyze",
        action="store_true",
        help="Forçar re-análise mesmo se já existir analysis.json com cortes",
    )
    parser.add_argument(
        "--force-cut",
        action="store_true",
        help="Forçar re-corte mesmo se os arquivos de corte já existirem",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Fazer upload dos shorts ao YouTube após o export (requer 6_upload.py)",
    )
    parser.add_argument(
        "--upload-privacy",
        type=str,
        default="private",
        choices=["private", "unlisted", "public"],
        help="Privacidade dos vídeos no upload (padrão: private)",
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

    # Coletar URLs para processar
    urls_to_process = []
    if args_parsed.url:
        urls_to_process.append(args_parsed.url)
    if args_parsed.urls_file:
        urls_file = Path(args_parsed.urls_file)
        if not urls_file.exists():
            logger.error(f"Arquivo de URLs não encontrado: {urls_file}")
            return
        with open(urls_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls_to_process.append(line)

    # -------------------------------------------------------------------------
    # MODO DIRETO: --url / --urls-file
    # -------------------------------------------------------------------------
    if urls_to_process:
        import re

        total = len(urls_to_process)
        for idx_url, url in enumerate(urls_to_process, 1):
            if total > 1:
                logger.info(f"\n--- URL {idx_url}/{total}: {url} ---")
            logger.info(f"Modo direto: processando URL {url}")

            # Extrair video_id da URL do YouTube
            match = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
            if not match:
                logger.error(f"Não foi possível extrair video_id da URL: {url}")
                if total > 1:
                    continue
                return
            video_id = match.group(1)
            logger.info(f"Video ID: {video_id}")

            # Configurar log por vídeo
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_log = log_dir / f"{video_id}_{ts}.log"
            file_handler = logging.FileHandler(video_log, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            logging.getLogger().addHandler(file_handler)
            logger.info(f"Log salvo em: {video_log}")

            # Verificar se já foi baixado
            raw_video = Path(f"data/raw/{video_id}.mp4")
            if raw_video.exists():
                logger.info(f"Vídeo já baixado: {raw_video}. Pulando download.")
            else:
                if not run_script("1_download.py", [url]):
                    logger.error("Falha no download. Abortando.")
                    continue

            # Transcrever
            transcript_path = Path(f"data/transcripts/{video_id}_transcript.json")
            if transcript_path.exists():
                logger.info(
                    f"Transcript já existe: {transcript_path}. Pulando transcrição."
                )
            else:
                transcribe_args = [str(raw_video), "--profile", args_parsed.profile]
                if args_parsed.min_speakers:
                    transcribe_args += ["--min-speakers", str(args_parsed.min_speakers)]
                if not run_script("2_transcribe.py", transcribe_args):
                    logger.error("Falha na transcrição. Abortando.")
                    continue

            # Analisar — pular se já existe com cortes válidos (exceto --force-analyze)
            analysis_path = Path(f"data/analysis/{video_id}_analysis.json")
            analysis_has_cuts = False
            if analysis_path.exists() and not args_parsed.force_analyze:
                try:
                    import json as _json

                    _a = _json.load(open(analysis_path, "r", encoding="utf-8"))
                    analysis_has_cuts = len(_a.get("cuts", [])) > 0
                except Exception:
                    pass

            if analysis_has_cuts:
                logger.info(
                    "Analysis com cortes já existe. Pulando análise (use --force-analyze para re-analisar)."
                )
            else:
                if not run_script(
                    "3_analyze.py",
                    [str(transcript_path), "--profile", args_parsed.profile],
                ):
                    logger.error("Falha na análise. Abortando.")
                    continue

            # Cortar — pular se os arquivos de corte já existem (exceto --force-cut)
            existing_cuts = list(Path("data/output").glob(f"{video_id}_cut_*.mp4"))
            if existing_cuts and not args_parsed.force_cut:
                logger.info(
                    f"{len(existing_cuts)} corte(s) já existem. Pulando 4_cut.py (use --force-cut para re-cortar)."
                )
            else:
                if not run_script(
                    "4_cut.py", [str(analysis_path), "--profile", args_parsed.profile]
                ):
                    logger.error("Falha no corte. Abortando.")
                    continue

            # Exportar
            if not run_script(
                "5_export.py", [str(analysis_path), "--profile", args_parsed.profile]
            ):
                logger.error("Falha na exportação. Abortando.")
                continue

            # Upload (opcional, requer --upload)
            if args_parsed.upload:
                logger.info("Iniciando upload para o YouTube...")
                upload_args = [
                    str(analysis_path),
                    "--privacy",
                    args_parsed.upload_privacy,
                ]
                if not run_script("6_upload.py", upload_args):
                    logger.warning(
                        "Upload falhou — shorts salvos localmente em data/shorts/"
                    )

            # Sumário final do vídeo
            shorts_dir = Path("data/shorts")
            # Tentar padrão clássico e padrão human-readable (hook)
            generated = sorted(shorts_dir.glob(f"{video_id}_cut_*_short.mp4"))
            if not generated:
                # Busca por arquivos que terminam com _C01.mp4, _C02.mp4 etc.
                generated = sorted(shorts_dir.glob(f"*_C[0-9][0-9].mp4"))
                # Filtrar apenas os que pertencem a este vídeo se possível,
                # mas o pattern de exportação do 5_export.py já os torna únicos o suficiente
                # ou busca por arquivos que foram criados recentemente para este vídeo
            logger.info("")
            logger.info(f"{'=' * 55}")
            logger.info(f"  PIPELINE CONCLUÍDA — {video_id}")
            logger.info(f"{'=' * 55}")
            if generated:
                try:
                    with open(analysis_path, "r", encoding="utf-8") as f:
                        _analysis = json.load(f)
                    cuts = _analysis.get("cuts", [])
                    for i, short in enumerate(generated):
                        size_mb = short.stat().st_size / (1024 * 1024)
                        score = cuts[i]["viral_score"] if i < len(cuts) else "?"
                        hook_s = (
                            cuts[i].get("hook_strength", "?") if i < len(cuts) else "?"
                        )
                        logger.info(f"  [{i + 1}] {short.name}")
                        logger.info(
                            f"       Viral: {score}/10  Hook: {hook_s}/10  Tamanho: {size_mb:.1f} MB"
                        )
                except Exception:
                    for i, short in enumerate(generated):
                        size_mb = short.stat().st_size / (1024 * 1024)
                        logger.info(f"  [{i + 1}] {short.name} ({size_mb:.1f} MB)")
            else:
                logger.info("  Nenhum short encontrado no diretório data/shorts/")
            logger.info(f"  Log: {video_log}")
            logger.info(f"{'=' * 55}")

            # Remover handler do log por vídeo para não duplicar nas próximas URLs
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()

        return

    # -------------------------------------------------------------------------
    # MODO CANAL: usa discovery_queue.json (comportamento original)
    # -------------------------------------------------------------------------

    # Carregar Profile
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
