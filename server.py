"""
FastAPI Server & Background Job Daemon for SaaS Automation.
Allows 24/7 autonomous processing on CPU VPS.
"""

import os
import sys
import time
import logging
import argparse
import subprocess
import threading
import platform
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Adicionar raiz ao python path para os scripts locais
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from scripts.utils import supabase_client
from scripts.utils.supabase_client import get_supabase_client

# Configurar logging para o servidor
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - SERVER - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/server.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("SERVER")

# Dicionário de tarefas ativas locais (video_code -> info_dict)
active_tasks: Dict[str, Dict[str, Any]] = {}
active_tasks_lock = threading.Lock()

app = FastAPI(
    title="Shorts Automated - SaaS API Server",
    description="Servidor API FastAPI e Daemon de fila para VPS.",
    version="1.0.0",
)

# Permitir CORS para que o frontend Next.js se conecte de qualquer lugar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    url: str
    profile: str = "recommended"


def get_video_code_from_url(url: str) -> Optional[str]:
    """Extrai o ID de 11 caracteres do YouTube a partir da URL."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def terminate_process(pid: int):
    """Interrompe o processo e toda a sua árvore de subprocessos de forma limpa."""
    try:
        if platform.system() == "Windows":
            # Força o encerramento do processo e todos os subprocessos filhos (/T)
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            # Envia SIGKILL para o grupo de processos
            import signal
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception as e:
        logger.warning(f"Erro ao terminar processo {pid}: {e}")


class SaaSQueueDaemon(threading.Thread):
    """Daemon em segundo plano que processa vídeos sequencialmente a partir do Supabase."""

    def __init__(self, max_concurrent: int = 1, check_interval_sec: int = 10, profile: str = "recommended"):
        super().__init__()
        self.daemon = True
        self.max_concurrent = max_concurrent
        self.check_interval_sec = check_interval_sec
        self.profile = profile
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        logger.info(
            f"🤖 Queue Daemon iniciado (Concorrência máx: {self.max_concurrent}, Intervalo: {self.check_interval_sec}s, Perfil: {self.profile})"
        )
        while self.running:
            try:
                # 1. Limpeza/Reaper: Verificar se os processos ativos terminaram
                self._reap_finished_processes()

                # 2. Verificar cota de concorrência
                with active_tasks_lock:
                    current_active_count = len(active_tasks)

                if current_active_count < self.max_concurrent:
                    # 3. Buscar vídeo descoberto pendente no Supabase
                    videos_pendentes = supabase_client.get_videos_by_stage("discovered")
                    
                    # Filtrar apenas os que não estão atualmente ativos localmente
                    queued_videos = []
                    for v in videos_pendentes:
                        v_code = v.get("video_code")
                        with active_tasks_lock:
                            is_active = v_code in active_tasks
                        if not is_active:
                            queued_videos.append(v)

                    if queued_videos:
                        next_video = queued_videos[0]
                        self._start_pipeline_job(next_video)

            except Exception as e:
                logger.error(f"Erro no ciclo do Queue Daemon: {e}", exc_info=True)

            time.sleep(self.check_interval_sec)

    def _reap_finished_processes(self):
        """Verifica quais processos terminaram, limpa o dicionário e atualiza o Supabase se necessário."""
        finished_tasks = []

        with active_tasks_lock:
            for video_code, info in active_tasks.items():
                proc = info["process"]
                poll_result = proc.poll()
                if poll_result is not None:
                    # Processo terminou!
                    finished_tasks.append((video_code, poll_result))

        for video_code, return_code in finished_tasks:
            logger.info(f"Processamento do vídeo {video_code} terminou com código de retorno {return_code}")
            
            with active_tasks_lock:
                if video_code in active_tasks:
                    del active_tasks[video_code]

            # Se falhou e o estágio ainda não foi marcado como failed, atualizar
            if return_code != 0:
                # Verificar estágio atual
                client = get_supabase_client()
                if client:
                    try:
                        res = client.table("videos").select("stage").eq("video_code", video_code).execute()
                        data = res.data if hasattr(res, 'data') else res[1]
                        if data and data[0]["stage"] not in ["exported", "uploaded", "failed"]:
                            supabase_client.update_video_stage(
                                video_code, 
                                "failed", 
                                error_log=f"Processo terminado inesperadamente (Exit Code: {return_code})."
                            )
                    except Exception as e:
                        logger.error(f"Erro ao verificar estágio final do vídeo {video_code}: {e}")

    def _start_pipeline_job(self, video_data: dict):
        """Inicializa a execução assíncrona do script pipeline.py para o vídeo indicado."""
        video_code = video_data.get("video_code")
        url = video_data.get("url")
        title = video_data.get("title", video_code)

        logger.info(f"🚀 Iniciando processamento do vídeo: {title} ({video_code})")

        # Atualiza o estágio no Supabase para 'downloading' imediatamente para avisar o dashboard
        supabase_client.update_video_stage(video_code, "downloading")

        # Monta comando do subprocesso
        python_exe = sys.executable
        cmd = [python_exe, "pipeline.py", "--url", url, "--profile", self.profile]

        # Configurar ambiente com PYTHONPATH para resolução de imports
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

        try:
            # Spawna de forma não-bloqueante
            if platform.system() == "Windows":
                # CREATE_NEW_PROCESS_GROUP para isolar árvore de processos no Windows
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # os.setsid para isolar grupo de processos no Linux/Mac
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    preexec_fn=os.setsid
                )

            with active_tasks_lock:
                active_tasks[video_code] = {
                    "process": proc,
                    "url": url,
                    "title": title,
                    "started_at": datetime.now().isoformat(),
                }
            logger.info(f"Subprocesso iniciado com sucesso para {video_code} (PID: {proc.pid})")

        except Exception as e:
            logger.error(f"Erro ao iniciar subprocesso para o vídeo {video_code}: {e}")
            supabase_client.update_video_stage(video_code, "failed", error_log=f"Falha ao iniciar processo: {e}")


@app.get("/")
def read_root():
    """Retorna o estado geral e status do servidor."""
    with active_tasks_lock:
        tasks_copy = {
            k: {
                "title": v["title"],
                "started_at": v["started_at"],
                "pid": v["process"].pid,
            }
            for k, v in active_tasks.items()
        }

    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "platform": platform.system(),
        "active_jobs_count": len(tasks_copy),
        "active_jobs": tasks_copy,
        "supabase_connection": get_supabase_client() is not None,
    }


@app.post("/api/process")
def process_video(request: ProcessRequest):
    """
    Submete um vídeo para processamento. 
    Insere o vídeo no Supabase e deixa o Daemon lidar com a fila.
    """
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL vazia.")

    video_code = get_video_code_from_url(url)
    if not video_code:
        raise HTTPException(status_code=400, detail="Formato de URL do YouTube inválido.")

    logger.info(f"Recebida requisição de processamento para: {url} (ID: {video_code})")

    # Registrar no Supabase no estágio inicial 'discovered'
    video_id = supabase_client.register_discovered_video(
        video_code=video_code,
        url=url,
        title=f"Vídeo de Fila ({video_code})",
        channel="Fila Web"
    )

    if not video_id:
        # Se falhar o registro por rede ou restrição, verificar se já existe no banco
        client = get_supabase_client()
        if client:
            try:
                res = client.table("videos").select("id, stage").eq("video_code", video_code).execute()
                data = res.data if hasattr(res, 'data') else res[1]
                if data:
                    # Se já existia e estava em falha, resetar para 'discovered' para re-tentar
                    if data[0]["stage"] == "failed":
                        supabase_client.update_video_stage(video_code, "discovered", error_log="")
                        return {
                            "status": "re-queued",
                            "video_code": video_code,
                            "message": "Tarefa resetada na fila com sucesso."
                        }
                    return {
                        "status": "already_exists",
                        "video_code": video_code,
                        "stage": data[0]["stage"],
                        "message": "Este vídeo já está cadastrado ou em processamento."
                    }
            except Exception as e:
                logger.error(f"Erro ao buscar vídeo existente: {e}")

        raise HTTPException(status_code=500, detail="Erro ao registrar vídeo no Supabase.")

    return {
        "status": "queued",
        "video_code": video_code,
        "message": "Vídeo adicionado à fila do SaaS com sucesso."
    }


@app.get("/api/active-tasks")
def get_active_tasks():
    """Retorna a lista de tarefas rodando na CPU da VPS."""
    with active_tasks_lock:
        return {
            "active_tasks_count": len(active_tasks),
            "tasks": [
                {
                    "video_code": k,
                    "title": v["title"],
                    "url": v["url"],
                    "started_at": v["started_at"],
                    "pid": v["process"].pid,
                }
                for k, v in active_tasks.items()
            ],
        }


@app.get("/api/status/{video_code}")
def get_video_status(video_code: str):
    """Consulta o status em tempo real do processamento de um vídeo no Supabase."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=503, detail="Supabase indisponível.")

    try:
        # Buscar dados do vídeo
        video_res = client.table("videos").select("*").eq("video_code", video_code).execute()
        video_data = video_res.data if hasattr(video_res, 'data') else video_res[1]

        if not video_data:
            raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

        video = video_data[0]

        # Buscar cortes gerados se existirem
        cuts_res = client.table("cuts").select("*").eq("video_id", video["id"]).execute()
        cuts_data = cuts_res.data if hasattr(cuts_res, 'data') else cuts_res[1]

        # Verificar se está ativo localmente
        with active_tasks_lock:
            is_active = video_code in active_tasks
            task_info = active_tasks[video_code] if is_active else None

        return {
            "video_code": video_code,
            "title": video["title"],
            "stage": video["stage"],
            "is_running_locally": is_active,
            "local_task_details": {
                "started_at": task_info["started_at"] if task_info else None,
                "pid": task_info["process"].pid if task_info else None,
            } if is_active else None,
            "error_log": video["error_log"],
            "cuts_count": len(cuts_data),
            "cuts": cuts_data,
            "updated_at": video["updated_at"],
        }
    except Exception as e:
        logger.error(f"Erro ao consultar status do vídeo {video_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cancel/{video_code}")
