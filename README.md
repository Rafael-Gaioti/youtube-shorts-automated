# YouTube Shorts Automation with AI

Automação completa para extrair os melhores momentos de vídeos longos do YouTube e transformá-los em Shorts virais usando IA (Whisper + Claude).

## Características

- Download automático de vídeos do YouTube
- Transcrição precisa com Whisper (GPU accelerated)
- Análise inteligente de conteúdo com Claude Sonnet 4
- Identificação automática de momentos virais
- Cortes otimizados para formato Shorts (9:16)
- Pipeline completo em 5 etapas

## Requisitos do Sistema

### Hardware

- **GPU**: NVIDIA RTX 4060 ou superior (8GB VRAM mínimo)
- **RAM**: 16GB recomendado
- **Storage**: 50GB+ de espaço livre
- **SO**: Windows 10/11, Linux (Ubuntu 20.04+), macOS

### Software

- Python 3.10 ou superior
- CUDA Toolkit 11.8+ (para aceleração GPU)
- FFmpeg instalado e configurado no PATH
- Git

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/Rafael-Gaioti/youtube-shorts-automated.git
cd youtube-shorts-automated
```

### 2. Crie e ative o ambiente virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Instale FFmpeg

**Windows:**

```bash
# Usando Chocolatey
choco install ffmpeg

# Ou baixe de: https://ffmpeg.org/download.html
```

**Linux:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**

```bash
brew install ffmpeg
```

### 5. Configure as variáveis de ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite .env e adicione sua chave da API do Claude
ANTHROPIC_API_KEY=sua_chave_aqui
```

Para obter uma chave da API:

