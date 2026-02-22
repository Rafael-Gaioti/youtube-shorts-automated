# Fase de Consistência — Shorts Automated

## Objetivo Estratégico

Transformar o pipeline atual em um motor consistente de retenção para canais próprios.

**Consistência > Viral isolado.**

---

## Definição de Consistência

O sistema será considerado consistente quando atingir:

- Retenção média > 65%
- Taxa de conclusão > 50%
- Pelo menos 30% dos Shorts acima de 10k views
- Pelo menos 1 Short acima de 100k views por mês
- Performance estável por 60 dias

---

## Regras da Fase

1. Escolher 1 único nicho por 60 dias
2. Não alterar identidade visual durante testes
3. Não mudar múltiplas variáveis ao mesmo tempo
4. Produzir volume controlado
5. Medir tudo

---

## Implementações Técnicas

### ✅ 4. Ajustes no 3_analyze.py — CONCLUÍDO

Campos adicionados ao output de análise:

| Campo                 | Range | Descrição                                                    |
| --------------------- | ----- | ------------------------------------------------------------ |
| `hook_strength`       | 0–10  | Força do gancho nos primeiros 3s                             |
| `opening_pattern`     | str   | `contrarian`, `emotional`, `authority`, `curiosity`, `story` |
| `emotional_intensity` | 0–10  | Intensidade emocional geral                                  |
| `loop_potential`      | 0–10  | Probabilidade de reassistir                                  |

Novo foco no prompt: Maximizar força dos **primeiros 3 segundos** como ponto de START do corte.

---

### ✅ 1. Upload Automático — CONCLUÍDO

`scripts/6_upload.py` — funcional:

- Upload via YouTube Data API v3 com OAuth2
- Título baseado no `hook` dos primeiros 3s
- Descrição com hashtags geradas das `keywords`
- Privacidade configurável: `private`, `unlisted`, `public`
- Flag `--dry-run` para simular sem enviar
- Registro em `data/uploads/{video_id}_uploads.json`
- Quota: ~6 uploads/dia no plano gratuito

---

### 2. Coleta de Métricas — PENDENTE

Criar: `scripts/7_metrics.py`

Buscar via API:

- `views`, `averageViewDuration`, `averageViewPercentage`, `likes`, `comments`

Salvar em: `data/metrics/{short_id}_metrics.json`

```json
{
  "short_id": "...",
  "analysis_id": "...",
  "hook_strength": 9,
  "opening_pattern": "contrarian",
  "views": 12034,
  "avg_view_duration": 28.4,
  "avg_view_percentage": 72.3,
  "likes": 540,
  "comments": 32
}
```

---

### 3. Feedback Loop — PENDENTE

Criar: `scripts/8_correlate.py`

Cruzar:

- `viral_score`, `hook_strength`, `opening_pattern`, `emotional_intensity`
- com métricas reais de views/retenção

Gerar relatório em: `data/reports/performance_report.json`

**Objetivo:** Identificar padrões de retenção real vs score da IA e ajustar o prompt.

---

## Plano Operacional (60 Dias)

### Dias 1–7

- [x] Ajustes no `3_analyze.py` (hook_strength, opening_pattern, etc.)
- [x] Consolidar o sistema (--force, log por vídeo, batch URLs)
- [x] Implementar upload automático (`6_upload.py`) ✅
- [ ] Integrar upload no `pipeline.py` com flag `--upload`
- [ ] Implementar coleta de métricas (`7_metrics.py`)
- [ ] Escolher nicho fixo
- [ ] Definir padrão de título

### Dias 8–30

- Publicar 2 Shorts por dia
- Mesmo padrão visual
- Duração alvo: 30–45 segundos
- Não alterar múltiplas variáveis

### Dias 31–45

- Rodar script de correlação (`8_correlate.py`)
- Ajustar heurística do `3_analyze.py` com base em dados reais
- Testar variação leve de duração

### Dias 46–60

- Escalar para 3 Shorts/dia
- Manter apenas padrões vencedores
- Validar repetibilidade

---

## Critério Para Próxima Fase

Avançar para revenda apenas quando:

- Existir padrão replicável
- Retenção consistente por 3 meses
- Pipeline totalmente automatizado
- Capacidade de operar múltiplos canais

---

## Norte do Projeto

**Produzir → Medir → Ajustar → Repetir**

A consistência validará o modelo. Depois disso, a revenda vira consequência.
