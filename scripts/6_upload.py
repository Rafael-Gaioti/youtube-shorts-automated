"""
6_upload.py — Upload automático de Shorts para o YouTube

Uso:
    python scripts/6_upload.py data/analysis/{video_id}_analysis.json [--profile recommended]
    python scripts/6_upload.py data/analysis/{video_id}_analysis.json --dry-run
    python scripts/6_upload.py data/analysis/{video_id}_analysis.json --privacy unlisted

Primeira execução: abre o browser para autenticação OAuth2.
Token salvo em config/youtube_token.json para reutilização.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Google API
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    print(
        "❌ Dependências do Google não instaladas.\n"
        "   Execute: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Scopes necessários para upload e leitura de métricas (Data API + Analytics API)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Caminho padrão para os arquivos de autenticação
CLIENT_SECRETS_PATH = Path("client_secrets.json")
TOKEN_PATH = Path("config/youtube_token.json")

# Tipos de conteúdo para descrição
CONTENT_TYPE_LABELS = {
    "financial_mistake": "💸 Erro financeiro com lição",
    "success_revelation": "🚀 Revelação de sucesso",
    "dramatic_transformation": "🔥 Transformação dramática",
    "controversial_opinion": "⚡ Opinião polêmica",
    "emotional_breakdown": "💔 Momento emocional",
    "behind_the_scenes": "🎬 Bastidores",
    "insight": "💡 Insight valioso",
}

# Hashtags padrão (Nicho: Produtividade/Performance)
DEFAULT_HASHTAGS = ["#shorts", "#produtividade", "#motivação", "#mindset"]


def get_authenticated_service():
    """
    Autentica com OAuth2 e retorna o serviço YouTube.
    Na primeira execução, abre o browser para autorização.
    """
    creds = None

    # Encontrar o client_secrets.json — suporta o nome longo do Google
    secrets_path = _find_client_secrets()
    if not secrets_path:
        logger.error(
            "❌ client_secrets.json não encontrado.\n"
            "   Baixe as credenciais OAuth2 do Google Cloud Console e coloque na raiz do projeto."
        )
        sys.exit(1)

    # Carregar token salvo se existir
    TOKEN_PATH.parent.mkdir(exist_ok=True)
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Renovar ou autenticar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Token expirado. Renovando...")
            creds.refresh(Request())
        else:
            logger.info("Iniciando autenticação OAuth2 — o browser será aberto...")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Salvar token para próximas execuções
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        logger.info(f"Token salvo em: {TOKEN_PATH}")

    return build("youtube", "v3", credentials=creds)


def _find_client_secrets() -> Path | None:
    """Encontra o client_secrets.json — suporta o nome longo gerado pelo Google."""
    # Prioridade: nome padrão
    if CLIENT_SECRETS_PATH.exists():
        return CLIENT_SECRETS_PATH

    # Buscar por arquivos client_secret_*.json na raiz
    candidates = list(Path(".").glob("client_secret_*.json"))
    if candidates:
        logger.info(f"Usando client_secrets: {candidates[0].name}")
        return candidates[0]

    return None


def build_video_title(cut: dict, max_len: int = 95) -> str:
    """
    Gera o título do Short com base nos campos de análise.

    Estratégia de prioridade (Alta Performance/Produtividade):
    1. youtube_title — gerado via IA pelos templates (máx 8 palavras)
    2. on_screen_text — compacto e impactante (geralmente em CAPS)
    3. hook — os primeiros 3s (pode ser longo mas é o mais relevante)
    """
    # 1. youtube_title gerado pela IA (Regra dos 3 Templates)
    yt_title = cut.get("youtube_title", "").strip()
    if yt_title:
        # Garante que não ultrapassa limite, mas a IA já deve mandar curto
        if len(yt_title) <= max_len:
            return yt_title
        return yt_title[: max_len - 3].rsplit(" ", 1)[0] + "..."

    # 2. on_screen_text: curto, impactante, feito para ser lido
    on_screen = cut.get("on_screen_text", "").strip()
    if on_screen and len(on_screen) >= 10:
        title = on_screen.title()  # "ERRO QUE ME CUSTOU" → "Erro Que Me Custou"
        if len(title) <= max_len:
            return title

    # 3. hook: primeiros 3s — trunca se muito longo
    hook = cut.get("hook", "").strip()
    if hook and len(hook) >= 10:
        # Remover reticências no início (transcrições às vezes começam com "...")
        hook = hook.lstrip(".").strip()
        # Capitalizar primeira letra
        hook = hook[0].upper() + hook[1:] if hook else hook
        if len(hook) > max_len:
            # Cortar na última palavra que caiba + reticências
            hook = hook[: max_len - 3].rsplit(" ", 1)[0] + "..."
        return hook

    # 4. fallback
    return cut.get("rationale", cut.get("reason", "Short rápido"))[:max_len]


def build_description(cut: dict, profile_settings: dict | None = None) -> str:
    """Gera a descrição do Short."""
    lines = []

    # 1. Gancho/Contexto da IA formatado
    yt_title = cut.get("youtube_title", "").strip()
    hook = cut.get("hook", "").strip()

    if yt_title:
        lines.append(yt_title)
        lines.append("")
    elif hook:
        lines.append(f"A reflexão de hoje: {hook}")
        lines.append("")

    # Tipo de conteúdo
    content_type = cut.get("content_type", "")
    label = CONTENT_TYPE_LABELS.get(content_type, "")
    if label:
        lines.append(label)
        lines.append("")

    # Call To Action (do perfil)
    if profile_settings:
        cta = profile_settings.get("upload_settings", {}).get(
            "default_description_footer"
        )
        if cta:
            lines.append(cta)
            lines.append("")

    # Hashtags
    hashtags = DEFAULT_HASHTAGS.copy()
    keywords = cut.get("keywords", [])
    for kw in keywords[:3]:
        tag = f"#{kw.replace(' ', '').lower()}"
        if tag not in hashtags:
            hashtags.append(tag)

    lines.append(" ".join(hashtags))
    return "\n".join(lines)


def build_tags(cut: dict) -> list:
    """Gera as tags do vídeo."""
    base_tags = ["shorts", "empreendedorismo", "negócios", "motivação"]
    keywords = cut.get("keywords", [])
    emotions = cut.get("emotions", [])
    return list(set(base_tags + keywords[:5] + emotions[:3]))


def upload_short(
    youtube,
    video_path: Path,
    cut: dict,
    privacy: str = "private",
    profile_settings: dict | None = None,
    dry_run: bool = False,
) -> dict | None:
    """
    Faz upload de um Short para o YouTube.

    Args:
        youtube: serviço autenticado
        video_path: path do arquivo .mp4
        cut: dados do corte (analysis.json)
        privacy: 'private', 'unlisted', 'public'
        profile_settings: configurações do perfil SaaS
        dry_run: se True, apenas exibe o que seria feito

    Returns:
        dict com youtube_video_id e metadados, ou None em caso de erro
    """
    title = build_video_title(cut)
    description = build_description(cut, profile_settings)
    tags = build_tags(cut)

    logger.info(f"📤 Preparando upload: {video_path.name}")
    logger.info(f"   Título: {title}")
    logger.info(f"   Privacidade: {privacy}")
    logger.info(f"   Tags: {', '.join(tags[:5])}")

    if dry_run:
        logger.info("   [DRY RUN] Upload não realizado.")
        return {
            "youtube_video_id": "DRY_RUN",
            "title": title,
            "privacy": privacy,
            "dry_run": True,
        }

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs (mais comum para Shorts brasileiros)
            "defaultLanguage": "pt",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        logger.info("   Enviando...")
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"   Progresso: {pct}%")

        video_id = response["id"]
        url = f"https://youtube.com/shorts/{video_id}"
        logger.info(f"   ✅ Upload concluído: {url}")

        return {
            "youtube_video_id": video_id,
            "youtube_url": url,
            "title": title,
            "privacy": privacy,
            "tags": tags,
        }

    except HttpError as e:
        error_content = json.loads(e.content.decode())
        reason = (
            error_content.get("error", {})
            .get("errors", [{}])[0]
            .get("reason", "unknown")
        )
        logger.error(f"   ❌ Erro no upload (HTTP {e.resp.status}): {reason}")
        logger.error(f"      Detalhes: {e.content.decode()[:300]}")
        return None


def save_upload_record(video_id: str, cut_index: int, result: dict, analysis: dict):
    """Salva o registro do upload em data/uploads/{video_id}_uploads.json."""
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    record_path = uploads_dir / f"{video_id}_uploads.json"

    # Carregar registro existente ou criar novo
    records = []
    if record_path.exists():
        with open(record_path, "r", encoding="utf-8") as f:
            records = json.load(f)

    cut = analysis["cuts"][cut_index]
    records.append(
        {
            "cut_index": cut_index + 1,
            "local_file": f"data/shorts/{video_id}_cut_{cut_index + 1:02d}_short.mp4",
            "youtube_video_id": result.get("youtube_video_id"),
            "youtube_url": result.get("youtube_url"),
            "title": result.get("title"),
            "privacy": result.get("privacy"),
            "viral_score": cut.get("viral_score"),
            "hook_strength": cut.get("hook_strength"),
            "opening_pattern": cut.get("opening_pattern"),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )

    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    logger.info(f"   Registro salvo em: {record_path}")


def run_autonomous_upload(
    profile_settings, privacy="private", dry_run=False, target_count=2
):
    """Lê os vídeos 'exported' do banco de dados e realiza o upload."""
    from scripts.utils import supabase_client

    logger.info("Modo autônomo. Buscando shorts exportados no Supabase...")
    exported_cuts = supabase_client.get_cuts_by_status("exported")

    if not exported_cuts:
        logger.info("Nenhum short 'exported' aguardando upload no banco.")
        return

    youtube = None
    if not dry_run:
        youtube = get_authenticated_service()

    analysis_dir = Path("data/analysis")
    shorts_dir = Path("data/shorts")
    results = []

    # Limitar quantidade diária de uploads aqui
    if target_count:
        exported_cuts = exported_cuts[:target_count]

    for cut_record in exported_cuts:
        video_code = cut_record.get("videos", {}).get("video_code")
        cut_index = cut_record.get("cut_index")

        if not video_code:
            continue

        analysis_path = analysis_dir / f"{video_code}_analysis.json"
        if not analysis_path.exists():
            logger.error(f"Analysis file missing: {analysis_path}. Pulando.")
            continue

        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)

        cuts = analysis.get("cuts", [])
        actual_idx = cut_index - 1
        if actual_idx < 0 or actual_idx >= len(cuts):
            logger.error(f"Cut {cut_index} invalid length {len(cuts)}")
            continue

        cut = cuts[actual_idx]

        # Padrão 1
        short_path = shorts_dir / f"{video_code}_cut_{cut_index:02d}_short.mp4"

        # Padrão 2
        if not short_path.exists():
            thumb_hook = cut.get("thumbnail_hook", "")
            if thumb_hook:
                base_name = (
                    thumb_hook.replace(" ", "-")
                    .replace("?", "")
                    .replace("!", "")
                    .replace(".", "")
                    .upper()
                )
                alt_path = shorts_dir / f"{base_name}_C{cut_index:02d}.mp4"
                if alt_path.exists():
                    short_path = alt_path

        if not short_path.exists():
            logger.warning(f"Short não encontrado: {short_path.name} — pulando.")
            continue

        result = upload_short(
            youtube, short_path, cut, privacy, profile_settings, dry_run
        )

        if result:
            save_upload_record(video_code, actual_idx, result, analysis)
            results.append(result)
            supabase_client.update_cut_status(video_code, cut_index, "uploaded")
            logger.info(
                f"✅ Status do short {video_code}_{cut_index:02d} atualizado para 'uploaded' no banco!"
            )

        if len(exported_cuts) > 1:
            logger.info("   Aguardando 5s antes do próximo upload...")
            time.sleep(5)

    logger.info(f"\nUPLOADS AUTÔNOMOS CONCLUÍDOS: {len(results)}/{len(exported_cuts)}")


def main():
    parser = argparse.ArgumentParser(description="Upload de Shorts para o YouTube")
    parser.add_argument(
        "analysis_file",
        type=str,
        nargs="?",
        help="Path do analysis.json (opcional — usa o mais recente se omitido)",
    )
    parser.add_argument(
        "--profile", type=str, default="recommended", help="Perfil de usuário"
    )
    parser.add_argument(
        "--privacy",
        type=str,
        default="private",
        choices=["private", "unlisted", "public"],
        help="Privacidade do vídeo (padrão: private — revise antes de publicar)",
    )
    parser.add_argument(
        "--cut",
        type=int,
        default=None,
        help="Índice do corte específico a fazer upload (1, 2, 3). Padrão: todos",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular upload sem enviar nada",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Apenas realizar a autenticação OAuth2 e sair",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2,
        help="Quantidade de vídeos para upload no modo autônomo",
    )
    args = parser.parse_args()

    # Carregar configurações do Perfil para usar depois
    from scripts.utils import settings_manager

    settings = settings_manager.get_settings(args.profile)

    # Modo apenas Autenticação
    if args.auth:
        logger.info("Modo Autenticação selecionado.")
        get_authenticated_service()
        logger.info("✅ Autenticação concluída com sucesso!")
        sys.exit(0)

    # Modo autônomo baseado no Supabase
    if not args.analysis_file:
        logger.info(
            "Nenhum arquivo de análise especificado. Iniciando Modo Autônomo..."
        )
        run_autonomous_upload(
            profile_settings=settings,
            privacy=args.privacy,
            dry_run=args.dry_run,
            target_count=args.limit,
        )
        sys.exit(0)

    # Carregar analysis.json explicitamente
    analysis_path = Path(args.analysis_file)

    if not analysis_path.exists():
        logger.error(f"Arquivo não encontrado: {analysis_path}")
        sys.exit(1)

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    video_id = analysis["video_id"]
    cuts = analysis.get("cuts", [])

    if not cuts:
        logger.error("Nenhum corte encontrado no analysis.json.")
        sys.exit(1)

    # Filtrar cortes a fazer upload
    if args.cut:
        idx = args.cut - 1
        if idx >= len(cuts):
            logger.error(f"Corte {args.cut} não existe (total: {len(cuts)})")
            sys.exit(1)
        cuts_to_upload = [(idx, cuts[idx])]
    else:
        cuts_to_upload = list(enumerate(cuts))

    # Autenticar (pula se dry-run)
    youtube = None
    if not args.dry_run:
        youtube = get_authenticated_service()

    logger.info(f"\n{'=' * 55}")
    logger.info(f"  UPLOAD — {video_id} ({len(cuts_to_upload)} short(s))")
    logger.info(f"  Privacidade: {args.privacy}")
    logger.info(f"{'=' * 55}")

    shorts_dir = Path("data/shorts")
    results = []

    for cut_idx, cut in cuts_to_upload:
        # Padrão 1: vídeo_id_cut_01_short.mp4 (Clássico)
        short_path = shorts_dir / f"{video_id}_cut_{cut_idx + 1:02d}_short.mp4"

        # Padrão 2: HOOK-NAME_C01.mp4 (Novo Estilo Human-Readable do 5_export.py)
        if not short_path.exists():
            thumb_hook = cut.get("thumbnail_hook", "")
            if thumb_hook:
                base_name = (
                    thumb_hook.replace(" ", "-")
                    .replace("?", "")
                    .replace("!", "")
                    .replace(".", "")
                    .upper()
                )
                alt_path = shorts_dir / f"{base_name}_C{cut_idx + 1:02d}.mp4"
                if alt_path.exists():
                    short_path = alt_path

        if not short_path.exists():
            logger.warning(f"Short não encontrado: {short_path.name} — pulando.")
            continue

        result = upload_short(
            youtube=youtube,
            video_path=short_path,
            cut=cut,
            privacy=args.privacy,
            dry_run=args.dry_run,
        )

        if result:
            save_upload_record(video_id, cut_idx, result, analysis)
            results.append(result)

        # Aguardar entre uploads para evitar rate limit
        if len(cuts_to_upload) > 1 and cut_idx < len(cuts_to_upload) - 1:
            logger.info("   Aguardando 5s antes do próximo upload...")
            time.sleep(5)

    # Sumário final
    logger.info(f"\n{'=' * 55}")
    logger.info(f"  UPLOADS CONCLUÍDOS: {len(results)}/{len(cuts_to_upload)}")
    for r in results:
        url = r.get("youtube_url", "DRY_RUN")
        logger.info(f"  ✅ {r['title'][:50]}...")
        logger.info(f"     {url}")
    logger.info(f"{'=' * 55}")


if __name__ == "__main__":
    main()
