# Shorts SaaS: Visão e Roadmap do Produto

Este documento traça o caminho para transformar o pipeline de scripts local em uma plataforma profissional de criação automática de canais.

## 🎯 A Visão

Um portal centralizado onde qualquer usuário pode lançar um canal de Shorts lucrativo em minutos. O sistema resolve toda a complexidade técnica (extração, IA, edição, legendas, upload) e o usuário foca na estratégia.

---

## 🏗️ Arquitetura Proposta (SaaS)

### 1. Front-end & Dashboard (Web)

- **Tecnologia**: Next.js ou React.
- **Funcionalidades**:
  - **Niche Selector**: Marketplace de nichos validados (Finanças, Fitness, Curiosidades, etc.).
  - **Real-time Pipeline**: Barra de progresso ao vivo para cada vídeo ("Transcrevendo...", "Renderizando...", "Upload em 80%").
  - **Metrics Center**: Dashboard profissional conectada à YouTube Analytics API.
  - **Configuration**: Gestão de chaves API (OpenAI, Anthropic) e OAuth2 (YouTube).

### 2. Backend & State (Supabase)

- **Multi-tenancy**: Adição de tabelas `users`, `channels` e `profiles`.
- **Real-time**: Uso de Supabase Realtime para atualizar o Dashboard sem refresh.
- **Storage**: Armazenamento centralizado de templates de fontes, cores e músicas.

### 2. Distributed Workers (Orquestração)

- **O PC Local (ou GPU Cloud)**: Atua como um "Worker". Ele recebe tarefas do Supabase, processa (usando a GPU para Whisper/FFmpeg) e devolve o resultado.
- **n8n / API Central**: Coordena a distribuição de carga entre múltiplos workers.

---

## 💎 Dashboards Profissionais

### 📺 Monitor de Operação (Real-time)

- **Fila de Espera**: Quantos vídeos no `discovered`.
- **Gargalos**: Alertas se a GPU estiver lenta.
- **Status Visual**: Grid de cards com o frame do vídeo e o status atual em cores (Verde: Sucesso, Azul: Processando, Vermelho: Erro).

### 📈 Painel de Performance (Métricas)

- **KPIs**: Views, Retenção Média, Cliques no link da bio.
- **ROI Real**: Comparativo de custo de API vs. Performance do vídeo.
- **A/B Testing**: Qual nicho ou estilo de legenda está performando melhor.

---

## 🗺️ Roadmap de Evolução

### Fase 1: Padronização Local (Onde estamos)

- [x] Unificar scripts em um Master Pipeline estável.
- [x] Estado centralizado no Supabase.
- [ ] Dashboards iniciais via Streamlit ou ferramenta low-code.

### Fase 2: Plataforma Web & Multi-Nicho

- [ ] Criar o Portal Web (Login/Dashboard).
- [ ] Implementar a lógica de "Niches" (Presets de Prompts e Estilos).
- [ ] Sistema de notificações (Telegram/Email para vídeos prontos).

### Fase 3: Escala SaaS

- [ ] Migrar processamento local para Workers na nuvem (opcional).
- [ ] Sistema de Assinatura/Créditos por canais.

### Fase 4: Performance Feedback Loop

- [ ] Executar rodada de teste em lote (Batch Run) manual para verificar o fluxo ponta a ponta.
- [ ] Integrar `7_metrics.py` com Supabase.
- [ ] Criar `8_correlate.py` para análise de performance.
- [ ] Atualizar n8n com cronograma de métricas/correlação.
- [ ] Gerar primeiro relatório de Performance Insights.

### Fase 5: SaaS Evolution

- [ ] Desenhar e construir o "Operational Dashboard" (Next.js/Supabase Realtime).
- [ ] Implementar abstração de "Niche Settings" (Prompts e Estilos dinâmicos).
- [ ] Construir o "Metrics Dashboard" para performance do canal e ROI.
- [ ] Refatorar os Workers para suporte a canais multi-inquilino (multi-tenant).

---

## 🛠️ Próximos Passos Imediatos

1.  **Dashboard de Operação**: Criar uma primeira versão visual para ver a "fase" de cada vídeo em tempo real.
2.  **Métricas**: Finalizar a integração de dados do YouTube para o Supabase.
3.  **Configuração de Nicho**: Abstrair as configurações de prompts e estilos para que mudar de nicho seja apenas trocar uma variável.
