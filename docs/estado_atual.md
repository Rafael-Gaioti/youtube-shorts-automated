# Estado Atual do Projeto

> Última atualização: Fev 2026

## ✅ O que está funcionando

### Pipeline Principal (ponta a ponta)

Pipeline **completo** — do download ao upload no YouTube:

```
Download → Transcrição → Análise → Corte → Export → Upload
```

- **`pipeline.py --url <youtube_url> --profile <perfil>`** — processa um vídeo do início ao fim
- **`pipeline.py --urls-file urls.txt`** — processa uma lista de URLs em batch
- Skip inteligente: cada etapa verifica se o output já existe antes de re-rodar
  - Download: `data/raw/{video_id}.mp4`
  - Transcrição: `data/transcripts/{video_id}_transcript.json`
  - Análise: `data/analysis/{video_id}_analysis.json` (pula se já tem cortes válidos)
  - Corte: `data/output/{video_id}_cut_0X.mp4` (pula se já existem)
  - Export: sempre re-gera `data/shorts/{video_id}_cut_0X_short.mp4`
- **`--force-analyze`** — re-analisa mesmo com analysis.json existente
- **`--force-cut`** — re-corta mesmo com arquivos de corte existentes

### Flags disponíveis no pipeline

| Flag                | Descrição                                        |
| ------------------- | ------------------------------------------------ |
| `--url URL`         | Processar uma URL diretamente                    |
| `--urls-file FILE`  | Arquivo txt com uma URL por linha (batch)        |
| `--profile PROFILE` | Perfil de usuário (`recommended`, `custom_test`) |
| `--force-analyze`   | Re-analisar ignorando cache                      |
| `--force-cut`       | Re-cortar ignorando cache                        |
| `--min-speakers N`  | Mínimo de oradores na diarização                 |

### Logs

- **Log por vídeo**: `logs/{video_id}_{timestamp}.log` — gerado automaticamente por execução
- **Erros FFmpeg**: `logs/ffmpeg_error.txt` (apenas quando há falha)

### Scripts Individuais

| Script                    | Função                                                                           |
| ------------------------- | -------------------------------------------------------------------------------- |
| `scripts/0_discover.py`   | Descobre novos vídeos via RSS/canal                                              |
| `scripts/1_download.py`   | Baixa vídeo do YouTube com yt-dlp                                                |
| `scripts/2_transcribe.py` | Transcreve com Whisper (GPU) + diarização                                        |
| `scripts/3_analyze.py`    | IA (**GPT-4o**) identifica cortes virais com anchors milimétricos na transcrição |
| `scripts/4_cut.py`        | Corta os segmentos do vídeo com FFmpeg                                           |
| `scripts/5_export.py`     | Exporta para 9:16 com legendas ASS karaoke                                       |
| `scripts/6_upload.py`     | Upload para YouTube via OAuth2 (✅ funcional)                                    |

### Upload para YouTube (`6_upload.py`)

```bash
# Dry run — ver título/tags sem fazer upload
.venv\Scripts\python.exe scripts/6_upload.py data/analysis/{id}_analysis.json --dry-run

# Upload como privado (padrão — revisa no YouTube Studio antes)
.venv\Scripts\python.exe scripts/6_upload.py data/analysis/{id}_analysis.json

# Upload de um corte específico
.venv\Scripts\python.exe scripts/6_upload.py data/analysis/{id}_analysis.json --cut 2 --privacy unlisted
```

- **Autenticação**: OAuth2, `client_secret_*.json` na raiz do projeto
- **Token salvo**: `config/youtube_token.json` (não commitar)
- **Registro de uploads**: `data/uploads/{video_id}_uploads.json`
- **Quota YouTube**: ~6 uploads/dia no plano gratuito (1.600 unidades/upload)

### Campos de Análise (output de `3_analyze.py`)

| Campo                 | Tipo | Descrição                                                         |
| --------------------- | ---- | ----------------------------------------------------------------- |
| `viral_score`         | 0–10 | Score geral de viralização                                        |
| `hook_strength`       | 0–10 | Força do gancho nos primeiros 3s                                  |
| `opening_pattern`     | str  | `contrarian`, `emotional`, `authority`, `curiosity`, `story`      |
| `emotional_intensity` | 0–10 | Intensidade emocional geral                                       |
| `loop_potential`      | 0–10 | Probabilidade de reassistir                                       |
| `content_type`        | str  | Tipo de conteúdo: `financial_mistake`, `success_revelation`, etc. |
| `hook`                | str  | Texto exato dos primeiros 3s                                      |
| `cliffhanger`         | str  | Texto exato dos últimos 3s                                        |

