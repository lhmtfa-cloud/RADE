import re

STOPWORDS = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "em", "no", "na", "que", "qual", "quais", "é", "são", "para"}

def extrair_conceitos(pergunta: str) -> list:
    clean_q = re.sub(r'[^\w\s]', '', pergunta.lower())
    tokens = [w for w in clean_q.split() if w not in STOPWORDS]
    return tokens