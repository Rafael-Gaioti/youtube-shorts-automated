"""
Orchestration Script: run_pipeline.py
Executa a cadeia principal de geração de shorts em modo autônomo.
"""

import subprocess
import logging
import sys

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_script(script_name: str):
    """Executa um script Python e verifica retorno."""
    logger.info(f"==== Iniciando {script_name} ====")
    try:
        # Usa o mesmo interpretador atual
        result = subprocess.run(
            [sys.executable, f"scripts/{script_name}"],
            check=True,
            capture_output=False,  # Mostra o output no terminal de forma unificada
        )
        logger.info(f"==== {script_name} finalizado ====\n")
    except subprocess.CalledProcessError as e:
        logger.error(f"Erro ao executar {script_name}. Interrompendo pipeline.")
        sys.exit(1)


def main():
    logger.info("Iniciando Pipeline Autônomo de Processamento...")

    # Executa a esteira em ordem.
    # Os scripts já foram modificados para rodar em modo autônomo caso não tenham argumentos.
    run_script("2_transcribe.py")
    run_script("3_analyze.py")
    run_script("4_cut.py")
    run_script("5_export.py")

    logger.info(
        "Pipeline executado com sucesso! Os vídeos exportados aguardam em 'data/output/shorts'."
    )


if __name__ == "__main__":
    main()
