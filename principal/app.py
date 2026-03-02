import streamlit as st
import json
import os
import random

# Importando os seus módulos modulares já criados
from extrator import extrair_texto
from matriz_1_input import extrair_conceitos
from matriz_2_thought import localizar_inicios
from matriz_3_knowledge import treinar_conhecimento, gerar_pensamento
from matriz_4_consensus import atingir_consenso
from matriz_5_output import traduzir_para_humano

ARQUIVO_MEMORIA = "memoria_aprendizado.json"

# =============================================================================
# FUNÇÕES DE MEMÓRIA
# =============================================================================
def carregar_memoria() -> dict:
    if not os.path.exists(ARQUIVO_MEMORIA):
        return {}
    with open(ARQUIVO_MEMORIA, 'r', encoding='utf-8') as f:
        m_json = json.load(f)
    m = {}
    for q_key, states in m_json.items():
        q_tokens = tuple(q_key.split("|"))
        m[q_tokens] = {}
        for s_key, score in states.items():
            s_tokens = tuple(s_key.split("|"))
            m[q_tokens][s_tokens] = score
    return m

def salvar_memoria(memoria: dict):
    m_json = {}
    for q_tokens, states in memoria.items():
        q_key = "|".join(q_tokens)
        m_json[q_key] = {}
        for state_tokens, score in states.items():
            s_key = "|".join(state_tokens)
            m_json[q_key][s_key] = score
    with open(ARQUIVO_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(m_json, f, ensure_ascii=False, indent=4)

# =============================================================================
# INICIALIZAÇÃO DO ESTADO DO FRONT-END
# =============================================================================
# O Streamlit roda o script de cima a baixo. O session_state guarda as variáveis para não sumirem.
if "treinado" not in st.session_state:
    st.session_state.treinado = False
    st.session_state.texto_puro = ""
    st.session_state.transicoes = {}
    st.session_state.memoria = carregar_memoria()
    st.session_state.chave_memoria = None
    st.session_state.winning_start = None
    st.session_state.resposta_atual = None

# =============================================================================
# INTERFACE GRÁFICA (UI)
# =============================================================================
st.set_page_config(page_title="Aegis-QA: Treinamento RLHF", layout="wide")
st.title("🛡️ Aegis-QA: Treinamento e Extração")

# --- BARRA LATERAL (Injeção de PDF) ---
with st.sidebar:
    st.header("1. Injeção de Conhecimento")
    caminho_pdf = st.text_input("Caminho do PDF:", value=r"C:\Users\rafael.goncalves\Documents\GitHub\RafaelAugustoDocumentoExtrator RADE\principal\documento_teste.pdf")
    
    if st.button("Extrair e Aprender"):
        with st.spinner("Lendo documento e mapeando a Matriz 3..."):
            texto = extrair_texto(caminho_pdf)
            st.session_state.texto_puro = texto
            st.session_state.transicoes = treinar_conhecimento(texto)
            st.session_state.treinado = True
        st.success(f"Concluído! {len(st.session_state.transicoes)} estados mapeados na RAM.")
    
    st.markdown("---")
    st.write(f"🧠 **Memórias salvas:** {len(st.session_state.memoria)} tópicos conhecidos.")

# --- ÁREA PRINCIPAL (Perguntas e Feedback) ---
if not st.session_state.treinado:
    st.info("👈 Clique em 'Extrair e Aprender' na barra lateral para carregar o cérebro da IA.")
else:
    st.header("2. Teste e Feedback Humano")
    
    # Formulário de Pergunta
    with st.form("form_pergunta"):
        pergunta = st.text_input("Faça sua pergunta ao documento:")
        perguntar_btn = st.form_submit_button("Gerar Resposta")

    # Processamento das Matrizes
    if perguntar_btn and pergunta:
        with st.spinner("Matrizes calculando caminhos (Monte Carlo)..."):
            tokens = extrair_conceitos(pergunta)
            st.session_state.chave_memoria = tuple(sorted(tokens))
            
            start_states = localizar_inicios(tokens, st.session_state.texto_puro, st.session_state.memoria)
            
            if not start_states:
                st.warning("Não encontrei pontos válidos baseados nesses conceitos.")
                st.session_state.resposta_atual = None
            else:
                top_states = start_states[:5]
                divergent_thoughts = []
                for state in top_states:
                    for _ in range(15):
                        thought = gerar_pensamento(state, st.session_state.transicoes)
                        divergent_thoughts.append(thought)
                        
                best_thought = atingir_consenso(divergent_thoughts)
                st.session_state.winning_start = tuple(best_thought[:2])
                st.session_state.resposta_atual = traduzir_para_humano(best_thought)

    # Exibição da Resposta e Painel de Avaliação
    if st.session_state.resposta_atual:
        st.markdown("### 🤖 Resposta da IA:")
        st.info(st.session_state.resposta_atual)
        st.caption(f"🎯 Ponto de partida estatístico escolhido: `{st.session_state.winning_start}`")
        
        st.markdown("#### Como você avalia essa associação?")
        col1, col2, col3 = st.columns(3)
        
        # Botões de Treinamento (Atualizam a Matriz de Experiência e recarregam a tela)
        with col1:
            if st.button("✅ Certo (Reforçar Rota)", use_container_width=True):
                chave = st.session_state.chave_memoria
                inicio = st.session_state.winning_start
                if chave not in st.session_state.memoria:
                    st.session_state.memoria[chave] = {}
                st.session_state.memoria[chave][inicio] = st.session_state.memoria[chave].get(inicio, 0) + 1
                salvar_memoria(st.session_state.memoria)
                st.session_state.resposta_atual = None
                st.rerun() # Limpa a tela para a próxima pergunta
        
        with col2:
            if st.button("❌ Errado (Penalizar Rota)", use_container_width=True):
                chave = st.session_state.chave_memoria
                inicio = st.session_state.winning_start
                if chave not in st.session_state.memoria:
                    st.session_state.memoria[chave] = {}
                st.session_state.memoria[chave][inicio] = st.session_state.memoria[chave].get(inicio, 0) - 5
                salvar_memoria(st.session_state.memoria)
                st.session_state.resposta_atual = None
                st.rerun()
                
        with col3:
            if st.button("⏭️ Pular (Tentar de Novo)", use_container_width=True):
                st.session_state.resposta_atual = None
                st.rerun()