def cancel_task(video_code: str):
    """Cancela e encerra o processador ativo de um vídeo."""
    info = None
    with active_tasks_lock:
        if video_code in active_tasks:
            info = active_tasks[video_code]

    if not info:
        raise HTTPException(
            status_code=404, 
            detail="Processo não encontrado ou já finalizado na CPU local."
        )

    proc = info["process"]
    logger.warning(f"Recebida requisição de cancelamento para: {video_code} (PID: {proc.pid})")
    
    # Executa encerramento forçado do processo
    terminate_process(proc.pid)

    # Limpa dicionário local
    with active_tasks_lock:
        if video_code in active_tasks:
            del active_tasks[video_code]

    # Atualiza Supabase
    supabase_client.update_video_stage(
        video_code, 
        "failed", 
        error_log="Cancelado manualmente pelo usuário através do endpoint de API."
    )

    return {
        "status": "cancelled",
        "video_code": video_code,
        "message": f"Processamento interrompido. PID {proc.pid} encerrado."
    }


def main():
    parser = argparse.ArgumentParser(description="Shorts Automated Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="IP do host bind")
    parser.add_argument("--port", type=int, default=8000, help="Porta TCP do servidor")
    parser.add_argument("--profile", type=str, default="recommended", help="Perfil de processamento")
    parser.add_argument("--concurrency", type=int, default=1, help="Vídeos concorrentes")
    args = parser.parse_args()

    # Inicializar e disparar o Queue Daemon em segundo plano
    daemon = SaaSQueueDaemon(
        max_concurrent=args.concurrency, 
        check_interval_sec=10, 
        profile=args.profile
    )
    daemon.start()

    logger.info(f"Starting server web API at http://{args.host}:{args.port}")
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        logger.info("Encerrando Queue Daemon...")
        daemon.stop()
        daemon.join(timeout=5)


if __name__ == "__main__":
    main()
