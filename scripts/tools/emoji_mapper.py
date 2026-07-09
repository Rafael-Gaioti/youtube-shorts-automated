import re
import unicodedata
from typing import Optional

# Mapeamento estendido de termos em português e inglês para Emojis
EMOJI_MAP = {
    # Sucesso e Performance
    "sucesso": "🏆",
    "success": "🏆",
    "vitoria": "🥇",
    "vencer": "🥇",
    "win": "🥇",
    "rico": "💰",
    "rich": "💰",
    "dinheiro": "💸",
    "money": "💸",
    "dolar": "💵",
    "ouro": "🪙",
    "meta": "🎯",
    "foco": "🎯",
    "focus": "🎯",
    "trabalho": "💼",
    "work": "💼",
    "habito": "🌱",
    "habit": "🌱",
    "crescimento": "📈",
    "growth": "📈",
    
    # Mental e Conhecimento
    "mente": "🧠",
    "mind": "🧠",
    "cerebro": "🧠",
    "pensar": "💭",
    "think": "💭",
    "ideia": "💡",
    "idea": "💡",
    "aprender": "📚",
    "learn": "📚",
    "livro": "📖",
    "book": "📖",
    "conselho": "🗣️",
    
    # Tempo e Foco
    "tempo": "⏱️",
    "time": "⏱️",
    "relogio": "⏰",
    "dia": "☀️",
    "day": "☀️",
    "noite": "🌙",
    "night": "🌙",
    "futuro": "🔮",
    "future": "🔮",
    "vida": "✨",
    "life": "✨",
    
    # Emoções e Desafios
    "morte": "💀",
    "death": "💀",
    "morrer": "💀",
    "medo": "😨",
    "fear": "😨",
    "erro": "❌",
    "error": "❌",
    "falha": "⚠️",
    "fail": "⚠️",
    "rejeição": "💔",
    "rejeitado": "💔",
    "rejection": "💔",
    "coracao": "❤️",
    "heart": "❤️",
    "dor": "💥",
    "pain": "💥",
    
    # Outros comuns em podcasts
    "telefone": "📱",
    "celular": "📱",
    "computador": "💻",
    "computer": "💻",
    "elefante": "🐘",
    "elephant": "🐘",
    "escola": "🏫",
    "school": "🏫",
    "faculdade": "🎓",
    "college": "🎓",
    "empresa": "🏢",
    "company": "🏢",
    "pessoas": "👥",
    "people": "👥",
    "mundo": "🌍",
    "world": "🌍",
}

def clean_word(word: str) -> str:
    """Remove pontuação e acentuação da palavra para correspondência robusta."""
    # Remover pontuação das pontas
    word = re.sub(r"^[^\w]+|[^\w]+$", "", word).lower()
    # Remover acentuação (ex: 'rejeição' -> 'rejeicao')
    nfkd_form = unicodedata.normalize('NFKD', word)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def get_emoji_for_word(word: str) -> Optional[str]:
    """Retorna um emoji correspondente se a palavra for uma palavra-chave."""
    cleaned = clean_word(word)
    if not cleaned:
        return None
        
    # Busca por correspondência exata
    if cleaned in EMOJI_MAP:
        return EMOJI_MAP[cleaned]
        
    # Busca por correspondência de prefixo/sufixo (ex: 'rejeitados' -> 'rejeitado' -> 💔)
    for key, emoji in EMOJI_MAP.items():
        if len(cleaned) > 4 and (cleaned.startswith(key) or key.startswith(cleaned)):
            return emoji
            
    return None

def enrich_word_with_emoji(word: str) -> str:
    """Se a palavra possuir mapeamento, retorna ela com o emoji anexado (ex: 'MORTE 💀')."""
    emoji = get_emoji_for_word(word)
    if emoji:
        # Preserva pontuação original ao anexar emoji
        # ex: "morte," vira "MORTE 💀,"
        match = re.search(r"(\w+)([^\w]*)$", word)
        if match:
            base, punctuation = match.groups()
            return f"{base.upper()} {emoji}{punctuation}"
        return f"{word.upper()} {emoji}"
    return word.upper()
