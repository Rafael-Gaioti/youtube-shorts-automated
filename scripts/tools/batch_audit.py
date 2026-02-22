import sys
import os
from pathlib import Path
import logging

# Adicionar raiz ao path para encontrar scripts.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from scripts.tools.design_auditor import DesignAuditor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("BatchAudit")


def run_batch():
    shorts_dir = Path("data/shorts")
    if not shorts_dir.exists():
        logger.error(f"Diretório não encontrado: {shorts_dir}")
        return

    auditor = DesignAuditor()

    # Pegar todos os MP4 que não sejam temporários
    videos = [v for v in shorts_dir.glob("*.mp4") if "cv_temp" not in v.name]
    logger.info(f"🚀 Iniciando Auditoria em Lote: {len(videos)} vídeos encontrados.")

    for video_path in videos:
        # Thumbnail padrão segue o padrão do pipeline
        thumb_path = video_path.with_name(f"{video_path.stem}_thumb.jpg")

        # Se não existir a thumb específica, tenta a thumb genérica (caso o nome tenha mudado)
        if not thumb_path.exists():
            logger.warning(
                f"⚠️ Thumbnail específica não encontrada para {video_path.name}. Pulando."
            )
            continue

        try:
            logger.info(f"--- Auditando: {video_path.name} ---")
            auditor.run_audit(
                video_id=video_path.stem, video_path=video_path, thumb_path=thumb_path
            )
        except Exception as e:
            logger.error(f"❌ Erro crítico ao auditar {video_path.name}: {e}")

    logger.info(
        "✅ Batch Audit Concluído. Verifique o arquivo 'data/audit_ledger.csv'."
    )


if __name__ == "__main__":
    run_batch()
