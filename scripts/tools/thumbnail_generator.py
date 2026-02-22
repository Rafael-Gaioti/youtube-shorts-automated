import sys
import os
import argparse
import logging
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

# Evitar ModuleNotFoundError no import abaixo, caso seja chamado direto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


def extract_frame(
    video_path: Path, output_image_path: Path, timestamp: str = "00:00:03"
) -> bool:
    """Extrai um frame especifico do video usando FFmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        timestamp,
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(output_image_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_image_path.exists()
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Erro FFmpeg ao extrair frame: {e.stderr.decode('utf-8', errors='ignore')}"
        )
        return False
    except Exception as e:
        logger.error(f"Erro ao extrair frame: {e}")
        return False


def generate_thumbnail(
    video_path: Path,
    output_path: Path,
    text: str,
    font_name: str = "arialbd.ttf",  # Arial Bold no Windows
    primary_color: str = "#FFFF00",  # Amarelo
    secondary_color: str = "#FF0000",  # Vermelho
    extraction_timestamp: str = "00:00:03",
    zoom_level: float = 1.0,
    vignette: bool = False,
    bg_image_path: Optional[Path] = None,
    font_size_override: Optional[int] = None,
) -> Optional[Path]:
    """
    Gera uma thumbnail para Short vertical (9:16).
    Extrai frame dinâmico, aplica composição avançada (Crop/Vignette/Blur) e tipologia colossal.
    """
    logger.info(f"Gerando thumbnail para: {video_path.name}")

    if bg_image_path and bg_image_path.exists():
        temp_frame = bg_image_path
        logger.info(f"Usando OpenCV base frame inteligente: {bg_image_path.name}")
    else:
        temp_frame = output_path.with_name(f"{output_path.stem}_temp_bg.jpg")
        logger.info(f"Extraindo via FFmpeg asilo: T={extraction_timestamp}")
        if not extract_frame(video_path, temp_frame, timestamp=extraction_timestamp):
            logger.error("Falha ao extrair frame base para thumbnail.")
            return None

    try:
        # 2. Processar background no Pillow
        with Image.open(temp_frame) as img:
            width, height = img.size

            # Psycho-Visuals: Zoom Dinâmico
            if zoom_level > 1.0:
                new_width = int(width / zoom_level)
                new_height = int(height / zoom_level)
                left = (width - new_width) / 2
                top = (height - new_height) / 2
                right = (width + new_width) / 2
                bottom = (height + new_height) / 2
                img = img.crop((left, top, right, bottom))
                img = img.resize((width, height), Image.Resampling.LANCZOS)

            # Psycho-Visuals: Vignette Radial asfixiante
            if vignette:
                mask = Image.new("L", (width, height), 255)  # Branco = Escurece
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse(
                    (width * 0.05, height * 0.1, width * 0.95, height * 0.9), fill=0
                )  # Preto = Livre central
                mask = mask.filter(
                    ImageFilter.GaussianBlur(radius=150)
                )  # Transição suave maciça
                black_layer = Image.new("RGB", (width, height), (0, 0, 0))
                img = Image.composite(black_layer, img, mask)

            # Escurecer 30% (suave para não matar a expressão)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.7 if vignette else 0.75)

            # Aplicar Gaussian Blur sutil (V4.2: Reduzido para não perder o sentido do frame)
            blur_intensity = 6 if zoom_level > 1.0 else 3
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_intensity))

            draw = ImageDraw.Draw(img)

            # 3. Configurar Fonte (Tamanhos colossais V5, ~60% da tela)
            font_size = (
                font_size_override
                if font_size_override
                else (230 if len(text) <= 12 else 200)
            )
            try:
                font = ImageFont.truetype(font_name, font_size)
            except IOError:
                logger.warning(
                    f"Fonte {font_name} não encontrada. Trocando pro fallback."
                )
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except IOError:
                    font = ImageFont.load_default()

            # 4. Quebra de linha (Wrap agressivo para Max 2-3 linhas)
            max_chars = 8 if font_size >= 230 else 10
            lines = textwrap.wrap(text.upper(), width=max_chars)[
                :3
            ]  # Aumentado para 3 linhas se necessário para ocupar mais área

            line_spacing = int(font_size * 0.22)
            # Altura total estimada para a caixa de texto
            # Usando textbbox para calcular precisamente no Pillow 10+
            total_text_height = sum(
                (
                    draw.textbbox((0, 0), line, font=font)[3]
                    - draw.textbbox((0, 0), line, font=font)[1]
                )
                for line in lines
            ) + line_spacing * (len(lines) - 1)

            # Centralizar na tela verticalmente
            # Colocamos exato no meio matemático da thumbnail
            start_y = (height - total_text_height) // 2

            # 5. Iterar pelas linhas e desenhar
            current_y = start_y
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                line_height = bbox[3] - bbox[1]
                x = (width - line_width) // 2

                # Coisa similar ao n8n: linha index 1 vermelha, outras amarelas
                color = secondary_color if i == 1 else primary_color

                # Scale stroke_width & shadow by font_size dynamically
                stroke_width = 8 if font_size >= 195 else 6
                stroke_fill = "black"

                # Sombra (Drope shadow massivo)
                shadow_offset = 12 if font_size >= 195 else 8
                shadow_color = "black"
                draw.text(
                    (x + shadow_offset, current_y + shadow_offset),
                    line,
                    font=font,
                    fill=shadow_color,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill,
                )

                # Texto principal
                draw.text(
                    (x, current_y),
                    line,
                    font=font,
                    fill=color,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill,
                )

                current_y += line_height + line_spacing

            # Adicionar Marca d'Água Técnica V4.3 (Canto superior direito)
            try:
                # Tentar carregar fonte, senão usa Default
                try:
                    wm_font = ImageFont.truetype("arial.ttf", 40)
                except:
                    wm_font = ImageFont.load_default()

                wm_text = "v4.3"
                wm_bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
                wm_w = wm_bbox[2] - wm_bbox[0]

                # Posição: Canto superior direito com margem de 50px
                draw.text(
                    (width - wm_w - 50, 50),
                    wm_text,
                    font=wm_font,
                    fill=(255, 255, 255, 128),  # Branco semi-transparente
                    stroke_width=1,
                    stroke_fill="black",
                )
            except Exception as wm_e:
                logger.warning(f"Erro ao adicionar watermark na thumb: {wm_e}")

            img.save(output_path, "JPEG", quality=95)
            logger.info(f"✓ Thumbnail criada: {output_path.name}")
            return output_path

    except Exception as e:
        logger.error(f"Erro ao desenhar texto no Pillow: {e}")
        return None
    finally:
        if temp_frame.exists() and (
            bg_image_path is None or temp_frame != bg_image_path
        ):
            try:
                temp_frame.unlink()
            except:
                pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser("Thumbnail Generator CLI")
    parser.add_argument("video", help="Caminho pro video input")
    parser.add_argument("text", help="Texto do hook na thumbnail")
    parser.add_argument("--output", help="Arquivo saida (.jpg)", default=None)
    args = parser.parse_args()

    vid_path = Path(args.video)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = vid_path.with_name(f"{vid_path.stem}_thumb.jpg")

    generate_thumbnail(vid_path, out_path, args.text)
