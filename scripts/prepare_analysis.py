"""
Script Helper: Preparar Análise Manual
Prepara transcrição + prompt formatados para análise no Claude browser.
"""

import sys
import json
from pathlib import Path
from typing import Optional

def prepare_for_analysis(video_id: str) -> None:
    """
    Prepara os dados para análise manual no Claude browser.

    Args:
        video_id: ID do vídeo (ex: ff88SpBpkD0)
    """
    # Caminhos
    transcript_file = Path(f"data/transcripts/{video_id}_transcript.json")
    prompt_file = Path("config/prompts/analysis_prompt.txt")
    output_file = Path(f"data/analysis/{video_id}_prepared.txt")

    # Verificar se arquivos existem
    if not transcript_file.exists():
        print(f"[ERRO] Transcrição não encontrada: {transcript_file}")
        print(f"\nExecute primeiro: python main.py <URL> --stages download,transcribe")
        sys.exit(1)

    if not prompt_file.exists():
        print(f"[ERRO] Prompt não encontrado: {prompt_file}")
        sys.exit(1)

    # Carregar transcrição
    with open(transcript_file, 'r', encoding='utf-8') as f:
        transcript = json.load(f)

    # Carregar prompt
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt = f.read()

    # Formatar texto completo da transcrição
    full_text = []
    for i, seg in enumerate(transcript['segments'], 1):
        timestamp = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
        full_text.append(f"{i}. {timestamp} {seg['text']}")

    transcript_text = "\n".join(full_text)

    # Criar output combinado
    output_dir = Path("data/analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    combined = f"""# ANÁLISE DE SHORTS - VIDEO {video_id}

## Informações do Vídeo
- Duração: {transcript['duration']:.1f}s ({transcript['duration']/60:.1f} min)
- Idioma: {transcript['language']} (confiança: {transcript['language_probability']:.2%})
- Total de segmentos: {len(transcript['segments'])}

{'-' * 80}

## PROMPT DE ANÁLISE

{prompt}

{'-' * 80}

## TRANSCRIÇÃO COMPLETA

{transcript_text}

{'-' * 80}

## INSTRUÇÕES

1. COPIE todo o conteúdo acima (Ctrl+A, Ctrl+C)
2. COLE no Claude browser (claude.ai)
3. Claude vai retornar um JSON com os cortes virais
4. SALVE a resposta do Claude em: data/analysis/{video_id}_analysis.json
5. Execute: python scripts/4_cut.py data/raw/{video_id}.mp4

Formato esperado do JSON de resposta:
{{
  "cuts": [
    {{
      "start_time": 45.2,
      "end_time": 89.5,
      "viral_score": 9.5,
      "reason": "Descrição do porquê esse corte é viral",
      "content_type": "money_revelation",
      "emotions": ["surprise", "excitement"],
      "keywords": ["palavra1", "palavra2"]
    }}
  ]
}}
"""

    # Salvar arquivo preparado
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(combined)

    # Também criar um arquivo só com transcrição simples
    simple_file = output_dir / f"{video_id}_transcript_simple.txt"
    with open(simple_file, 'w', encoding='utf-8') as f:
        f.write(transcript_text)

    # Estatísticas
    total_duration = transcript['duration']
    avg_segment_duration = total_duration / len(transcript['segments'])

    print(f"\n{'=' * 80}")
    print(f"[OK] Arquivos preparados para análise manual!")
    print(f"{'=' * 80}\n")

    print(f"Video ID: {video_id}")
    print(f"Duração: {total_duration:.1f}s ({total_duration/60:.1f} minutos)")
    print(f"Segmentos: {len(transcript['segments'])} (média {avg_segment_duration:.1f}s cada)")
    print(f"Idioma: {transcript['language']} ({transcript['language_probability']:.1%} confiança)")

    print(f"\n{'=' * 80}")
    print(f"ARQUIVOS CRIADOS:")
    print(f"{'=' * 80}\n")

    print(f"1. ARQUIVO COMPLETO (prompt + transcrição):")
    print(f"   {output_file}")
    print(f"   > Abra este arquivo e copie TUDO para o Claude browser\n")

    print(f"2. TRANSCRIÇÃO SIMPLES:")
    print(f"   {simple_file}")
    print(f"   > Apenas a transcrição, sem prompt\n")

    print(f"{'=' * 80}")
    print(f"PRÓXIMOS PASSOS:")
    print(f"{'=' * 80}\n")

    print(f"1. Abra o arquivo: {output_file}")
    print(f"2. Copie todo o conteúdo (Ctrl+A, Ctrl+C)")
    print(f"3. Cole no Claude browser (claude.ai)")
    print(f"4. Copie a resposta JSON do Claude")
    print(f"5. Salve em: data/analysis/{video_id}_analysis.json")
    print(f"6. Execute: python scripts/4_cut.py data/raw/{video_id}.mp4")
    print(f"7. Execute: python scripts/5_export.py")
    print(f"\n{'=' * 80}\n")

def find_latest_transcript() -> Optional[str]:
    """Encontra a transcrição mais recente."""
    transcripts_dir = Path("data/transcripts")

    if not transcripts_dir.exists():
        return None

    transcripts = list(transcripts_dir.glob("*_transcript.json"))
    if not transcripts:
        return None

    # Retorna o mais recente
    latest = max(transcripts, key=lambda p: p.stat().st_mtime)
    return latest.stem.replace("_transcript", "")

def main():
    """Função principal."""
    if len(sys.argv) > 1:
        video_id = sys.argv[1]
    else:
        print("Nenhum video_id especificado, buscando transcrição mais recente...")
        video_id = find_latest_transcript()

        if not video_id:
            print("\n[ERRO] Nenhuma transcrição encontrada em data/transcripts/")
            print("\nUso: python scripts/prepare_analysis.py <video_id>")
            print("Exemplo: python scripts/prepare_analysis.py ff88SpBpkD0")
            sys.exit(1)

        print(f"[OK] Encontrado: {video_id}")

    try:
        prepare_for_analysis(video_id)
    except Exception as e:
        print(f"\n[ERRO] Falha ao preparar análise: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
