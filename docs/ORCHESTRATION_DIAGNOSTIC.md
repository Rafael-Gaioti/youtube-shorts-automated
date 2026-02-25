# Diagnóstico de Orquestração Híbrida - Shorts AI

Este documento contém a especificação técnica para construir o workflow de orquestração no n8n.
**Cenário**: n8n rodando em Servidor Linux (24/7) e Projeto rodando em Windows Local (On-demand via SSH).

---

## 1. Arquitetura Híbrida

| Camada           | Host           | Papel                              | Requisito                 |
| :--------------- | :------------- | :--------------------------------- | :------------------------ |
| **Orquestrador** | Servidor Linux | n8n (24/7), Discovery, Upload      | Python 3.9+, Supabase     |
| **Processador**  | Windows Local  | Transcrição (GPU), Cortes e Export | Windows OpenSSH, RTX 4060 |

---

## 2. Configuração do Servidor (Linux)

O servidor remoto deve rodar apenas os scripts de gerenciamento (Discovery e Upload).

- **Pasta do Projeto**: Recomenda-se clonar o repositório ou copiar os scripts/config.
- **Dependências**: `pip install -r requirements_server.txt`
- **Variáveis**: `.env` deve conter `SUPABASE_URL` e `SUPABASE_KEY`.

---

## 3. Interface de Comandos (CLI)

### A. No Servidor (Linux) - Local Execution do n8n

**Gatilho de Discovery (02:00 AM)**:

```bash
python3 scripts/0_discover.py
```

_Se o discovery encontrar vídeos novos, o n8n deve disparar o nó SSH para o Windows._

**Gatilho de Upload (Estratégico)**:

```bash
python3 scripts/6_upload.py --limit 1
```

### B. No Windows (via SSH Node no n8n)

O n8n deve usar um nó **SSH** apontando para o IP/Host do seu Windows.
**Comando de Processamento**:

```powershell
cmd.exe /c "cd /d c:\Users\gaiot\Projetos\shorts_cortes_ai && .venv\Scripts\python.exe scripts\master_pipeline.py"
```

---

## 4. Guia para o GPT (Prompt de Construção)

"Construa um workflow no n8n para o projeto `shorts_cortes_ai` seguindo estes requisitos:

1. **Trigger Cron**: Rodar às 02:00.
2. **Nó de Execução Local (Linux)**: Rodar `python3 scripts/0_discover.py`.
3. **Lógica de Decisão**: Consultar o Supabase (ou ler o stdout do discovery) para saber se há novos vídeos.
4. **Nó SSH**: Se houver trabalho, conectar ao Windows e rodar o `master_pipeline.py`.
5. **Trigger de Upload**: Rodar às 10h, 14h, 18h e 21h chamando `python3 scripts/6_upload.py --limit 1` localmente no servidor."

---

## 5. Por que Híbrido?

- **Economia**: Você não precisa deixar o Windows ligado 24h. Ele só precisa estar ligado durante a madrugada quando o n8n der o comando de processamento.
- **Escalabilidade**: O Discovery e o monitoramento de uploads rodam no servidor estável.
- **Performance**: O trabalho de IA (Whisper/GPU) continua acontecendo onde o hardware é forte.
