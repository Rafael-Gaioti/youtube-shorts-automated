import cv2
import numpy as np
import json
import logging
import csv
from pathlib import Path
from scripts.utils.subtitle_qa import SubtitleAuditor
from scripts.tools.semantic_auditor import SemanticAuditor
from datetime import datetime
import yaml
from dotenv import load_dotenv
import os

try:
    import mediapipe as mp
except ImportError:
    mp = None

# Carregar variáveis de ambiente
load_dotenv()


# Carregar config central
def load_config():
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
logger = logging.getLogger(__name__)


class DesignAuditor:
    def __init__(
        self,
        ledger_path: str = "data/audit_ledger.csv",
        approval_threshold: float = 7.0,
    ):
        self.ledger_path = Path(ledger_path)
        self.approval_threshold = approval_threshold
        self.metrics = {}

    def _save_to_ledger(self, video_id: str, results: dict):
        """Append results to CSV ledger."""
        file_exists = self.ledger_path.exists()

        headers = [
            "timestamp",
            "video_id",
            "hook_score",
            "thumb_score",
            "subtitle_ratio",
            "rhythm_score",
            "is_approved",
            "viral_potential",
            "diagnosis",
        ]

        with open(self.ledger_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()

            writer.writerow(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "video_id": video_id,
                    "hook_score": results.get("hook", {}).get("score", 0),
                    "thumb_score": results.get("thumbnail", {}).get("score", 0),
                    "subtitle_ratio": results.get("subtitles", {}).get(
                        "emphasis_ratio", 0
                    ),
                    "rhythm_score": results.get("rhythm", {}).get("score", 0),
                    "is_approved": "YES" if results.get("is_approved") else "NO",
                    "viral_potential": results.get("viral_potential", "UNKNOWN"),
                    "diagnosis": results.get("diagnosis", "").replace("\n", " "),
                }
            )

    def analyze_thumbnail(self, image_path: Path):
        """Camada 1: Thumbnail (Text Area + Face Expression via MediaPipe)"""
        if not image_path.exists():
            return {"score": 0, "error": "file_not_found"}

        # Fix OpenCV UTF-8 path reading on Windows
        try:
            import numpy as np

            img_array = np.fromfile(str(image_path), np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception:
            img = None

        if img is None:
            return {"score": 0, "error": "invalid_image"}

        h, w = img.shape[:2]
        total_pixels = h * w

        # 1.1 Ocupação de Texto (Heurística de Cores/Bordas)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        kernel = np.ones((15, 15), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        occupied_pixels = np.sum(dilated > 0)
        occupation_ratio = occupied_pixels / total_pixels

        # Score de Ocupação (Ideal: 35-55%)
        occ_score = 10
        if occupation_ratio < 0.20:  # Mais complacente
            occ_score = 6
        elif occupation_ratio > 0.65:
            occ_score = 5
        elif 0.30 <= occupation_ratio <= 0.60:
            occ_score = 10

        # 1.2 Detecção de Colisão de Borda (Safe Zone Check)
        # Margens aumentadas para 12% nas laterais (espaço para botões/UI do Shorts)
        # e 10% topo/base
        margin_w = int(w * 0.12)
        margin_h = int(h * 0.10)

        has_collision = False
        issues = []

        # Encontrar contornos na máscara dilatada para isolar blocos de texto
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filtrar contornos muito pequenos (ruído ou UI residual do vídeo)
        # Consideramos um contorno "texto principal" se tiver área significativa (ex: > 1% da tela)
        min_text_area = (w * h) * 0.01

        # DEBUG IMAGE
        debug_img = img.copy()
        cv2.line(debug_img, (margin_w, 0), (margin_w, h), (0, 0, 255), 2)
        cv2.line(debug_img, (w - margin_w, 0), (w - margin_w, h), (0, 0, 255), 2)
        cv2.line(debug_img, (0, margin_h), (w, margin_h), (0, 0, 255), 2)
        cv2.line(debug_img, (0, h - margin_h), (w, h - margin_h), (0, 0, 255), 2)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > min_text_area:
                x, y, cw, ch = cv2.boundingRect(cnt)

                # Draw the bounding box
                cv2.rectangle(debug_img, (x, y), (x + cw, y + ch), (0, 255, 0), 3)

                # Checar se este bounding box invade as margens com uma pequena tolerância
                leak_tolerance_w = int(w * 0.015)
                leak_tolerance_h = int(h * 0.015)

                hits_left = x < (margin_w - leak_tolerance_w)
                hits_right = (x + cw) > (w - margin_w + leak_tolerance_w)
                hits_top = y < (margin_h - leak_tolerance_h)
                hits_bottom = (h - margin_h + leak_tolerance_h) < (y + ch)

                if hits_left or hits_right:
                    has_collision = True
                    occ_score -= 5
                    issues.append("Texto da thumbnail encostando nas bordas laterais")

                if hits_top or hits_bottom:
                    has_collision = True
                    occ_score -= 3
                    issues.append(
                        "Texto da thumbnail encostando no topo ou base (Safe Zone)"
                    )

                # HEURÍSTICA: Detecção de "Texto Estilhaçado" (Palavra cortada)
                # Se o bloco de texto for muito alto e estreito, pode ser uma letra ou sílaba isolada
                # Razão de aspecto (H/W) > 1.2 em um bloco pequeno é suspeito para o estilo colossal
                aspect_ratio = ch / cw if cw > 0 else 0
                if aspect_ratio > 1.2 and area < (w * h * 0.05):
                    occ_score -= 2
                    issues.append(
                        f"Possível palavra estilhaçada/cortada detectada (Aspect Ratio: {aspect_ratio:.1f})"
                    )

        cv2.imwrite("thumb_debug.jpg", debug_img)

        # 1.3 Expressividade Facial via MediaPipe
        face_score = 5
        mar = 0
        gaze_score = 0

        try:
            mp_face_mesh = None
            if mp:
                try:
                    import mediapipe.solutions.face_mesh as fm

                    mp_face_mesh = fm
                except ImportError:
                    if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
                        mp_face_mesh = mp.solutions.face_mesh

            if mp_face_mesh:
                with mp_face_mesh.FaceMesh(
                    static_image_mode=True, max_num_faces=1, refine_landmarks=True
                ) as face_mesh:
                    results = face_mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

                    if results.multi_face_landmarks:
                        landmarks = results.multi_face_landmarks[0].landmark

                        # Mouth Aspect Ratio (MAR)
                        top = landmarks[13]
                        bottom = landmarks[14]
                        left = landmarks[78]
                        right = landmarks[308]
                        v_dist = np.hypot(top.x - bottom.x, top.y - bottom.y)
                        h_dist = np.hypot(left.x - right.x, left.y - right.y)
                        mar = v_dist / h_dist if h_dist > 0 else 0

                        # Eye Gaze / Face orientation
                        nose = landmarks[1]
                        center_dist = np.hypot(nose.x - 0.5, nose.y - 0.5)
                        gaze_score = 10 - min(10, center_dist * 20)

                        face_score = 10 if mar > 0.08 else 7
                    else:
                        face_score = 0
                        logger.warning(f"Nenhum rosto detectado na thumb: {image_path}")
            else:
                logger.warning("MediaPipe FaceMesh fallback falhou.")
        except Exception as e:
            logger.warning(f"Erro no MediaPipe Audit: {e}")

        final_thumb_score = (occ_score * 0.6) + (face_score * 0.4)

        return {
            "occupation_ratio": round(occupation_ratio, 3),
            "text_area_score": occ_score,
            "mar": round(mar, 3),
            "face_score": face_score,
            "gaze_score": round(gaze_score, 1),
            "score": round(final_thumb_score, 1),
            "has_collision": has_collision,
            "issues": issues,
        }

    def analyze_rhythm(self, video_path: Path):
        """Camada 4: Ritmo Visual (Cuts Per Second + Motion Energy)"""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"score": 0}

        diffs = []
        prev_frame = None
        cuts = 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        frame_count = 0
        while frame_count < 300:  # Analisar 10s
            ret, frame = cap.read()
            if not ret:
                break

            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.GaussianBlur(curr_gray, (21, 21), 0)

            if prev_frame is not None:
                diff = cv2.absdiff(prev_frame, curr_gray)
                diff_score = np.mean(diff)
                diffs.append(diff_score)

                # Detectar Corte Visual (Mudança brusca de histograma/média)
                if diff_score > 15:  # Threshold de corte abrupto
                    cuts += 1

            prev_frame = curr_gray
            frame_count += 1

        cap.release()

        avg_motion = np.mean(diffs) if diffs else 0
        cps = cuts / (frame_count / fps) if frame_count > 0 else 0

        # Score de Ritmo: Motion > 3 e pelo menos 1 corte em 10s (dinâmico)
        rhythm_score = 5
        if avg_motion > 3:
            rhythm_score += 2
        if cps > 0.1:
            rhythm_score += 3

        return {
            "motion_energy": round(float(avg_motion), 3),
            "cuts_per_second": round(cps, 2),
            "score": min(10, rhythm_score),
        }

    def analyze_hook(self, video_path: Path):
        """Camada 2: O Hook (Silêncio e Ataque de Áudio nos primeiros 500ms)"""
        import subprocess
        import re

        # Analisar apenas os primeiros 0.5s
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-ss",
            "0",
            "-t",
            "0.5",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stderr

            # Buscar picos de volume
            max_vol = re.search(r"max_volume: ([\-\d\.]+) dB", output)
            mean_vol = re.search(r"mean_volume: ([\-\d\.]+) dB", output)

            max_val = float(max_vol.group(1)) if max_vol else -91
            mean_val = float(mean_vol.group(1)) if mean_vol else -91

            # Silêncio inicial? Se max_volume for muito baixo (ex: < -30dB), o hook começou mudo.
            silence_penalty = 0
            if max_val < -20:
                silence_penalty = 5

            hook_score = 10 - silence_penalty

            return {
                "max_volume_db": max_val,
                "mean_volume_db": mean_val,
                "score": hook_score,
            }
        except Exception as e:
            logger.warning(f"Erro no Hook Audit: {e}")
            return {"score": 5, "error": str(e)}

    def analyze_hook_text(self, transcript_path: Path, cut_start: float = 0.0):
        """Camada 2.1: Qualidade Semântica do Hook (As primeiras palavras são gatilhos?)"""
        if not transcript_path or not transcript_path.exists():
            return {"hook_text": "N/A", "has_filler": False}

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Pegar as palavras dos primeiros 3 segundos do corte
            # Suporta tanto análise direta (.json) quanto transcript whisper
            segments = data.get("segments", []) or data.get("results", [])
            first_words = []
            for seg in segments:
                start = seg.get("start", 0)
                # Verifica se o segmento começa logo após o início do corte (com margem de erro)
                if cut_start - 0.5 <= start <= cut_start + 3.0:
                    first_words.append(seg.get("text", ""))

            hook_text = " ".join(first_words).strip()

            # Heurística simples
            fillers = ["então", "bom", "olá", "pessoal", "tipo", "é...", "sabe"]
            has_filler = any(f in hook_text.lower() for f in fillers)

            return {
                "hook_text": hook_text[:100] if hook_text else "Vazio",
                "has_filler": has_filler,
                "score_impact": -2 if has_filler else 0,
            }
        except Exception:
            return {"hook_text": "Erro ao ler", "has_filler": False}

    def analyze_subtitles(self, ass_path: Path):
        """Camada 3: Legendas (Emphasis Ratio via parsing de .ass)"""
        if not ass_path.exists():
            return {"emphasis_ratio": 0, "score": 0}

        try:
            with open(ass_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Contar tags de cor \c&H ou \1c&H (independentemente de chaves {} para ser mais robusto)
            # Buscamos a sequência de escape do ASS
            emphasis_tags = content.count("\\c&H") + content.count("\\1c&H")

            # Estimar número de diálogos (linhas que começam com "Dialogue:")
            dialogue_lines = content.count("Dialogue:")

            # Ratio de ênfase (Tags por linha de diálogo)
            ratio = emphasis_tags / dialogue_lines if dialogue_lines > 0 else 0

            # Score (Ideal: 0.3 a 1.2 conforme novas diretrizes V5.1)
            sub_score = 10
            if ratio < 0.1:
                sub_score = 3  # Monótono demais
            elif ratio < 0.3:
                sub_score = 6
            elif ratio > 2.0:
                sub_score = 7  # Poluído demais

            return {
                "emphasis_ratio": round(ratio, 2),
                "dialogue_count": dialogue_lines,
                "score": sub_score,
            }
        except Exception as e:
            logger.warning(f"Erro no Subtitle Audit: {e}")
            return {"emphasis_ratio": 0, "score": 0}

    def analyze_graphics(
        self, video_path: Path, headline: str = "", headline_fontsize: int = None
    ):
        """Camada 5: Qualidade Gráfica In-Video (Legibilidade de Headline e Layout)"""
        results = {"headline_score": 10, "subtitle_layout_score": 10, "issues": []}

        # 1. Headline Legibility & Edge Collision
        if headline:
            word_count = len(headline.split())
            char_count = len(headline)

            # Penalidade por comprimento excessivo
            if word_count > 6:
                results["headline_score"] -= 3
                results["issues"].append("Headline muito longa (max 6 palavras)")

            if headline.isupper() is False:
                results["headline_score"] -= 1
                results["issues"].append("Headline não está em CAIXA ALTA")

            # Heurística de Colisão de Borda (Edge Collision)
            # Se não informado, tenta adivinhar pelo padrão v6.1
            if headline_fontsize is None:
                headline_fontsize = 95 if char_count <= 15 else 70

            estimated_w = char_count * (headline_fontsize * 0.7)

            if estimated_w > 1000:  # ~92% de 1080px (Largura do Short)
                results["headline_score"] -= 8  # Punição fatal
                results["issues"].append(
                    f"Risco CRÍTICO de colisão (Largura: {int(estimated_w)}px em FS {headline_fontsize})"
                )
            elif estimated_w > 950:  # ~88%
                results["headline_score"] -= 4
                results["issues"].append(
                    f"Risco ALTO de colisão de borda (Largura: {int(estimated_w)}px em FS {headline_fontsize})"
                )

        # 2. Layout Check
        results["score"] = (
            results["headline_score"] + results["subtitle_layout_score"]
        ) / 2
        return results

    def analyze_content_fidelity(self, transcript_path: Path, texts: list):
        """Camada 6: Fidelidade de Conteúdo (Evitar Alucinações em Títulos/Hooks)"""
        if not transcript_path or not transcript_path.exists() or not texts:
            return {"score": 10, "issues": []}

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extrair todas as palavras da transcrição
            transcript_text = ""
            segments = data.get("segments", [])
            for seg in segments:
                transcript_text += " " + seg.get("text", "")

            transcript_text = transcript_text.lower()

            hallucinated_words = set()
            import re

            for text in texts:
                if not text:
                    continue
                # Limpar texto e tokenizar
                clean_text = re.sub(r"[^\w\s]", "", text.lower())
                # Ignorar palavras funcionais curtas para evitar falsos positivos
                words = [w for w in clean_text.split() if len(w) > 3]

                for word in words:
                    if word not in transcript_text:
                        hallucinated_words.add(word)

            score = 10
            issues = []
            if hallucinated_words:
                # Penalidade severa: 5 pontos por palavra (2 palavras = falha total)
                penalty = len(hallucinated_words) * 5
                score = max(0, 10 - penalty)
                issues.append(
                    f"Palavras não encontradas no áudio: {', '.join(hallucinated_words)}"
                )

            return {
                "score": score,
                "hallucinated_words": list(hallucinated_words),
                "issues": issues,
            }
        except Exception as e:
            logger.warning(f"Erro no Content Fidelity Audit: {e}")
            return {"score": 5, "error": str(e)}

    def generate_llm_diagnosis(self, raw_results: dict):
        """Camada 4: Cérebro Audit (Removido LLM - Agora é Algorítmico 0 custo)"""
        try:
            # Forçar aprovação técnica baseada no threshold
            final_score = raw_results.get("overall_score", 0)
            is_approved = final_score >= self.approval_threshold

            # Análise de Viralidade baseada no Score Final
            if final_score >= 8.5:
                viral_potential = "HIGH"
            elif final_score >= 7.0:
                viral_potential = "MEDIUM"
            else:
                viral_potential = "LOW"

            # Recomendações Automáticas baseadas nas notas das subcamadas
            recommendations = []
            if raw_results.get("thumbnail", {}).get("score", 0) < 7.0:
                recommendations.append(
                    "A thumbnail precisa ser mais impactante ou sofre com colisão de texto."
                )
            if raw_results.get("hook", {}).get("score", 0) < 6.0:
                recommendations.append(
                    "O hook inicial (áudio) está muito silencioso ou sem impacto."
                )
            if dict(raw_results).get("subtitles", {}).get("score", 0) < 6.0:
                recommendations.append(
                    "A ênfase das legendas (cores) está monótona ou poluída."
                )
            if raw_results.get("rhythm", {}).get("score", 0) < 6.0:
                recommendations.append(
                    "O ritmo visual está devagar (pouca energia de movimento ou cortes)."
                )
            if raw_results.get("graphics", {}).get("headline_score", 10) < 5.0:
                is_approved = False  # Reprovação instantânea (Hard Fail)
                recommendations.append(
                    "O Texto do Header ultrapassou os limites e invadiu a borda da tela (Colisão Grave)."
                )

            if raw_results.get("fidelity", {}).get("score", 10) < 5.0:
                is_approved = False  # Hard Fail for hallucinations
                fidelity_issues = raw_results.get("fidelity", {}).get("issues", [])
                recommendations.append(
                    f"Headline inconsistente com o áudio: {fidelity_issues[0] if fidelity_issues else 'Alucinação detectada.'}"
                )

            if not recommendations:
                recommendations.append("Todas as métricas técnicas estão excelentes.")
                diagnosis_text = "Vídeo aprovado e pronto para publicação."
            else:
                diagnosis_text = "Vídeo com ressalvas. " + " ".join(recommendations)

            if not is_approved:
                diagnosis_text = "Reprovado pelo Gatekeeper. " + diagnosis_text

            diagnosis_data = {
                "diagnosis": diagnosis_text,
                "viral_potential": viral_potential,
                "recommendations": recommendations,
                "final_score": final_score,
                "is_approved": is_approved,
            }

            return diagnosis_data
        except Exception as e:
            logger.warning(f"Erro no Diagnosis Algorítmico: {e}")
            return {
                "diagnosis": "Erro ao gerar diagnóstico agorítmico.",
                "viral_potential": raw_results.get("viral_potential", "UNKNOWN"),
                "recommendations": [],
                "final_score": raw_results.get("overall_score", 0),
                "is_approved": False,
            }

    def run_audit(
        self,
        video_id: str,
        video_path: Path,
        thumb_path: Path,
        ass_path: Path = None,
        headline: str = "",
        headline_fontsize: int = None,
        transcript_path: Path = None,
        cut_start: float = 0.0,
        **kwargs,
    ):
        """Orquestra todas as camadas e salva no ledger."""
        logger.info(f"Iniciando Auditoria Científica: {video_id}")

        # 1. Coleta de Métricas Frias
        thumb_results = self.analyze_thumbnail(thumb_path)
        rhythm_results = self.analyze_rhythm(video_path)
        hook_results = self.analyze_hook(video_path)

        # 2. Identificar Transcrição
        if transcript_path and transcript_path.exists():
            transcript_json = transcript_path
        else:
            # Fallback heuristic
            transcript_json = video_path.with_name(
                video_id.split("_cut_")[0] + "_transcript.json"
            )
            if not transcript_json.exists():
                # Tenta localização alternativa se for pipeline direta
                transcript_json = (
                    video_path.parent.parent
                    / "analysis"
                    / f"{video_id.split('_cut_')[0]}_analysis.json"
                )

        hook_results["text_quality"] = self.analyze_hook_text(
            transcript_json, cut_start
        )

        if not ass_path:
            ass_path = video_path.with_suffix(".ass")
        sub_results = self.analyze_subtitles(ass_path)

        # 4. Análise Gráfica In-Video
        graphics_results = self.analyze_graphics(
            video_path, headline=headline, headline_fontsize=headline_fontsize
        )

        # 5. Score Preliminar
        overall = (
            thumb_results.get("score", 0) * 0.25
            + hook_results.get("score", 0) * 0.25
            + sub_results.get("score", 0) * 0.20
            + rhythm_results.get("score", 0) * 0.15
            + graphics_results.get("score", 0) * 0.15
        )

        # 5. CONTENT QUALITY CHECKS (Fidelity & Semantic)
        # 5.1 Fidelity Analysis (Transcript vs AI Titles)
        logger.info(f"Running FIDELITY check for {video_id}...")

        # Coletar textos para auditoria
        audit_list = [headline]
        if kwargs.get("youtube_title"):
            audit_list.append(kwargs.get("youtube_title"))
        if kwargs.get("thumb_hook"):
            audit_list.append(kwargs.get("thumb_hook"))

        fidelity_report = self.analyze_content_fidelity(
            transcript_path, texts=audit_list
        )

        # 5.2 Semantic Analysis (Logic Check)
        logger.info(f"Running SEMANTIC check for {video_id}...")
        semantic_auditor = SemanticAuditor()
        semantic_results = {
            "is_coherent": True,
            "sanity_score": 10.0,
            "detected_issues": [],
        }

        if transcript_path and transcript_path.exists():
            with open(transcript_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                semantic_results = semantic_auditor.audit_cut_transcript(
                    t_data.get("segments", [])
                )

        raw_results = {
            "thumbnail": thumb_results,
            "rhythm": rhythm_results,
            "hook": hook_results,
            "subtitles": sub_results,
            "graphics": graphics_results,
            "fidelity": fidelity_report,
            "semantic": semantic_results,
            "overall_score": round(overall, 2),
            "viral_potential": "UNKNOWN",
        }

        # 6. Diagnosis and Final Decision
        diagnosis_data = self.generate_llm_diagnosis(raw_results)

        final_results = {
            **raw_results,
            "diagnosis": diagnosis_data.get("diagnosis"),
            "viral_potential": diagnosis_data.get("viral_potential"),
            "recommendations": diagnosis_data.get("recommendations"),
            "is_approved": diagnosis_data.get("is_approved", False),
            "overall_score": diagnosis_data.get(
                "final_score", raw_results["overall_score"]
            ),
        }

        # AGGRESSIVE REJECT: If fidelity or semantic fails, force REPROVADO
        if fidelity_report.get("fidelity_score", 10.0) < 7.0:
            final_results["is_approved"] = False
            final_results["recommendations"] = (
                final_results.get("recommendations", "")
                + "\n❌ REPROVADO: Alucinação de conteúdo detectada!"
            )
            final_results["overall_score"] = min(final_results["overall_score"], 4.0)

        if semantic_results.get("sanity_score", 10.0) < 7.0:
            final_results["is_approved"] = False
            final_results["recommendations"] = (
                final_results.get("recommendations", "")
                + "\n❌ REPROVADO: Ilogia ou repetição detectada na transcrição!"
            )
            final_results["overall_score"] = min(final_results["overall_score"], 4.0)

        # 7. Salvar no Ledger
        self._save_to_ledger(video_id, final_results)

        # 8. Salvar JSON individual para o vídeo
        json_path = video_path.with_suffix(".audit.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, indent=2, ensure_ascii=False)

        logger.info(
            f"✅ Auditoria Concluída Score: {final_results['overall_score']} Potential: {final_results['viral_potential']}"
        )
        return final_results


if __name__ == "__main__":
    # Teste rápido
    logging.basicConfig(level=logging.INFO)
    auditor = DesignAuditor()
    print("Design Auditor carregado.")
