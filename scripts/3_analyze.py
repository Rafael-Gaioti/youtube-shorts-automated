"""
Script 3: Análise de Conteúdo com IA
Analisa transcrições e identifica os melhores momentos para Shorts usando Claude ou OpenAI.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Optional
import yaml
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()


def load_config() -> dict:
    """Carrega configurações do arquivo YAML."""
    config_path = Path("config/settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt() -> str:
    """Carrega o prompt de análise."""
    config = load_config()
    prompt_path = Path(config["paths"]["prompts"]) / "analysis_prompt.txt"

    if not prompt_path.exists():
        # Prompt padrão caso não exista
        return """Analise esta transcrição de vídeo e identifique os melhores momentos para criar Shorts virais.

Para cada corte, forneça:
1. Timestamp de início e fim (em segundos)
2. Score de retenção (0-10)
3. Justificativa
4. Título sugerido

Critérios:
- Conteúdo impactante e autossuficiente
- Duração ideal: 20-35 segundos
- Alto potencial viral
- Não requer contexto anterior

Retorne APENAS um JSON válido com este formato:
{
  "cuts": [
    {
      "start": 0.0,
      "end": 30.0,
      "retention_score": 9,
      "title": "Título do Short",
      "rationale": "Justificativa"
    }
  ]
}"""

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def analyze_transcript(
    transcript_path: Path,
    output_dir: Optional[Path] = None,
    max_cuts: Optional[int] = None,
) -> Dict:
    """
    Analisa uma transcrição usando IA (Claude ou OpenAI).

    Args:
        transcript_path: Caminho para o arquivo de transcrição JSON
        output_dir: Diretório de saída para análise (opcional)
        max_cuts: Número máximo de cortes a retornar (opcional)

    Returns:
        Dicionário com os cortes sugeridos
    """
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcrição não encontrada: {transcript_path}")

    config = load_config()
    ai_provider = config.get("ai_provider", "claude").lower()
    cuts_cfg = config["cuts_config"]

    if output_dir is None:
        output_dir = Path(config["paths"]["analysis"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if max_cuts is None:
        max_cuts = cuts_cfg["max_cuts_per_video"]

    # Carregar transcrição
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)

    # Preparar texto para análise com numeração de linhas
    segments_text = []
    for i, seg in enumerate(transcript_data["segments"]):
        segments_text.append(
            f"L{i}: [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        )

    transcript_formatted = "\n".join(segments_text)

    # Montar prompt
    system_prompt = load_prompt()

    # Personalizar prompt se for modelo local (para garantir formato e speaker_map)
    if ai_provider == "ollama":
        system_prompt += "\n\n### MANDATORY INSTRUCTIONS FOR LLAMA 3:\n"
        system_prompt += (
            "1. OUTPUT ONLY JSON. DO NOT INCLUDE ANY TEXT OUTSIDE THE JSON.\n"
        )
        system_prompt += "2. USE THESE EXACT ENGLISH KEYS: 'start', 'end', 'viral_score', 'content_type', 'on_screen_text', 'speaker_map'.\n"
        system_prompt += "3. DO NOT TRANSLATE KEYS TO PORTUGUESE (i.e., use 'start', not 'início' or 'iniciar').\n"
        system_prompt += "4. 'speaker_map' IS MANDATORY for every segment in the cut.\n"
        system_prompt += "5. EXAMPLE: {'start': 10.5, 'end': 35.0, 'viral_score': 9, 'on_screen_text': 'TITLE', 'speaker_map': {'L1': 1, 'L2': 2}}\n"
        system_prompt += "\nResponse must be a single JSON object with a 'cuts' key containing the list of moments.\n"

    user_message = f"""Vídeo ID: {transcript_data["video_id"]}
Duração total: {transcript_data["duration"]:.1f}s
Idioma: {transcript_data["language"]}

TRANSCRIÇÃO:
{transcript_formatted}

