import cv2
import mediapipe as mp
import math
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def distance(p1, p2, width, height):
    x1, y1 = p1.x * width, p1.y * height
    x2, y2 = p2.x * width, p2.y * height
    return math.hypot(x1 - x2, y1 - y2)


def calculate_mar(landmarks, width, height):
    """
    Calcula o Mouth Aspect Ratio (MAR) usando os pontos internos dos lábios do MediaPipe FaceMesh.
    """
    # Índices dos lábios internos:
    top = landmarks[13]
    bottom = landmarks[14]
    left = landmarks[78]
    right = landmarks[308]

    vertical_dist = distance(top, bottom, width, height)
    horizontal_dist = distance(left, right, width, height)

    if horizontal_dist == 0:
        return 0
    return vertical_dist / horizontal_dist


def extract_best_frame(
    video_path: Path,
    output_image_path: Path,
    target_timestamp_sec: float,
    search_window_sec: float = 3.0,
    fps_sample: int = 10,
) -> bool:
    """
    Busca o frame mais expressivo na janela dada usando MediaPipe.
    O foco é capturar o momento exato em que o locutor abre a boca (impacto).

    video_path: Caminho do vídeo
    output_image_path: Onde salvar o JPG
    target_timestamp_sec: O momento do Hook/Início (segundos)
    search_window_sec: Janela foca em buscar para frente (para pegar a respiração e ataque à frase)
    fps_sample: Avaliar N frames por segundo para não onerar CPU.
    """
    logger.info(
        f"Ocular Attention Engine: Scanning {video_path.name} próximo a {target_timestamp_sec}s"
    )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"Erro ao abrir video {video_path} via OpenCV")
        return False

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30

    # Começa tentar escanear 0.5s antes do corte para prevenir drift de edição
    start_sec = max(0.0, target_timestamp_sec - 0.5)
    end_sec = target_timestamp_sec + search_window_sec

    # Seek via MSEC
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)

    step_frames = max(1, int(fps / fps_sample))

    # Tentar usar MediaPipe de forma resiliente
    face_mesh = None
    try:
        import mediapipe as mp

        # Tenta várias formas de acesso aos submódulos
        mp_face_mesh = None
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
            mp_face_mesh = mp.solutions.face_mesh

        if mp_face_mesh:
            face_mesh = mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.4,
            )
            logger.info("IA de Visão Computacional ATIVA.")
    except Exception:
        logger.warning("IA Visual offline. Usando extração de frame direta.")

    best_score = -1.0
    best_frame = None

    if face_mesh:
        current_frame_idx = 0
        while True:
            pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            if pos_msec / 1000.0 > end_sec:
                break

            ret, frame = cap.read()
            if not ret:
                break

            if current_frame_idx % step_frames == 0:
                h, w = frame.shape[:2]
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)

                score = 0.0
                if results.multi_face_landmarks:
                    landmarks = results.multi_face_landmarks[0].landmark
                    mar = calculate_mar(landmarks, w, h)
                    score = mar
                else:
                    score = -1.0

                if score > best_score:
                    best_score = score
                    best_frame = frame.copy()

            current_frame_idx += 1
        face_mesh.close()
    else:
        # FALLBACK: Pega o frame exatamente no target_time
        cap.set(cv2.CAP_PROP_POS_MSEC, target_timestamp_sec * 1000.0)
        ret, best_frame = cap.read()
        if ret:
            logger.info(f"Capturado frame estático em {target_timestamp_sec}s")

    cap.release()

    if best_frame is not None:
        cv2.imwrite(str(output_image_path), best_frame)
        return True

    logger.warning("Falha ao capturar frame de qualquer fonte.")
    return False

    if best_frame is not None:
        cv2.imwrite(str(output_image_path), best_frame)
        logger.debug(
            f"✅ Frame dinâmico matador salvo com MAR (Mouth Aspect Ratio): {best_score:.4f}"
        )
        return True

    logger.warning("Nenhum frame ótimo capturado ou vídeo corrompido.")
    return False


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Video path")
    parser.add_argument("output", help="Output JPG path")
    parser.add_argument("timestamp", type=float, help="Timestamp in seconds")
    args = parser.parse_args()

    extract_best_frame(Path(args.video), Path(args.output), args.timestamp)
