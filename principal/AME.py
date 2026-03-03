import fitz
import re
from tqdm import tqdm
import ctranslate2
from transformers import AutoTokenizer
import time

# ==========================================
# CONFIGURAÇÕES E INICIALIZAÇÃO
# ==========================================
# Substitua pelos caminhos reais do seu ambiente
TOKENIZER_PATH = r"model_ptt5"
MODEL_PATH = r"model_ptt5_ct2"

BATCH_SIZE = 4
MAX_TOKENS_MODELO = 512
num_threads = 4

# Inicialização (descomente para executar)
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, legacy=False)
translator = ctranslate2.Translator(MODEL_PATH, device="cpu", inter_threads=num_threads)

# ==========================================
# FUNÇÕES DE PRÉ-PROCESSAMENTO
# ==========================================
def limpar_ruido_pdf(texto):
    """Remove links, rodapés e cabeçalhos padronizados."""
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)
    texto = re.sub(r'piweb/validarDocumento.*|código: [a-f0-9]+', '', texto, flags=re.IGNORECASE)
    
    padroes_remover = [
        r'ESTADO DO PARANÁ.*?Folha \d+',
        r'Protocolo: \d{2}\.\d{3}\.\d{3}-\d+',
        r'Órgão Cadastro:.*?\d{2}/\d{2}/\d{4}.*?\d{2}:\d{2}',
        r'Para informações acesse:.*',
        r'Código TTD:.*',
        r'Palavras-chave:.*',
        r'Assunto:.*',
        r'Detalhamento:.*'
    ]
    
    for padrao in padroes_remover:
        texto = re.sub(padrao, '', texto, flags=re.IGNORECASE | re.DOTALL)
    
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def extrair_texto_pdf(caminho_pdf):
    """Lê o PDF e aplica a limpeza de ruído."""
    doc = fitz.open(caminho_pdf)
    texto = ""
    for pagina in doc:
        texto_pagina = pagina.get_text("text")
        texto += limpar_ruido_pdf(texto_pagina) + " "
    return texto

def dividir_em_blocos(texto, max_palavras=350):
    """Divide o texto em blocos menores para não estourar o limite de tokens."""
    palavras = texto.split()
    blocos = [" ".join(palavras[i:i + max_palavras]) for i in range(0, len(palavras), max_palavras)]
    return blocos if blocos else [""]

# ==========================================
# FUNÇÕES DO MODELO (LLM)
# ==========================================
def processar_lotes(textos, max_decoding_length, desc_barra, usar_beam=False):
    """Envia os blocos de texto para o modelo gerar o resumo."""
    resultados_finais = []
    
    for i in tqdm(range(0, len(textos), BATCH_SIZE), desc=desc_barra, unit="lote"):
        lote_textos = textos[i:i+BATCH_SIZE]
        lote_tokens = [tokenizer.convert_ids_to_tokens(tokenizer.encode(t, add_special_tokens=True)) for t in lote_textos]
        
        resultados = translator.translate_batch(
            lote_tokens, 
            max_decoding_length=max_decoding_length,
            min_decoding_length=15,
            beam_size=2 if usar_beam else 1,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            replace_unknowns=True
        )
        
        for r in resultados:
            texto_decodificado = tokenizer.decode(tokenizer.convert_tokens_to_ids(r.hypotheses[0]), skip_special_tokens=True)
            texto_limpo = texto_decodificado.replace("summarize:", "").replace("Resumo:", "").strip()
            resultados_finais.append(texto_limpo)
            
    return resultados_finais

# ==========================================
# FUNÇÕES DE EXTRAÇÃO E ESTRUTURAÇÃO
# ==========================================
def extrair_metadados_protocolo(texto):
    """Extrai quem enviou, para quem e o assunto base usando RegEx."""
    metadados = {
        "Para": "Não identificado",
        "De": "Não identificado",
        "Assunto_Base": "Não identificado"
    }
    
    match_para = re.search(r'(?i)Para:\s*(.*?)(?=\n|De:|Assunto|Documento)', texto)
    if match_para: metadados["Para"] = match_para.group(1).strip()
        
    match_de = re.search(r'(?i)De:\s*(.*?)(?=\n|Para|Assunto)', texto)
    if not match_de:
        match_de = re.search(r'(?i)Memo.*?/(.*?)(?=\s|\n)', texto)
    if match_de: metadados["De"] = match_de.group(1).strip()
        
    match_assunto = re.search(r'(?i)(?:Assunto|Documento):\s*(.*?)(?=\n)', texto)
    if match_assunto: metadados["Assunto_Base"] = match_assunto.group(1).strip()
        
    return metadados

def resumir_pdf_estruturado(caminho_pdf):
    """Função principal que integra extração de dados e resumo do motivo."""
    texto_completo = extrair_texto_pdf(caminho_pdf)
    if not texto_completo.strip(): return "Erro: PDF vazio."

    # 1. Extração via código (rápido e preciso)
    metadados = extrair_metadados_protocolo(texto_completo)

    # 2. Resumo via IA (apenas na introdução do documento)
    blocos = dividir_em_blocos(texto_completo)
    bloco_principal = blocos[0]
    
    prompt = f"Resuma o objetivo deste documento de forma direta: {bloco_principal}"
    
    resumo_motivo = processar_lotes(
        [prompt], 
        max_decoding_length=150, 
        desc_barra="Analisando Motivo", 
        usar_beam=True
    )[0]

    # 3. Formatação
    resultado_estruturado = (
        f"**DE:** {metadados['De']}\n"
        f"**PARA:** {metadados['Para']}\n"
        f"**REFERÊNCIA:** {metadados['Assunto_Base']}\n"
        f"**RESUMO:** {resumo_motivo}"
    )
    
    return resultado_estruturado

# Exemplo de uso:
# print(resumir_pdf_estruturado("seu_arquivo.pdf"))


if __name__ == "__main__":
    arquivo_teste = r"principal\documento_teste.pdf" 
    tempo_inicio = time.time()
    
    try:
        resultado_final = resumir_pdf_estruturado(arquivo_teste)
        print("\n" + "="*50)
        print("RESUMO FINAL:")
        print("="*50)
        print(resultado_final)
    except Exception as e:
        print(f"Ocorreu um erro: {e}")
    finally:
        print("\n" + "-"*50)
        print(f"Processo concluído em {time.time() - tempo_inicio:.2f} segundos.")
        print("-"*50)