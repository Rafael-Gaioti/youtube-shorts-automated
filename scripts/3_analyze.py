"""
Script 3: Análise de Conteúdo com Claude
Analisa transcrições e identifica os melhores momentos para Shorts.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from dotenv import load_dotenv
from anthropic import Anthropic

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

def load_config() -> dict:
    """Carrega configurações do arquivo YAML."""
    config_path = Path("config/settings.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_prompt() -> str:
    """Carrega o prompt de análise."""
    config = load_config()
    prompt_path = Path(config['paths']['prompts']) / "analysis_prompt.txt"

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

    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def analyze_transcript(
    transcript_path: Path,
    output_dir: Optional[Path] = None,
    max_cuts: Optional[int] = None
) -> Dict:
    """
    Analisa uma transcrição usando Claude.

    Args:
        transcript_path: Caminho para o arquivo de transcrição JSON
        output_dir: Diretório de saída para análise (opcional)
        max_cuts: Número máximo de cortes a retornar (opcional)

    Returns:
        Dicionário com os cortes sugeridos

    Raises:
        FileNotFoundError: Se a transcrição não existir
    """
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcrição não encontrada: {transcript_path}")

    config = load_config()
    claude_cfg = config['claude_config']
    cuts_cfg = config['cuts_config']

    if output_dir is None:
        output_dir = Path(config['paths']['analysis'])
    output_dir.mkdir(parents=True, exist_ok=True)

    if max_cuts is None:
        max_cuts = cuts_cfg['max_cuts_per_video']

    # Carregar transcrição
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript_data = json.load(f)

    # Preparar texto para análise
    segments_text = []
    for seg in transcript_data['segments']:
        segments_text.append(
            f"[{seg['start']:.1f}s - {seg['end']:.1f}s]: {seg['text']}"
        )

    transcript_formatted = "\n".join(segments_text)

    # Montar prompt
    system_prompt = load_prompt()
    user_message = f"""Vídeo ID: {transcript_data['video_id']}
Duração total: {transcript_data['duration']:.1f}s
Idioma: {transcript_data['language']}

TRANSCRIÇÃO:
{transcript_formatted}

CONFIGURAÇÕES:
- Duração mínima: {cuts_cfg['min_duration']}s
- Duração máxima: {cuts_cfg['max_duration']}s
- Duração ideal: {cuts_cfg['target_duration']}s
- Score mínimo: {cuts_cfg['min_retention_score']}
- Máximo de cortes: {max_cuts}

Analise e retorne os {max_cuts} melhores momentos em JSON."""

    logger.info("Enviando para Claude API...")
    logger.info(f"Modelo: {claude_cfg['model']}")

    # Chamar Claude API
    client = Anthropic()

    response = client.messages.create(
        model=claude_cfg['model'],
        max_tokens=claude_cfg['max_tokens'],
        temperature=claude_cfg['temperature'],
        messages=[
            {
                "role": "user",
                "content": user_message
            }
        ],
        system=system_prompt
    )

    # Extrair resposta
    response_text = response.content[0].text.strip()
    logger.info("Resposta recebida do Claude")

    # Parse JSON
    try:
        # Remover possíveis marcadores de código
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        analysis_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao fazer parse do JSON: {e}")
        logger.error(f"Resposta: {response_text}")
        raise

    # Adicionar metadados
    analysis_data['video_id'] = transcript_data['video_id']
    analysis_data['transcript_path'] = str(transcript_path)
    analysis_data['config'] = {
        'min_duration': cuts_cfg['min_duration'],
        'max_duration': cuts_cfg['max_duration'],
        'min_retention_score': cuts_cfg['min_retention_score']
    }

    # Filtrar por score mínimo
    original_count = len(analysis_data.get('cuts', []))
    analysis_data['cuts'] = [
        cut for cut in analysis_data.get('cuts', [])
        if cut.get('retention_score', 0) >= cuts_cfg['min_retention_score']
    ]

    logger.info(f"Cortes sugeridos: {original_count}")
    logger.info(f"Cortes após filtro (score >= {cuts_cfg['min_retention_score']}): {len(analysis_data['cuts'])}")

    # Salvar análise
    output_file = output_dir / f"{transcript_data['video_id']}_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Análise salva em: {output_file}")

    return analysis_data

def find_latest_transcript() -> Path:
    """Encontra a transcrição mais recente."""
    config = load_config()
    transcripts_dir = Path(config['paths']['transcripts'])

    transcripts = list(transcripts_dir.glob("*_transcript.json"))
    if not transcripts:
        raise FileNotFoundError(f"Nenhuma transcrição encontrada em {transcripts_dir}")

    # Retorna o mais recente
    latest = max(transcripts, key=lambda p: p.stat().st_mtime)
    return latest

def main():
    """Função principal."""
    if len(sys.argv) > 1:
        transcript_path = Path(sys.argv[1])
    else:
        logger.info("Nenhuma transcrição especificada, buscando a mais recente...")
        transcript_path = find_latest_transcript()

    try:
        logger.info(f"Analisando: {transcript_path}")
        analysis = analyze_transcript(transcript_path)

        print(f"\n✓ Análise concluída!")
        print(f"Cortes identificados: {len(analysis['cuts'])}")

        for i, cut in enumerate(analysis['cuts'], 1):
            print(f"\n{i}. {cut['title']}")
            print(f"   Tempo: {cut['start']:.1f}s - {cut['end']:.1f}s ({cut['end']-cut['start']:.1f}s)")
            print(f"   Score: {cut['retention_score']}/10")

        print(f"\nPróximo passo: python scripts/4_cut.py")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
