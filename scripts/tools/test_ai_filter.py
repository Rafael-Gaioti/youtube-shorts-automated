from scripts.utils import supabase_client
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


def test_niche_filter(title):
    client = OpenAI()
    prompt = f"""Analise o título do vídeo e responda 'SIM' se ele for relevante para o nicho de PRODUTIVIDADE, HÁBITOS, ALTA PERFORMANCE ou NEUROCIÊNCIA (incluindo foco, rotina, disciplina, sono e saúde mental aplicada ao trabalho). Caso contrário, responda 'NÃO'.

Título: "{title}"

Resposta (Apenas SIM ou NÃO):"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5,
        temperature=0.0,
    )
    result = response.choices[0].message.content.strip().upper()
    print(f"Título: {title} -> AI: {result}")


titles = [
    "COMO TER MAIS FOCO E DISCIPLINA",
    "TOUR PELO MEU ESCRITÓRIO",
    "A CIÊNCIA DO HÁBITO - NEUROESTRANHO",
    "COMO EU PERDI 30KG COM DIETA",
    "10 DECORAÇÕES DO FLOW",
    "DORMIR MELHOR PARA TRABALHAR MELHOR",
    "SERJÃO FOGUETES E OS MISTÉRIOS DO ESPAÇO",
]

for t in titles:
    test_niche_filter(t)
