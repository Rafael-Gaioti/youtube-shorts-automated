# Arquitetura do Pipeline

## Visão Geral

```
YouTube URL (--url) ou arquivo com URLs (--urls-file)
    │
    ▼
┌─────────────────┐
│  1_download.py  │  yt-dlp  →  data/raw/{id}.mp4
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│  2_transcribe.py    │  Whisper (GPU) + pyannote  →  data/transcripts/{id}_transcript.json
│  - words com timing │     (speakers identificados por cor)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  3_analyze.py       │  GPT-4o-mini  →  data/analysis/{id}_analysis.json
│  - identifica clips │     (viral_score, hook_strength, opening_pattern,
│  - filtra por score │      emotional_intensity, loop_potential, content_type)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  4_cut.py           │  FFmpeg  →  data/output/{id}_cut_0X.mp4
│  - corta segmentos  │
└─────────┬───────────┘
          │
          ▼
┌──────────────────────────┐
│  5_export.py             │  FFmpeg  →  data/shorts/{id}_cut_0X_short.mp4
│  - scale + crop 9:16     │  (temp .ass gerado e deletado após uso)
│  - ASS subtitles karaoke │  + .audit.json via Design Auditor
│  - headline drawtext     │
│  - Design Auditor (Alg)  │  <- Avalia Colisões/Ritmo/Legendas
│  - Auto-Fix Typography   │  <- Reduz fonte paralelamente em erros
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  6_upload.py             │  YouTube Data API v3  →  Short publicado no canal
│  - OAuth2 automático    │  (token salvo em config/youtube_token.json)
│  - título via hook       │  registro em data/uploads/{id}_uploads.json
└──────────────────────────┘
          │
          ▼ (planejado)
┌──────────────────────────┐
│  7_metrics.py            │  YouTube Analytics API  →  data/metrics/
└──────────────────────────┘
```

## Orchestrator

**`pipeline.py`** orquestra os scripts acima:

| Flag                | Descrição                                         |
| ------------------- | ------------------------------------------------- |
| `--url URL`         | Processar uma URL diretamente                     |
| `--urls-file FILE`  | Arquivo txt com uma URL por linha (batch)         |
| `--profile PROFILE` | Perfil de usuário (`recommended`, `custom_test`)  |
| `--force-analyze`   | Re-analisar ignorando cache do analysis.json      |
| `--force-cut`       | Re-cortar ignorando cache dos arquivos de corte   |
| `--min-speakers N`  | Mínimo de oradores para diarização                |
| `--upload`          | _(planejado)_ Fazer upload ao YouTube após export |

**Skip inteligente:** cada etapa verifica se o output já existe antes de re-executar.

**Log por vídeo:** `logs/{video_id}_{timestamp}.log` — gerado automaticamente.

**Sumário final:** após a pipeline, exibe viral_score, hook_strength e tamanho de cada short.

## Formato das Legendas (ASS)

- `[Script Info]`: resolução 1080×1920, escala ASS
- `[V4+ Styles]`: Arial Black, font_size=52
- `[Events]`: uma linha por palavra, com karaoke timing `{\k<ms>}`
- Cores dinâmicas por speaker: **amarelo** = speaker 1 (principal), **ciano** = speaker 2
- Arquivos `.ass` temporários são deletados automaticamente após o export

## Formato do Transcript JSON

```json
{
  "segments": [
    {
      "start": 1.23,
      "end": 2.45,
      "text": "palavra",
      "speaker": 1,
      "words": [{ "word": "palavra", "start": 1.23, "end": 1.89 }]
    }
  ]
}
```

## Formato do Analysis JSON

```json
{
  "video_id": "y9hwhoB9XTI",
  "transcript_path": "data/transcripts/..._transcript.json",
  "config": {
    "min_duration": 20,
    "max_duration": 55,
    "min_viral_score": 4.0,
    "max_cuts_to_export": 3
  },
  "cuts": [
    {
      "start": 91.0,
      "end": 150.0,
      "duration": 59.0,
      "viral_score": 8.5,
      "hook_strength": 9,
      "opening_pattern": "emotional",
      "emotional_intensity": 8,
      "loop_potential": 7,
      "content_type": "dramatic_transformation",
      "hook": "texto exato dos primeiros 3 segundos",
      "cliffhanger": "texto exato dos últimos 3 segundos",
      "on_screen_text": "FRASE EM CAPS",
      "emotions": ["shock", "curiosity"],
      "keywords": ["dinheiro", "erro"],
      "target_audience": "empreendedores",
      "speaker_map": { "L10": 1, "L11": 1, "L12": 2 },
      "speakers": [
        { "start": 91.0, "end": 120.0, "id": 1 },
        { "start": 120.0, "end": 150.0, "id": 2 }
      ]
    }
  ],
  "stats": {
    "total_analyzed": 5,
    "filtered": 3,
    "exported": 3,
    "avg_viral_score": 8.2
  }
}
```

## Campos de Análise — Scoring

| Campo                 | Range | Descrição                                                    |
| --------------------- | ----- | ------------------------------------------------------------ |
| `viral_score`         | 0–10  | Score geral de viralização                                   |
| `hook_strength`       | 0–10  | Força do gancho nos primeiros 3s                             |
| `opening_pattern`     | str   | `contrarian`, `emotional`, `authority`, `curiosity`, `story` |
| `emotional_intensity` | 0–10  | Intensidade emocional geral do trecho                        |
| `loop_potential`      | 0–10  | Probabilidade de reassistir / efeito loop                    |

## Configuração de Perfis

Os perfis em `config/user_profiles.json` definem:

- `min_viral_score` — mínimo para um corte ser aprovado (override do `settings.yaml`)
- `caption_styles` — cores e tamanho das legendas
- `discovery_rules` — filtros para o modo canal (`0_discover.py`)

O `settings.yaml` define valores globais de fallback (quando o perfil não especifica).