### Qualidade das Legendas e Título (UI)

- Formato ASS com karaoke dinâmico (palavra por palavra)
- **Cores por speaker**: speaker principal = amarelo, secundário = ciano
- **Fundo Translúcido**: O texto recebe um discreto box semi-transparente (Alpha C0, 25%) que confere contraste profissional e esconde poluição visual como propagandas.
- **Font size 52** (legível em mobile)
- Fonte Global: Arial Black
- **On Screen Text (Título Flutuante)**: Design moderno de criador usando Bordas (Outline=4) e Sombra Direcional (Shadow=6) robustos.
- Arquivos temp `.ass` são limpos automaticamente após export

### Auditoria de Design (Design Auditor) e Auto-Fix

O projeto conta com um `design_auditor.py` acoplado ao `5_export.py`, atuando como um rigoroso gatekeeper de qualidade visual, agora **totalmente algorítmico** (sem custos de LLM):

- **Análise Multicamadas**: O auditor pontua ritmo (motion energy), aderência do hook, e **Colisões Gráficas** (Textos vazando da Safe-Zone).
- **MediaPipe Integrado**: Avalia poses do rosto e score da área de texto na thumbnail gerada para as pontuações do OpenCV.
- **Auto-Fix (Auto-Correção)**: Se o auditor detectar textos mal dimensionados (tanto no vídeo quanto na thumbnail), o `5_export.py` aciona um loop automático de até 3 tentativas, redesenhando as mídias com fontes proporcionalmente reduzidas (steps de -15%) de forma paralela até a aprovação.
- Hard-Fails cirúrgicos atrelados diretamente a métricas como `headline_score` previnem vídeos defeituosos de avançarem para a nuvem.

### Configuração

- Perfis em `config/user_profiles.json`: `recommended`, `custom_test`
  - Cada perfil define `min_viral_score` próprio (override do global)
- Settings globais em `config/settings.yaml` (`min_viral_score: 5.0` como fallback)
- Variáveis de ambiente em `.env` (OpenAI key, HuggingFace token)

---

## ⚠️ Limitações Conhecidas

| Limitação                           | Detalhes                                                                         |
| ----------------------------------- | -------------------------------------------------------------------------------- |
| **GPU obrigatória para diarização** | Sem CUDA, diarização desativada (só 1 speaker)                                   |
| **Modo canal incompleto**           | `0_discover.py` + `discovery_queue.json` funciona mas não é testado regularmente |
| **Quota de upload**                 | YouTube Data API: ~6 uploads/dia no plano gratuito                               |
| **Título gerado pelo hook**         | Título pode ficar genérico se o `hook` da transcrição não for impactante         |
| **Métricas não coletadas**          | `7_metrics.py` ainda não existe — próxima etapa do roadmap                       |

---

## 🧭 Visão Estratégica (Produtividade HQ)

O projeto migrou da fase técnica de experimentação aberta para uma fase de consistência. Todos os rumos estão documentados em `docs/Produtividade_HQ_Decisoes_Estrategicas.md`.

Regras de Ouro atuais:

- **Consistência > Viral isolado**: Nicho cravado em Desenvolvimento Pessoal e Produtividade (mínimo 60 dias sem desvios).
- **Identidade Visual**: Logomarca Produtividade HQ (B/W + Amarelo).
- **Cadência de Uploads**: Subindo gradativamente para testes de 2 e depois 3 _Shorts_ por dia.
- O _Target_ prioritário do Pipeline é assegurar uma **retenção média acima de 65%.**

---

## 📁 Estrutura de Dados

```
data/
├── raw/           # Vídeos originais baixados (.mp4)
├── transcripts/   # Transcrições JSON com words + speakers
├── analysis/      # Análise de cortes por vídeo (JSON)
├── output/        # Cortes brutos do vídeo original
├── shorts/        # Shorts finais 9:16 com legendas ← OUTPUT FINAL
└── uploads/       # Registros de uploads (youtube_video_id, título, scores)

logs/
├── {video_id}_{timestamp}.log  # Log de cada execução do pipeline
└── ffmpeg_error.txt             # Último erro do FFmpeg (quando houver)

config/
├── settings.yaml               # Configuração global
├── user_profiles.json          # Perfis SaaS
└── youtube_token.json          # Token OAuth2 (gerado na 1ª autenticação, não commitar)
```
