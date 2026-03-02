import os
import json
import random
from extrator import extrair_texto
from matriz_1_input import extrair_conceitos
from matriz_2_thought import localizar_inicios
from matriz_3_knowledge import treinar_conhecimento, gerar_pensamento
from matriz_4_consensus import atingir_consenso
from matriz_5_output import traduzir_para_humano

# =============================================================================
# GERENCIADOR DA MATRIZ DE MEMÓRIA (JSON)
# =============================================================================

ARQUIVO_MEMORIA = "memoria_aprendizado.json"

def carregar_memoria() -> dict:
    """Carrega o JSON e converte as chaves de string de volta para tuplas."""
    if not os.path.exists(ARQUIVO_MEMORIA):
        return {}
        
    with open(ARQUIVO_MEMORIA, 'r', encoding='utf-8') as f:
        memoria_json = json.load(f)
        
    memoria = {}
    for q_key, states in memoria_json.items():
        q_tokens = tuple(q_key.split("|"))
        memoria[q_tokens] = {}
        for s_key, score in states.items():
            s_tokens = tuple(s_key.split("|"))
            memoria[q_tokens][s_tokens] = score
            
    return memoria

def salvar_memoria(memoria: dict):
    """Converte as tuplas em strings separadas por '|' e salva no JSON."""
    memoria_json = {}
    for q_tokens, states in memoria.items():
        q_key = "|".join(q_tokens)
        memoria_json[q_key] = {}
        for state_tokens, score in states.items():
            s_key = "|".join(state_tokens)
            memoria_json[q_key][s_key] = score
            
    with open(ARQUIVO_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(memoria_json, f, ensure_ascii=False, indent=4)

# =============================================================================
# LOOP DE TREINAMENTO FOCADO
# =============================================================================

def loop_de_treino(pergunta: str, texto_puro: str, transitions: dict, memoria: dict, amostras_por_ponto: int = 15):
    tokens = extrair_conceitos(pergunta)
    chave_memoria = tuple(sorted(tokens))
    print(f"\n[Matriz 1] Palavras associadas à pergunta: {tokens}")
    
    # 1. LOOP DA MESMA PERGUNTA
    while True:
        start_states = localizar_inicios(tokens, texto_puro, memoria)
        if not start_states:
            print("Não há pontos válidos para explorar nesta pergunta.")
            break
            
        top_states = start_states[:5]
        
        divergent_thoughts = []
        for state in top_states:
            for _ in range(amostras_por_ponto):
                thought = gerar_pensamento(state, transitions)
                divergent_thoughts.append(thought)
                
        best_thought = atingir_consenso(divergent_thoughts)
        
        # 2. MOSTRA AS PALAVRAS DE ASSOCIAÇÃO DO CONHECIMENTO
        winning_start_state = tuple(best_thought[:2])
        final_answer = traduzir_para_humano(best_thought)
        
        print("\n" + "="*60)
        print(f"🎯 PONTO DE PARTIDA ESCOLHIDO PELA IA: {winning_start_state}")
        print(f"🤖 RESPOSTA GERADA:\n{final_answer}")
        print("="*60)
        
        # 3. SISTEMA DE NOTAS E NAVEGAÇÃO
        print("\nComo você avalia essa associação?")
        print("[ s ] Positivo (A IA foi no lugar certo)")
        print("[ n ] Negativo (A IA pegou o contexto errado)")
        print("[ p ] Pular  (Deixar a IA tentar de novo sem dar nota)")
        print("[ q ] Sair   (Mudar de pergunta)")
        
        feedback = input("Sua escolha: ").strip().lower()
        
        if chave_memoria not in memoria:
            memoria[chave_memoria] = {}
            
        if feedback == 's':
            memoria[chave_memoria][winning_start_state] = memoria[chave_memoria].get(winning_start_state, 0) + 1
            print(f"✅ Aprendizado salvo! O peso da associação {winning_start_state} AUMENTOU.")
            salvar_memoria(memoria)
            
        elif feedback == 'n':
            # Penaliza pesadamente para forçar a IA a fugir dessa resposta imediatamente
            memoria[chave_memoria][winning_start_state] = memoria[chave_memoria].get(winning_start_state, 0) - 5
            print(f"❌ Aprendizado salvo! A IA vai EVITAR a associação {winning_start_state}.")
            salvar_memoria(memoria)
            
        elif feedback == 'q':
            print("Saindo do loop desta pergunta...")
            break
            
        else:
            print("⏭️ Avaliação pulada. Tentando nova iteração...")

# =============================================================================
# INICIALIZAÇÃO
# =============================================================================
if __name__ == "__main__":
    pdf_file = r"C:\Users\rafael.goncalves\Documents\GitHub\RafaelAugustoDocumentoExtrator RADE\principal\documento_teste.pdf"
    
    texto_puro = extrair_texto(pdf_file)
    print("Treinando Matriz de Conhecimento Base...")
    transicoes_conhecimento = treinar_conhecimento(texto_puro)
    print(f"Treinamento concluído. {len(transicoes_conhecimento)} estados mapeados na RAM.")
    
    # Carrega a "Matriz 3" (Memória Humana) do disco
    memoria_aprendizado = carregar_memoria()
    print(f"Memória de Aprendizado (JSON) carregada com {len(memoria_aprendizado)} tópicos conhecidos.")
    
    print("\n--- INICIANDO MODO DE TREINAMENTO RLHF ---")
    while True:
        pergunta_usuario = input("\nDigite a pergunta para treinar a IA (ou 'sair' para encerrar): ")
        if pergunta_usuario.lower() == 'sair':
            break
            
        loop_de_treino(pergunta_usuario, texto_puro, transicoes_conhecimento, memoria_aprendizado)