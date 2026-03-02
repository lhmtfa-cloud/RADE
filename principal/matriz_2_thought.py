import re
from collections import Counter

def localizar_inicios(input_tokens: list, text_completo: str, memoria_aprendizado: dict) -> list:
    tokens_texto = re.findall(r"[\w']+|[.,!?;]", text_completo.lower())
    pontuacoes = [".", "!", "?"]
    
    frequencia = Counter(tokens_texto)
    pesos = {token: (10000 / (frequencia[token] + 1)) for token in input_tokens}
    
    candidatos = []
    
    # Transforma os tokens de entrada em uma tupla para buscar na memória
    chave_memoria = tuple(sorted(input_tokens))
    experiencia_passada = memoria_aprendizado.get(chave_memoria, {})
    
    for i, token in enumerate(tokens_texto):
        if token in input_tokens:
            janela_inicio = max(0, i - 15)
            janela_fim = min(len(tokens_texto), i + 15)
            contexto_proximo = tokens_texto[janela_inicio:janela_fim]
            
            tokens_encontrados = set([t for t in input_tokens if t in contexto_proximo])
            score_base = sum(pesos[t] for t in tokens_encontrados)
            
            if len(tokens_encontrados) > 1:
                score_base *= len(tokens_encontrados)
            
            inicio_frase = i
            while inicio_frase > 0 and tokens_texto[inicio_frase - 1] not in pontuacoes and (i - inicio_frase) < 15:
                inicio_frase -= 1
            
            if inicio_frase + 1 < len(tokens_texto):
                estado_inicial = (tokens_texto[inicio_frase], tokens_texto[inicio_frase + 1])
                
                # MÁGICA DO APRENDIZADO: Adiciona o peso do seu feedback (Positivo ou Negativo)
                # Multiplicamos por 10000 para que o aprendizado humano esmague a estatística cega
                score_experiencia = experiencia_passada.get(estado_inicial, 0) * 100000
                score_final = score_base + score_experiencia
                
                # Só adiciona se o score final for maior que zero (ignora caminhos que você negativou muito)
                if score_final > 0:
                    candidatos.append((estado_inicial, score_final))
                
    melhores_candidatos = {}
    for estado, score in candidatos:
        if estado not in melhores_candidatos or score > melhores_candidatos.get(estado, -99999):
            melhores_candidatos[estado] = score
            
    candidatos_ordenados = sorted(melhores_candidatos.items(), key=lambda x: x[1], reverse=True)
    return [estado for estado, score in candidatos_ordenados]