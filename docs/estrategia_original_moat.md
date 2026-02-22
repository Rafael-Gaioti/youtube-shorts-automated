# 🧠 Estratégia, Visão de Produto e Moat Técnico

Este documento detalha o pensamento estratégico por trás do projeto `shorts_cortes_ai`. Não somos apenas um script de corte; somos uma fábrica de conteúdo de alta retenção otimizada para custo zero.

## 1. Visão de Mercado (The "Pink Cow" Strategy)

No mar de milhares de canais de cortes automatizados, a maioria falha porque:

1. **Legendas Médias**: Usam legendas estáticas ou de uma cor só.
2. **Falta de Título**: Não usam headlines fixas para prender a atenção (Hook visual).
3. **Cortes sem Contexto**: Cortam por tempo, não por narrativa.

**Nossa Diferenciação:**

- **Diarização (Multi-Speaker)**: Atribuímos cores únicas a cada orador (Amarelo para o host, Ciano para o convidado). Isso aumenta a imersão e reduz o esforço cognitivo do espectador.
- **Efeito Zoom-Pop**: Legendas dinâmicas que "saltam" na tela, técnica de editores profissionais de elite.
- **Seleção por Viral_Score**: Usamos LLMs (Llama 3) para agir como diretores de arte, escolhendo momentos baseados em "Punchlines" e "Hooks".

## 2. Moat Técnico (Defesa de Negócios)

Nossa vantagem competitiva (Moat) é a **descorrelação entre escala e custo**.

| Componente      | Solução Comum (Custo)            | Nossa Solução (Custo Zero)    | Vantagem                         |
| :-------------- | :------------------------------- | :---------------------------- | :------------------------------- |
| **Discovery**   | YouTube Data API (Cota Limitada) | `yt-dlp` scraping             | Busca ilimitada e escalável.     |
| **Transcrição** | OpenAI Whisper API ($$$)         | `Faster-Whisper` Local (CUDA) | Transcrição infinita e privada.  |
| **Análise**     | GPT-4o / Claude 3.5 ($$$)        | `Llama 3` via Ollama Local    | Análise profunda e ilimitada.    |
| **Edição**      | Adobe Premiere / CapCut          | `FFmpeg` Automatisado         | Exportação em massa em segundos. |

## 3. Estratégia de Conteúdo (Gold Miners)

Focamos em **Podcasts de Business e Mindset**.

- **Por quê?** São vídeos longos (mais de 1h) com densidade de "pérolas" de sabedoria.
- **Fator Viral**: Dinheiro, Erros de Negócios e Revelações Chocantes são os tópicos que mais geram compartilhamento e retenção.

## 4. Próximos Passos Estratégicos

- [ ] **Multi-Channel Monitoring**: Escalar de 2 para 20 canais simultâneos.
- [ ] **A/B Testing de Headlines**: Criar 2 versões de cada corte com títulos diferentes para otimizar o gancho inicial.
- [ ] **Auto-Upload**: Integrar com APIs de redes sociais (após validação humana dos cortes).
