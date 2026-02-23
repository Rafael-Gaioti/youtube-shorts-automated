import json
import logging
from typing import Dict, Any, Tuple
from openai import OpenAI
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI Client
# Re-uses the existing ANTHROPIC_API_KEY if we were to adapt this for Claude,
# but for low-latency rewriting, we assume OPENAI_API_KEY is available in .env
# If not, the user has to supply it. We will prompt for it gracefully.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

VALIDATOR_PROMPT = """Você é um Copywriter Especialista em YouTube Shorts (Nível Elite).
Seu objetivo é transformar títulos "bons" (8/10) em títulos "espetaculares" (9/10 ou 10/10).

Regras de Ouro (MÉTRICA 9/10):
1. VERBO + CONSEQÜÊNCIA + TENSÃO: O título deve prometer uma transformação real ou avisar sobre um perigo iminente.
2. CONSEQÜÊNCIA CONCRETA: Proibido abstrações como "melhorar" ou "crescer". Use "FALÊNCIA", "LUCRO 10X", "DEMISSÃO", "MULTA GRAVE".
3. FIDELIDADE ABSOLUTA (CRÍTICO): ABSOLUTAMENTE PROIBIDO inventar palavras ou conceitos que não estejam no áudio. Use apenas o vocabulário e contexto fornecidos.
4. PROFISSIONALISMO (CRÍTICO): Proibido o uso de palavrões ou gírias ofensivas (Ex: "fode", "ferrou", "merda"). Mantenha um tom de autoridade executiva.
5. MECANISMO ÚNICO: Se possível, indique COMO ou POR QUE (Ex: "A técnica secreta que...", "O erro que...").
6. PÚBLICO IMPLÍCITO: Direcione para quem importa (Ex: "Donos de empresa", "Iniciantes", "Quem ganha pouco").
7. VIABILIDADE VISUAL (CRÍTICO): Os termos devem caber na tela. EVITE palavras com mais de 11 caracteres. Prefira termos curtos e fortes.
8. COMPLEMENTARIDADE: O Thumbnail Hook (max 3 palavras) deve ser o "soco" emocional que complementa o título.

Eixos de Avaliação (0-10):
- clarity: Entendimento instantâneo?
- tension: Dor ou desejo extremo?
- specificity: Zero abstração?
- mechanism: O "como" está claro?
- visual_feasibility: As palavras são curtas e impactantes para thumbnail?

Se a Média das 5 notas for MENOR que 9.0, gere uma alternativa de ELITE.

Responda ESTRITAMENTE em formato JSON:
{
  "scores": {
    "clarity": 9,
    "tension": 9,
    "specificity": 9,
    "mechanism": 8,
    "visual_feasibility": 10
  },
  "approved": false,
  "improved_youtube_title": "O erro de gestão que leva seu negócio à falência",
  "improved_thumbnail_hook": "EVITE A FALÊNCIA",
  "reason": "O título original era genérico. Adicionei mecanismo ('erro de gestão') e a consequência fatal ('falência')."
}
"""


def validate_and_improve_title(
    cut_data: Dict[str, Any], transcript_context: str
) -> Dict[str, Any]:
    """
    Validates the generated youtube_title and thumbnail_hook.
    If they are weak (abstract, low tension), it uses an LLM to rewrite them.

    Args:
        cut_data: The dictionary representing a single cut from the analysis JSON.
        transcript_context: A snippet of the transcript to give the LLM context for rewriting.
    Returns:
        The updated cut_data dictionary.
    """
    if not client.api_key:
        logger.warning("OPENAI_API_KEY not found. Skipping Title Validator.")
        return cut_data

    original_title = cut_data.get("youtube_title", "")
    original_hook = cut_data.get("thumbnail_hook", "")

    if not original_title:
        return cut_data

    # We send the transcription hook/cliffhanger as context so the LLM knows what the video is about
    spoken_hook = cut_data.get("hook", "")
    spoken_cliffhanger = cut_data.get("cliffhanger", "")

    user_message = (
        f"Abaixo estão os dados do corte atual.\n\n"
        f"Contexto Falado (Início): '{spoken_hook}'\n"
        f"Contexto Falado (Fim): '{spoken_cliffhanger}'\n\n"
        f"TÍTULO GERADO: '{original_title}'\n"
        f"THUMBNAIL HOOK GERADO: '{original_hook}'\n\n"
        f"Avalie e, se necessário, reescreva em JSON."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": VALIDATOR_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=300,
        )

        result_json = json.loads(response.choices[0].message.content)

        is_approved = result_json.get("approved", True)
        scores = result_json.get("scores", {})
        avg_score = sum(scores.values()) / len(scores) if scores else 0.0

        if not is_approved:
            new_title = result_json.get("improved_youtube_title", original_title)
            new_hook = result_json.get("improved_thumbnail_hook", original_hook)

            logger.info(
                f"Title Validator: Reprovou '{original_title}' (Média: {avg_score:.1f})."
            )
            logger.info(f"Title Validator: Novo Título -> '{new_title}'")

            cut_data["youtube_title"] = new_title
            cut_data["thumbnail_hook"] = new_hook
            cut_data["title_validation"] = {
                "original_title": original_title,
                "scores": scores,
                "reason": result_json.get("reason", ""),
            }
        else:
            logger.info(
                f"Title Validator: Aprovou '{original_title}' (Média: {avg_score:.1f})."
            )

    except Exception as e:
        logger.error(f"Erro no Title Validator: {str(e)}")

    return cut_data
