from collections import Counter

def atingir_consenso(thoughts: list) -> list:
    # Filtra pensamentos inúteis (menores que 4 palavras)
    valid_thoughts = [t for t in thoughts if len(t) > 3]
    if not valid_thoughts:
        valid_thoughts = thoughts 
        
    thought_counts = Counter(tuple(t) for t in valid_thoughts)
    
    melhor_pensamento = None
    maior_score = -1
    repeticoes_vencedor = 0
    
    for thought_tuple, count in thought_counts.items():
        # Conta quantas palavras reais a frase tem (ignorando pontuação)
        tamanho = len([w for w in thought_tuple if w.isalpha()])
        
        # MÁGICA 2: O novo placar prioriza frases longas e consistentes
        score = count * tamanho
        
        if score > maior_score:
            maior_score = score
            melhor_pensamento = thought_tuple
            repeticoes_vencedor = count
            
    print(f"[Matriz 4 - Consenso] A resposta vencedora repetiu {repeticoes_vencedor} vezes (Placar ajustado por tamanho: {maior_score}).")
    return list(melhor_pensamento) if melhor_pensamento else thoughts[0]