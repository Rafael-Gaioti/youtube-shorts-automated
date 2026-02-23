import sys
import os
from pathlib import Path
import logging

# Adicionar path para importar os módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from scripts.tools.thumbnail_generator import generate_thumbnail
from scripts.tools.design_auditor import DesignAuditor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_rendering():
    test_cases = [
        {"text": "MULTIPLIQUE GANHOS", "output": "test_multiplique.jpg"},
        {"text": "INCONSTITUCIONALMENTE LONGO", "output": "test_long.jpg"},
        {"text": "EVITE A FALÊNCIA AGORA", "output": "test_falencia.jpg"},
        {"text": "NÃO CAIA NESSA ARMADILHA", "output": "test_armadilha.jpg"},
    ]

    # Usar um vídeo fake ou existente para a extração (ou apenas o generator com bg_image se tivéssemos)
    # Como o generator extrai do vídeo, precisamos de um vídeo real ou passar bg_image_path

    # Procurar qualquer vídeo em data/raw ou data/exports para usar como base
    video_base = None
    raw_dir = Path("data/raw")
    if raw_dir.exists():
        videos = list(raw_dir.glob("*.mp4"))
        if videos:
            video_base = videos[0]

    if not video_base:
        logger.error(
            "Nenhum vídeo encontrado para teste. Crie a pasta data/raw com um vídeo .mp4."
        )
        return

    output_dir = Path("data/tests")
    output_dir.mkdir(parents=True, exist_ok=True)

    auditor = DesignAuditor()

    for case in test_cases:
        out_path = output_dir / case["output"]
        logger.info(f"Testando: {case['text']}")

        # Gerar thumbnail
        result = generate_thumbnail(
            video_path=video_base,
            output_path=out_path,
            text=case["text"],
            vignette=True,
        )

        if result:
            # Auditar thumbnail
            audit = auditor.analyze_thumbnail(out_path)
            logger.info(f"Audit Score: {audit['score']}")
            if audit.get("issues"):
                logger.warning(f"Issues: {audit['issues']}")
            else:
                logger.info("✓ Sem problemas detectados no audit.")
        else:
            logger.error(f"Falha ao gerar thumbnail para: {case['text']}")


if __name__ == "__main__":
    test_rendering()
