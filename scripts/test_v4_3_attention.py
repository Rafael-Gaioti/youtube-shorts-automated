import sys
from pathlib import Path
import json
import logging

# Adicionar o diretório atual ao sys.path para importar scripts locais
sys.path.append(str(Path(__file__).parent.parent))

from scripts.tools.thumbnail_generator import generate_thumbnail

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestV4.3")


def run_test():
    # Caminhos
    video_id = "X51KsjOa41E"
    video_path = Path(f"data/shorts/{video_id}_cut_01_short.mp4")
    analysis_path = Path(f"data/analysis/{video_id}_analysis.json")
    output_dir = Path("data/shorts/test_v4_3")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists() or not analysis_path.exists():
        logger.error("Arquivos de teste não encontrados.")
        return

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    # Simular o índice 0 (corte 01)
    cut_data = analysis["cuts"][0]

    # Testar 3 tipos de conteúdo diferentes
    tests = [
        {"type": "fear_mistake", "hook": "ERRO FATAL", "label": "fear"},
        {"type": "success_wealth", "hook": "FICOU RICO", "label": "success"},
        {"type": "mystery_revelation", "hook": "O SEGREDO", "label": "mystery"},
    ]

    for test in tests:
        content_type = test["type"]
        hook = test["hook"]
        label = test["label"]

        # Lógica de cores (copiada do 5_export.py)
        th_primary = "#FFFF00"
        th_secondary = "#FF0000"

        if (
            "fear" in content_type
            or "mistake" in content_type
            or "danger" in content_type
        ):
            th_primary, th_secondary = "#FFFFFF", "#FF0000"
        elif (
            "success" in content_type
            or "money" in content_type
            or "wealth" in content_type
        ):
            th_primary, th_secondary = "#FFFF00", "#00FF00"
        elif (
            "mystery" in content_type
            or "secret" in content_type
            or "revelation" in content_type
        ):
            th_primary, th_secondary = "#00FFFF", "#FF00FF"

        thumb_path = output_dir / f"test_{label}_thumb.jpg"

        logger.info(
            f"Gerando thumbnail para {label} ({content_type}) com cores {th_primary}/{th_secondary}"
        )

        generate_thumbnail(
            video_path,
            thumb_path,
            text=hook,
            extraction_timestamp="00:00:01.000",
            zoom_level=1.2,
            vignette=True,
            primary_color=th_primary,
            secondary_color=th_secondary,
        )

    logger.info(f"Testes concluídos em {output_dir}")


if __name__ == "__main__":
    run_test()