Analise e retorne os {max_cuts} melhores momentos em JSON no formato: {{"cuts": [...]}}"""

    response_text = ""

    if ai_provider == "openai":
        try:
            from openai import OpenAI

            client = OpenAI()
            openai_cfg = config["openai_config"]
            logger.info(f"Enviando para OpenAI API ({openai_cfg['model']})...")

            response = client.chat.completions.create(
                model=openai_cfg["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=openai_cfg["temperature"],
                max_tokens=openai_cfg["max_tokens"],
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content.strip()
            logger.info("Resposta recebida do OpenAI")

            # Debug: Salvar resposta bruta
            with open("debug_last_ai_response.json", "w", encoding="utf-8") as f:
                f.write(response_text)

        except ImportError:
            logger.error(
                "Erro: 'openai' library não instalada. Execute 'pip install openai'"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Erro na API do OpenAI: {e}")
            raise

    elif ai_provider == "ollama":
        try:
            from openai import OpenAI

            ollama_cfg = config["ollama_config"]
            client = OpenAI(
                base_url=ollama_cfg["base_url"],
                api_key="ollama",  # Ollama não exige chave real, mas o cliente OpenAI pede
            )
            logger.info(
                f"Enviando para Ollama ({ollama_cfg['model']}) em {ollama_cfg['base_url']}..."
            )

            response = client.chat.completions.create(
                model=ollama_cfg["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=ollama_cfg["temperature"],
                max_tokens=ollama_cfg["max_tokens"],
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content.strip()
            logger.info("Resposta recebida do Ollama")

            # Debug: Salvar resposta bruta
            with open("debug_last_ai_response.json", "w", encoding="utf-8") as f:
                f.write(response_text)

        except ImportError:
            logger.error(
                "Erro: 'openai' library não instalada. Execute 'pip install openai'"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Erro ao conectar com Ollama: {e}")
            logger.warning(
                "Certifique-se de que o Ollama está rodando e o modelo está baixado (ollama run llama3)."
            )
            raise

    else:  # Default to Claude
        try:
            from anthropic import Anthropic

            client = Anthropic()
            claude_cfg = config["claude_config"]
            logger.info(f"Enviando para Claude API ({claude_cfg['model']})...")

            response = client.messages.create(
                model=claude_cfg["model"],
                max_tokens=claude_cfg["max_tokens"],
                temperature=claude_cfg["temperature"],
                messages=[{"role": "user", "content": user_message}],
                system=system_prompt,
            )
            response_text = response.content[0].text.strip()
            logger.info("Resposta recebida do Claude")
        except ImportError:
            logger.error(
                "Erro: 'anthropic' library não instalada. Execute 'pip install anthropic'"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Erro na API da Anthropic: {e}")
            raise

    # Parse JSON
    try:
        # Remover possíveis marcadores de código e texto extra (comum em modelos locais)
        text_to_parse = response_text.strip()

        # Encontrar o primeiro '{' ou '[' e o último '}' ou ']'
        first_brace = text_to_parse.find("{")
        first_bracket = text_to_parse.find("[")

        start_idx = -1
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            start_idx = first_brace
            end_idx = text_to_parse.rfind("}")
        elif first_bracket != -1:
            start_idx = first_bracket
            end_idx = text_to_parse.rfind("]")

        if start_idx != -1 and end_idx != -1:
            text_to_parse = text_to_parse[start_idx : end_idx + 1]

        try:
            parsed_data = json.loads(text_to_parse)
        except json.JSONDecodeError:
            # Tentar encontrar múltiplos objetos {...} por contagem de chaves
            objects = []
            stack = 0
            start_pos = -1

            for i, char in enumerate(text_to_parse):
                if char == "{":
                    if stack == 0:
                        start_pos = i
                    stack += 1
                elif char == "}":
                    stack -= 1
                    if stack == 0 and start_pos != -1:
                        obj_str = text_to_parse[start_pos : i + 1]
                        try:
                            objects.append(json.loads(obj_str))
                        except json.JSONDecodeError:
                            pass
                        start_pos = -1

            if objects:
                logger.info(
                    f"Detectados {len(objects)} possíveis objetos JSON via brace-counting"
                )
                parsed_data = objects
            else:
                raise

        # Normalizar para formato consistente
        cuts_list = []
        if isinstance(parsed_data, list):
            cuts_list = parsed_data
        elif isinstance(parsed_data, dict):
            # Tentar encontrar a lista em chaves comuns
            for key in [
                "cuts",
                "result",
                "segments",
                "data",
                "video_cuts",
                "transcription",
            ]:
                if key in parsed_data and isinstance(parsed_data[key], list):
                    cuts_list = parsed_data[key]
                    break

            if not cuts_list:
                # Se ainda não for lista, talvez seja um objeto único que é um corte
                if "start" in parsed_data and "end" in parsed_data:
                    logger.info("Detectado objeto de corte único no nível raiz")
                    cuts_list = [parsed_data]
                else:
                    logger.warning(
                        f"Nenhum corte estruturado encontrado no JSON. Chaves: {list(parsed_data.keys())}"
                    )
                    cuts_list = []
        else:
            logger.warning(
                f"Formato JSON inesperado ({type(parsed_data)}), retornando lista vazia."
            )
            cuts_list = []

        logger.info(f"Total de cortes brutos detectados: {len(cuts_list)}")

    except json.JSONDecodeError as e:
        logger.error(f"Erro ao fazer parse do JSON: {e}")
        logger.error(f"Resposta: {response_text}")
        raise
    except ValueError as e:
        logger.error(f"Erro de formato: {e}")
        logger.error(f"Resposta: {response_text}")
        raise

    # Validar e normalizar cada corte
    min_viral_score = cuts_cfg.get(
        "min_viral_score", cuts_cfg.get("min_retention_score", 8.0)
    )

    validated_cuts = []
    for cut in cuts_list:
        # Normalizar campos (suportar Português e variações de nomes)
        # 1. Start/End/Duration
        start_val = cut.get("start", cut.get("inicio", cut.get("início", 0)))
        duration_val = cut.get("duration", cut.get("duração", cut.get("duracao", 0)))
        end_val = cut.get("end", cut.get("fim", 0))

        # Se não tem end mas tem duration, calcular
        if end_val == 0 and duration_val > 0:
            end_val = start_val + duration_val
        elif duration_val == 0 and end_val > start_val:
            duration_val = end_val - start_val

        cut["start"] = start_val
        cut["end"] = end_val
        cut["duration"] = duration_val

        # 2. Score
        viral_score = cut.get(
            "viral_score",
            cut.get(
                "retention_score",
                cut.get("score", cut.get("pontuação", cut.get("pontuacao", 0))),
            ),
        )
        cut["viral_score"] = viral_score

        # 3. Rationale/Headline
        cut["rationale"] = cut.get(
            "rationale",
            cut.get(
                "reason",
                cut.get(
                    "motivação",
                    cut.get("motivacao", cut.get("explanation", "")),
                ),
            ),
        )
        cut["headline"] = cut.get(
            "headline",
            cut.get("title", cut.get("titulo", cut.get("título", "Destaque"))),
        )

        # 4. Speaker Map
        speaker_map = cut.get(
            "speaker_map", cut.get("speakers", cut.get("mapa_falantes", {}))
        )
        if not isinstance(speaker_map, dict):
            speaker_map = {}
        cut["speaker_map"] = speaker_map

        # Garantir campos mínimos para validação continuar
        if cut["start"] == 0 and (cut["end"] == 0 or cut["duration"] == 0):
            logger.warning(f"Corte sem timestamps válidos: {cut}")
            continue

        # 5. On Screen Text (Headline)
        on_screen_text = (
            cut.get("on_screen_text", cut.get("headline", "MOMENTO INCRÍVEL"))
            .strip()
            .upper()
        )
        if not on_screen_text or on_screen_text == "DESTAQUE":
            on_screen_text = "MOMENTO INCRÍVEL"
        cut["on_screen_text"] = on_screen_text

        cut.setdefault("content_type", "unknown")
        cut.setdefault("emotions", [])
        cut.setdefault("keywords", [])
        cut.setdefault("hook", "")
        cut.setdefault("cliffhanger", "")
        cut.setdefault("target_audience", "geral")
        cut.setdefault("reason", cut.get("rationale", ""))

        # Novo sistema: converter speaker_map (L0: 1, L1: 2...) para a lista speakers
        speaker_map = cut.get("speaker_map", {})
        speakers_list = []
        if speaker_map:
            # Ordenar chaves numéricas (L0, L1, L10...)
            try:
                sorted_keys = sorted(speaker_map.keys(), key=lambda x: int(x[1:]))
                for key in sorted_keys:
                    idx = int(key[1:])
                    if idx < len(transcript_data["segments"]):
                        seg = transcript_data["segments"][idx]
                        speaker_id = speaker_map[key]

                        # Merge com o anterior se for o mesmo orador
                        if speakers_list and speakers_list[-1]["id"] == speaker_id:
                            speakers_list[-1]["end"] = seg["end"]
                        else:
                            speakers_list.append(
                                {
                                    "start": seg["start"],
                                    "end": seg["end"],
                                    "id": speaker_id,
                                }
                            )
            except Exception as ex:
                logger.warning(f"Erro ao converter speaker_map: {ex}")

        # Fallback: Se não houver speakers, criar um único segmento com Speaker 1 cobrindo o corte todo
        if not speakers_list:
            speakers_list.append({"start": cut["start"], "end": cut["end"], "id": 1})

        cut["speakers"] = speakers_list

        validated_cuts.append(cut)

    # Filtrar por viral score mínimo e duração
    original_count = len(validated_cuts)
    min_duration = cuts_cfg.get("min_duration", 15)

    filtered_cuts = []
    for cut in validated_cuts:
        if cut["viral_score"] < min_viral_score:
            continue

        if cut["duration"] < min_duration:
            logger.warning(
                f"Corte rejeitado (muito curto: {cut['duration']:.1f}s < {min_duration}s): {cut}"
            )
            continue

        filtered_cuts.append(cut)

    # Ordenar por viral_score (maior primeiro)
    filtered_cuts.sort(key=lambda x: x["viral_score"], reverse=True)

    # Limitar ao máximo de cortes para exportação
    max_cuts_to_export = cuts_cfg.get("max_cuts_to_export", max_cuts)
    final_cuts = filtered_cuts[:max_cuts_to_export]

    logger.info(f"Cortes analisados: {original_count}")
    logger.info(f"Após filtro (viral_score >= {min_viral_score}): {len(filtered_cuts)}")
    logger.info(f"Selecionados para exportação: {len(final_cuts)}")

    # Montar estrutura final
    analysis_data = {
        "video_id": transcript_data["video_id"],
        "transcript_path": str(transcript_path),
        "config": {
            "min_duration": cuts_cfg["min_duration"],
            "max_duration": cuts_cfg["max_duration"],
            "min_viral_score": min_viral_score,
            "max_cuts_to_export": max_cuts_to_export,
        },
        "cuts": final_cuts,
        "stats": {
            "total_analyzed": original_count,
            "filtered": len(filtered_cuts),
            "exported": len(final_cuts),
            "avg_viral_score": sum(c["viral_score"] for c in final_cuts)
            / len(final_cuts)
            if final_cuts
            else 0,
        },
    }

    logger.info(
        f"Score viral médio: {analysis_data['stats']['avg_viral_score']:.1f}/10"
    )

    # Salvar análise
    output_file = output_dir / f"{transcript_data['video_id']}_analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Análise salva em: {output_file}")

    return analysis_data


def find_latest_transcript() -> Path:
    """Encontra a transcrição mais recente."""
    config = load_config()
    transcripts_dir = Path(config["paths"]["transcripts"])

    transcripts = list(transcripts_dir.glob("*_transcript.json"))
    if not transcripts:
        raise FileNotFoundError(f"Nenhuma transcrição encontrada em {transcripts_dir}")

    # Retorna o mais recente
    latest = max(transcripts, key=lambda p: p.stat().st_mtime)
    return latest


def main():
    """Função principal."""
    # Garantir UTF-8 no terminal Windows para evitar erros de carmap
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            # Fallback para Python < 3.7 se necessário
            import codecs

            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

    if len(sys.argv) > 1:
        transcript_path = Path(sys.argv[1])
    else:
        logger.info("Nenhuma transcrição especificada, buscando a mais recente...")
        transcript_path = find_latest_transcript()

    try:
        logger.info(f"Analisando: {transcript_path}")
        analysis = analyze_transcript(transcript_path)

        print("\n✓ Análise concluída!")
        print(f"Cortes selecionados: {len(analysis['cuts'])}")
        print(f"Score viral médio: {analysis['stats']['avg_viral_score']:.1f}/10")

        for i, cut in enumerate(analysis["cuts"], 1):
            print(f"\n{i}. [{cut['content_type']}] Score: {cut['viral_score']:.1f}/10")
            print(
                f"   Tempo: {cut['start']:.1f}s - {cut['end']:.1f}s ({cut['duration']:.1f}s)"
            )
            print(f"   Texto tela: {cut.get('on_screen_text', 'N/A')}")
            print(f"   Hook: {cut.get('hook', 'N/A')[:50]}...")
            print(f"   Emoções: {', '.join(cut.get('emotions', []))}")
            print(f"   Motivo: {cut.get('reason', 'N/A')[:80]}...")

        print("\nPróximo passo: python scripts/4_cut.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
