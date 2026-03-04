
import ctranslate2
from transformers import AutoTokenizer
import time
from tqdm import tqdm
import fitz
from limpeza import extrair_metadados_protocolo, extrair_texto_bruto_pdf, limpar_texto_para_ia 

TOKENIZER_PATH = r"phi_completo_merged" 
MODEL_PATH = r"phi_ct2"                 

num_threads = 4

tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, trust_remote_code=True)

generator = ctranslate2.Generator(MODEL_PATH, device="cpu", compute_type="int8_float32", inter_threads=num_threads)

from difflib import SequenceMatcher

def localizar_paginas_referencia(caminho_pdf, resumo_ia):
    doc = fitz.open(caminho_pdf)
    palavras_chave = [w for w in resumo_ia.lower().split() if len(w) > 5] 
    
    paginas_encontradas = []
    
    for i, pagina in enumerate(doc):
        texto_pag = pagina.get_text("text").lower()
        matches = sum(1 for p in palavras_chave if p in texto_pag)
        if matches > len(palavras_chave) * 0.3:
            paginas_encontradas.append(str(i + 1))
            
    return ", ".join(paginas_encontradas) if paginas_encontradas else "Não identificada"



def gerar_resumo_phi(texto_limpo):
    prompt = (
        f"<|user|>\n"
        f"Você é um assistente administrativo da SETI/PR. Abaixo está o conteúdo de um documento oficial. "
        f"Resuma o objetivo principal deste documento de forma direta e profissional em uma única frase. "
        f"Ignore cabeçalhos, números de protocolo e assinaturas.\n\n"
        f"CONTEÚDO DO DOCUMENTO:\n{texto_limpo[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    
    tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(prompt))
    

    results = generator.generate_batch(
        [tokens],
        max_length=120,
        sampling_temperature=0.2, 
        repetition_penalty=1.1,
        include_prompt_in_result=False 
    )
    
    output = tokenizer.decode(results[0].sequences_ids[0], skip_special_tokens=True)
    return output.strip()


def processar_documento_final(caminho_pdf):
    texto_bruto = extrair_texto_bruto_pdf(caminho_pdf)
    if not texto_bruto.strip(): return "Erro: PDF sem texto."

    meta = extrair_metadados_protocolo(texto_bruto)
    corpo_limpo = limpar_texto_para_ia(texto_bruto)
    resumo_ia = gerar_resumo_phi(corpo_limpo)
    
    paginas_ref = localizar_paginas_referencia(caminho_pdf, resumo_ia)

    return (
        f"**DE:** {meta['De']}\n"
        f"**PARA:** {meta['Para']}\n"
        f"**PÁGINAS DE ORIGEM:** {paginas_ref}\n"
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