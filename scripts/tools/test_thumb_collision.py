import sys
import os
from pathlib import Path
import logging

# Adicionar o diretório raiz ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.tools.thumbnail_generator import generate_thumbnail
from scripts.tools.design_auditor import DesignAuditor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_collision():
    video_path = Path("data/videos/NUBANK-SECRETO.mp4")  # Exemplo
    # Se o video não existir, usaremos um placeholder ou falharemos
    if not video_path.exists():
        # Procurar qualquer video em data/shorts
        videos = list(Path("data/shorts").glob("*.mp4"))
        if videos:
            video_path = videos[0]
        else:
            logger.error("Nenhum vídeo encontrado em data/shorts.")
            return

    output_thumb = Path("data/test_collision_thumb.jpg")
    text = "ESTE É UM TEXTO MUITO LONGO QUE CERTAMENTE VAI COLIDIR COM AS BORDAS"

    logger.info(f"Gerando thumbnail de teste com fonte padrão (230/200)...")
    generate_thumbnail(video_path, output_thumb, text)

    auditor = DesignAuditor()
    results = auditor.analyze_thumbnail(output_thumb)

    logger.info(f"Resultados da Auditoria:")
    logger.info(f"Score: {results['score']}")
    logger.info(f"Colisão: {results['has_collision']}")
    logger.info(f"Issues: {results['issues']}")

    if results["has_collision"]:
        logger.info("✅ SUCESSO: Colisão detectada corretamente.")
    else:
        logger.error("❌ FALHA: Colisão NÃO detectada.")


if __name__ == "__main__":
    test_collision()
