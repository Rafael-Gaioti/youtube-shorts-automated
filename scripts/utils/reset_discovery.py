import sqlite3
import os
from pathlib import Path


def reset_discovery_history():
    db_path = Path("data/discovery_history.db")
    if db_path.exists():
        print(f"Limpando histórico de descoberta: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM processed_videos")
        conn.commit()
        conn.close()
        print("Histórico limpo com sucesso!")
    else:
        print("Nenhum histórico encontrado para limpar.")


if __name__ == "__main__":
    reset_discovery_history()
    # Também limpa a fila atual para garantir um fresh start
    queue_path = Path("data/discovery_queue.json")
    if queue_path.exists():
        queue_path.write_text("[]", encoding="utf-8")
        print("Fila de descoberta zerada.")
