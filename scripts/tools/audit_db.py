from scripts.utils.supabase_client import get_supabase_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_AUDIT")


def audit():
    client = get_supabase_client()
    if not client:
        print("Erro ao conectar ao Supabase.")
        return

    res = client.table("videos").select("*").execute()
    data = res.data if hasattr(res, "data") else res[1]

    print(f"Total de vídeos encontrados: {len(data)}")
    for v in data[:5]:
        print(f"- [{v['stage']}] {v['title']} ({v['video_code']})")


if __name__ == "__main__":
    audit()
