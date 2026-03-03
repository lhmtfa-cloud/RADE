import fitz
import re
import ctranslate2
from transformers import AutoTokenizer
import time
from tqdm import tqdm

# ==========================================
# CONFIGURAÇÕES E INICIALIZAÇÃO
# ==========================================
# Use a pasta onde estão os arquivos .json do tokenizer
TOKENIZER_PATH = r"phi_completo_merged" 
# Use a pasta gerada pelo conversor
MODEL_PATH = r"phi_ct2"                 

num_threads = 4

# Inicialização do Gerador (Phi-3 é Generator, não Translator)
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, trust_remote_code=True)
generator = ctranslate2.Generator(MODEL_PATH, device="cpu", inter_threads=num_threads)

# ==========================================
# FUNÇÕES DE LIMPEZA E EXTRAÇÃO
# ==========================================
def extrair_texto_bruto_pdf(caminho_pdf):
    doc = fitz.open(caminho_pdf)
    texto = ""
    for pagina in doc:
        texto += pagina.get_text("text") + " \n"
    return texto

def limpar_texto_para_ia(texto):
    """Remove ruídos para que o Phi-3 foque apenas no conteúdo."""
    # Remove assinaturas, protocolos e links de validação (linhas inteiras)
    texto = re.sub(r'(?i)(?:Assinatura|Protocolo|Inserido|Autenticidade|Local|Folha|Código TTD|piweb).*', '', texto)
    # Remove endereços e cabeçalhos fixos da SETI
    texto = re.sub(r'(?i)Av\..*?Curitiba/PR.*?CEP\s*\d{5}-\d{3}', '', texto)
    # Normaliza espaços
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def extrair_metadados_protocolo(texto_bruto):
    """Extrai cabeçalhos estruturados via Regex no texto original."""
    metadados = {"Para": "N/A", "De": "N/A", "Assunto": "N/A"}
    
    m_para = re.search(r'(?i)Para:\s*(.*?)(?=\n|De:|Assunto|Documento)', texto_bruto)
    if m_para: metadados["Para"] = m_para.group(1).strip()
        
    m_de = re.search(r'(?i)De:\s*(.*?)(?=\n|Para|Assunto)', texto_bruto)
    if not m_de:
        m_de = re.search(r'(?i)Memo.*?/(.*?)(?=\s|\n)', texto_bruto)
    if m_de: metadados["De"] = m_de.group(1).strip()
        
    m_assunto = re.search(r'(?i)(?:Assunto|Referência|Documento):\s*(.*?)(?=\n)', texto_bruto)
    if m_assunto: metadados["Assunto"] = m_assunto.group(1).strip()
        
    return metadados

# ==========================================
# LOGICA DE GERAÇÃO (PHI-3)
# ==========================================
def gerar_resumo_phi(texto_limpo):
    """Utiliza Prompt Instruct para gerar um resumo coeso."""
    
    # Formatando o prompt com as tags específicas do Phi-3
    prompt = (
        f"<|user|>\n"
        f"Você é um assistente administrativo da SETI/PR. Abaixo está o conteúdo de um documento oficial. "
        f"Resuma o objetivo principal deste documento de forma direta e profissional em uma única frase. "
        f"Ignore cabeçalhos, números de protocolo e assinaturas.\n\n"
        f"CONTEÚDO DO DOCUMENTO:\n{texto_limpo[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    
    # Tokenização
    tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(prompt))
    
    # Geração
    results = generator.generate_batch(
        [tokens],
        max_length=120,
        sampling_temperature=0.2, # Baixa temperatura = mais fatos, menos "criatividade"
        repetition_penalty=1.1,
        include_prompt_in_result=False # Não repete o prompt no output
    )
    
    # Decodificação do resultado
    output = tokenizer.decode(results[0].sequences_ids[0], skip_special_tokens=True)
    return output.strip()

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
def processar_documento_final(caminho_pdf):
    texto_bruto = extrair_texto_bruto_pdf(caminho_pdf)
    if not texto_bruto.strip(): return "Erro: PDF sem texto."

    # 1. Metadados (via Regex - mais preciso para nomes próprios)
    meta = extrair_metadados_protocolo(texto_bruto)

    # 2. Resumo (via Phi-3 - mais inteligente para o contexto)
    corpo_limpo = limpar_texto_para_ia(texto_bruto)
    resumo_ia = gerar_resumo_phi(corpo_limpo)

    # 3. Formatação Final
    return (
        f"**DE:** {meta['De']}\n"
        f"**PARA:** {meta['Para']}\n"
        f"**REFERÊNCIA:** {meta['Assunto']}\n"
        f"**RESUMO:** {resumo_ia}"
    )

if __name__ == "__main__":
    arquivo = r"principal\documento_teste.pdf"
    start = time.time()
    
    try:
        resultado = processar_documento_final(arquivo)
        print("\n" + "="*60)
        print(resultado)
        print("="*60)
    except Exception as e:
        print(f"Erro no processamento: {e}")
    finally:
        print(f"\nTempo decorrido: {time.time() - start:.2f}s")