1. Acesse [console.anthropic.com](https://console.anthropic.com)
2. Crie uma conta ou faça login
3. Vá em "API Keys" e gere uma nova chave

### 6. Verifique a instalação do CUDA

```bash
python -c "import torch; print(f'CUDA disponível: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A"}')"
```

Saída esperada:

```
CUDA disponível: True
GPU: NVIDIA GeForce RTX 4060
```

## Uso

### Método 1: Pipeline Completo com Claude API

```bash
# Configure primeiro a API key no .env
# ANTHROPIC_API_KEY=sua_chave_aqui

# Execute o pipeline completo
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Método 2: Workflow Híbrido (Recomendado - Sem custo de API)

Este método usa o Claude no browser (gratuito) em vez da API:

**Etapa 1: Download + Transcrição (Automático)**

```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" --stages download,transcribe
```

**Etapa 2: Análise Manual (Claude Browser)**

```bash
# Prepara arquivo para copiar no Claude browser
python scripts/prepare_analysis.py

# Ou especifique o video_id manualmente
python scripts/prepare_analysis.py ff88SpBpkD0
```

Isso cria o arquivo `data/analysis/{video_id}_prepared.txt` com:

- Prompt de análise otimizado
- Transcrição completa com timestamps
- Instruções passo a passo

**Passos para análise manual:**

1. Abra `data/analysis/{video_id}_prepared.txt`
2. Copie todo o conteúdo (Ctrl+A, Ctrl+C)
3. Cole no Claude browser (claude.ai)
4. Copie a resposta JSON do Claude
5. Salve em `data/analysis/{video_id}_analysis.json`

**Etapa 3: Corte (Automático)**

```bash
python scripts/4_cut.py data/raw/{video_id}.mp4
```

**Etapa 4: Exportação (Automático)**

```bash
python scripts/5_export.py
```

### Opções do Pipeline

```bash
# Executar apenas etapas específicas
python main.py "URL" --stages download,transcribe

# Resumir de onde parou (detecta checkpoints)
python main.py "URL" --resume

# Forçar reprocessamento completo
python main.py "URL" --force
```

### Comandos Individuais

```bash
# Download apenas
python scripts/1_download.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Transcrição (processa último vídeo baixado)
python scripts/2_transcribe.py

# Ou especifique o arquivo
python scripts/2_transcribe.py data/raw/VIDEO_ID.mp4

# Corte de vídeo
python scripts/4_cut.py data/raw/VIDEO_ID.mp4

# Exportação
python scripts/5_export.py
```

## Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                   PIPELINE DE AUTOMAÇÃO                      │
└─────────────────────────────────────────────────────────────┘

1. DOWNLOAD (1_download.py)
   ├─ Entrada: URL do YouTube
   ├─ Ação: Download via yt-dlp (vídeo + áudio)
   └─ Saída: data/raw/{video_id}.mp4

2. TRANSCRIÇÃO (2_transcribe.py)
   ├─ Entrada: data/raw/{video_id}.mp4
   ├─ Ação: Whisper large-v3 (GPU) + timestamps
   └─ Saída: data/transcripts/{video_id}.json

3. ANÁLISE (Manual via Claude Browser ou API)
   ├─ Entrada: data/transcripts/{video_id}.json
   ├─ Ação: Claude analisa + viral score
   ├─ Helper: prepare_analysis.py (formata para browser)
   └─ Saída: data/analysis/{video_id}_analysis.json

4. CORTE (4_cut.py)
   ├─ Entrada: data/analysis/{video_id}_analysis.json
   ├─ Ação: FFmpeg extrai segmentos (copy codec)
   └─ Saída: data/cuts/{video_id}_cut_{n}.mp4

5. EXPORTAÇÃO (5_export.py)
   ├─ Entrada: data/cuts/{video_id}_cut_{n}.mp4
   ├─ Ação: Conversão para formato Shorts (9:16, H.264)
   ├─ Validação: Design Auditor Algorítmico + Auto-Fix
   └─ Saída: data/shorts/{video_id}_cut_{n}_short.mp4
```

## Estrutura de Pastas

```
youtube-shorts-automated/
├── config/
│   ├── settings.yaml          # Configurações centralizadas
│   └── prompts/               # Prompts do Claude
│       └── analysis_prompt.txt
├── scripts/
│   ├── 1_download.py          # Download de vídeos
│   ├── 2_transcribe.py        # Transcrição com Whisper
│   ├── 3_analyze.py           # Análise com Claude (API)
│   ├── prepare_analysis.py    # Helper para análise manual
│   ├── 4_cut.py               # Corte de vídeos
│   ├── 5_export.py            # Exportação final
│   └── check_dependencies.py  # Validador de ambiente
├── data/
│   ├── raw/                   # Vídeos baixados
│   ├── transcripts/           # Transcrições JSON
│   ├── analysis/              # Análises da IA + arquivos preparados
│   ├── cuts/                  # Segmentos cortados
│   └── exports/               # Shorts finais (9:16)
├── models/                    # Modelos Whisper (cache)
├── logs/                      # Logs do sistema
├── .env                       # Variáveis de ambiente
├── .env.example               # Exemplo de configuração
├── requirements.txt           # Dependências Python
└── README.md                  # Documentação
```

## Custos Estimados

### Workflow Híbrido (Recomendado - Claude Browser)

| Componente           | Processamento                 | Custo       |
| -------------------- | ----------------------------- | ----------- |
| **Whisper large-v3** | Local (CPU ou GPU)            | R$ 0,00     |
| **Claude (Browser)** | Manual via claude.ai          | R$ 0,00     |
| **FFmpeg**           | Local                         | R$ 0,00     |
| **Total**            | Por vídeo de qualquer duração | **R$ 0,00** |

**Vantagens:**

- Custo zero (usa plano gratuito do Claude)
- Você revisa os cortes antes de processar
- Controle total sobre a análise

### Workflow Automático (Claude API)

| Componente              | Uso por vídeo (60 min)  | Custo        |
| ----------------------- | ----------------------- | ------------ |
| **Whisper**             | Local (GPU/CPU)         | R$ 0,00      |
| **Claude Sonnet 4 API** | ~15K tokens in + 4K out | ~R$ 0,30     |
| **FFmpeg**              | Local                   | R$ 0,00      |
| **Total**               | Por vídeo de 1h         | **~R$ 0,30** |

**Estimativa mensal (100 vídeos):**

- 100 vídeos × R$ 0,30 = **R$ 30,00/mês**
- Processamento 100% automático

## Configuração

Todas as configurações estão centralizadas em [config/settings.yaml](config/settings.yaml):

- **Whisper**: Modelo, device, compute type, VAD
- **Claude**: Modelo, tokens, temperatura
- **Vídeo**: Resolução, codec, bitrate, FPS
- **Cortes**: Duração mín/máx, score mínimo

## Otimizações para RTX 4060

O projeto está otimizado para GPUs com 8GB VRAM:

- `compute_type: float16` - Usa metade da VRAM sem perda significativa
- `batch_size: 16` - Balanceamento entre velocidade e memória
- `vad_filter: true` - Filtra silêncios, reduz processamento
- Cache de modelos - Download único do Whisper large-v3

## Troubleshooting

### Erro: "Could not locate cudnn_ops64_9.dll"

O sistema detectou automaticamente e fez fallback para CPU. Você pode:

**Opção 1: Continuar usando CPU** (funciona perfeitamente, só é mais lento)

- Nenhuma ação necessária
- Transcrição de 5min leva ~5-10min

**Opção 2: Instalar cuDNN para acelerar com GPU**

1. Baixe cuDNN 9 de: https://developer.nvidia.com/cudnn-downloads
2. Extraia para: `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x`
3. Reinicie o pipeline - vai usar GPU automaticamente

### Erro: CUDA out of memory

Reduza o modelo do Whisper em [config/settings.yaml](config/settings.yaml):

```yaml
whisper_config:
  model_size: "medium" # ou "small"
```

### Erro: FFmpeg not found

Verifique se FFmpeg está no PATH:

```bash
ffmpeg -version
```

### Erro: Transcrição muito lenta

Verifique se está usando GPU:

```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

Se `CUDA: False`, verifique instalação do PyTorch com CUDA:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Workflow híbrido: Arquivo analysis.json não encontrado

Certifique-se de:

1. Executar `python scripts/prepare_analysis.py`
2. Copiar resposta do Claude browser
3. Salvar em `data/analysis/{video_id}_analysis.json` (não .txt!)

## Desenvolvimento

### Type Hints e Docstrings

Todo código utiliza type hints e docstrings seguindo PEP 484 e PEP 257:

```python
from pathlib import Path
from typing import List, Dict

def process_video(video_path: Path, max_cuts: int = 5) -> List[Dict[str, float]]:
    """
    Processa um vídeo e retorna os melhores cortes.

    Args:
        video_path: Caminho para o arquivo de vídeo
        max_cuts: Número máximo de cortes a extrair

    Returns:
        Lista de dicionários com timestamps e scores
    """
    pass
```

### Logging

Sistema de logging configurável em [config/settings.yaml](config/settings.yaml):

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Processamento iniciado")
logger.error("Erro ao processar vídeo", exc_info=True)
```

## Roadmap

- [ ] Interface web com Streamlit
- [ ] Upload automático para YouTube Shorts
- [ ] Análise de tendências (trending topics)
- [ ] Legendas automáticas com destaque
- [ ] Suporte a múltiplos idiomas
- [ ] API REST para integração
- [ ] Dashboard de analytics

## Contribuindo

Contribuições são bem-vindas! Por favor:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Add: Minha nova feature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

## Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## Contato

Rafael Gaioti - [@Rafael-Gaioti](https://github.com/Rafael-Gaioti)

Link do Projeto: [https://github.com/Rafael-Gaioti/youtube-shorts-automated](https://github.com/Rafael-Gaioti/youtube-shorts-automated)

---

**Nota**: Este projeto é para fins educacionais. Respeite os direitos autorais e termos de serviço do YouTube ao usar esta ferramenta.
