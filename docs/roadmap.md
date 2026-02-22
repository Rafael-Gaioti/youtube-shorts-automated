# Roadmap — Próximos Passos

> Prioridades definidas com base no estado atual (Fev 2026)

---

## 🔴 Alta Prioridade

### 1. Integrar upload no `pipeline.py`

- Adicionar flag `--upload` para fazer upload automaticamente após o export
- **Ação:** chamar `6_upload.py` ao final do fluxo se `--upload` for passado

### 2. Coleta de Métricas

- Buscar métricas após upload: views, `averageViewDuration`, `averageViewPercentage`, likes, comments
- **Ação:** criar `scripts/7_metrics.py`
- Salvar em: `data/metrics/{short_id}_metrics.json`

### 3. Feedback Loop (correlação IA x performance real)

- Cruzar `viral_score`, `hook_strength`, `opening_pattern`, `emotional_intensity` com métricas reais
- **Ação:** criar `scripts/8_correlate.py`
- Gerar relatório em: `data/reports/performance_report.json`

---

## 🟡 Média Prioridade

### 4. Interface de revisão antes do upload

- Antes de fazer upload, mostrar preview dos shorts para aprovar/rejeitar
- **Ação:** criar `scripts/tools/review_shorts.py`

### 5. Modo canal estável

- O `0_discover.py` + discovery queue funciona mas não é testado regularmente
- **Ação:** testar e documentar o fluxo completo do modo canal

---

## 🟢 Baixa Prioridade / Futuro

### 6. Deploy em cloud / agendamento

- Rodar o pipeline automaticamente todos os dias para novos vídeos do canal
- Opções: GitHub Actions, servidor Linux com cron, ou n8n

### 7. Suporte a outros idiomas

- Testar com vídeos em inglês e espanhol
- A diarização e o Whisper já suportam, mas o prompt da IA está em PT

### 8. Dashboard de analytics

- Correlacionar `viral_score` da IA com métricas reais ao longo do tempo
- Identificar quais `opening_pattern` e `content_type` performam melhor

## ✅ Concluído

- [x] Transcrição com GPU + diarização de speakers
- [x] Cores distintas por speaker (amarelo/ciano)
- [x] Font size 52 para mobile
- [x] Pipeline unificado com `--url`
- [x] Skip inteligente de etapas já executadas
- [x] Correção do escaping do filtro `subtitles=` no Windows
- [x] Organização do projeto (`docs/`, `scripts/tools/`)
- [x] `--force-analyze` e `--force-cut` no pipeline
- [x] `--urls-file` para processamento em batch
- [x] Log por vídeo em `logs/{video_id}_{timestamp}.log`
- [x] Sumário final com scores e tamanhos dos shorts gerados
- [x] Limpeza automática de arquivos temp `.ass`
- [x] Campos de retenção no `3_analyze.py`: `hook_strength`, `opening_pattern`, `emotional_intensity`, `loop_potential`
- [x] Prompt com foco nos primeiros 3 segundos como ponto de START
- [x] `data/cuts/` removida (obsoleta)
- [x] `min_viral_score` unificado (settings.yaml = 5.0 fallback, perfis têm prioridade)
- [x] **Upload automático para YouTube** (`6_upload.py`) — OAuth2, privado/público/não-listado, registro em `data/uploads/`
- [x] Legendas com estilo mais avançado (Título Outline+Sombra e Box translúcida nas legendas ASS)
