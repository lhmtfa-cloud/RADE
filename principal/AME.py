import ctranslate2
from transformers import AutoTokenizer
import fitz
import concurrent.futures
import pytesseract
import pdfplumber
from PIL import ImageEnhance, ImageOps
from pdf2image import convert_from_path
from .limpeza import extrair_metadados_protocolo, extrair_texto_bruto_pdf, limpar_texto_para_ia 

TOKENIZER_PATH = r"./app/models/phi_completo_merged" 
MODEL_PATH = r"./app/models/phi_ct2"                 

num_threads = 4

tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, local_files_only=True, trust_remote_code=True)
generator = ctranslate2.Generator(MODEL_PATH, device="cpu", compute_type="int8_float32", inter_threads=num_threads)


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

def extrair_ocr_melhorado(caminho_pdf):
    texto_ocr = ""
    try:
        # Limite aumentado para 15 páginas para capturar anexos de pesquisa de preços
        imagens = convert_from_path(caminho_pdf, last_page=15)
        config_tesseract = "--psm 6" # Assume um bloco único de texto, ideal para faturas e layouts esparsos
        
        for img in imagens:
            # Pré-processamento com PIL para aumentar contraste de números e textos estilizados
            img_gray = ImageOps.grayscale(img)
            enhancer = ImageEnhance.Contrast(img_gray)
            img_contrast = enhancer.enhance(2.0)
            
            texto_ocr += pytesseract.image_to_string(img_contrast, lang="por", config=config_tesseract) + "\n"
    except Exception as e:
        print(f"Aviso no OCR: {e}")
        return ""
    
    return texto_ocr.strip()

def extrair_tabelas_pdf(caminho_pdf):
    texto_tabelas = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            paginas = pdf.pages[:15]
            for pagina in paginas:
                tabelas = pagina.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        # Remove células vazias e unifica a linha da tabela
                        linha_limpa = [str(celula).strip() for celula in linha if celula is not None and str(celula).strip()]
                        if linha_limpa:
                            texto_tabelas += " | ".join(linha_limpa) + "\n"
                    texto_tabelas += "\n"
    except Exception as e:
        print(f"Aviso na extração de tabelas: {e}")
        return ""
        
    return texto_tabelas.strip()

def avaliar_e_justificar_ocr(resumo_original, dados_extras):
    prompt = (
        f"<|user|>\n"
        f"Você possui o RESUMO PRINCIPAL de um documento e DADOS EXTRAS extraídos de tabelas e imagens anexas.\n"
        f"Se os DADOS EXTRAS não adicionarem informações úteis de valores, empresas ou quantitativos ao resumo, responda APENAS com a palavra 'IRRELEVANTE'.\n"
        f"Se os DADOS EXTRAS contiverem valores financeiros, quantidades importantes ou dados técnicos pertinentes, crie UMA ÚNICA FRASE como justificativa ou complemento ao resumo principal.\n\n"
        f"RESUMO PRINCIPAL: {resumo_original}\n\n"
        f"DADOS EXTRAS:\n{dados_extras[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    
    tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(prompt))
    
    results = generator.generate_batch(
        [tokens],
        max_length=150,
        sampling_temperature=0.2,
        repetition_penalty=1.1,
        include_prompt_in_result=False 
    )
    
    output = tokenizer.decode(results[0].sequences_ids[0], skip_special_tokens=True)
    return output.strip()

def processar_documento_final(caminho_pdf):
    texto_bruto = extrair_texto_bruto_pdf(caminho_pdf)
    if not texto_bruto.strip(): return "Erro: PDF sem texto.", ""

    meta = extrair_metadados_protocolo(texto_bruto)
    corpo_limpo = limpar_texto_para_ia(texto_bruto)
    
    # 1. Extração paralela para otimizar tempo (Resumo IA, OCR e Tabelas)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_resumo = executor.submit(gerar_resumo_phi, corpo_limpo)
        future_ocr = executor.submit(extrair_ocr_melhorado, caminho_pdf)
        future_tabelas = executor.submit(extrair_tabelas_pdf, caminho_pdf)
        
        resumo_ia = future_resumo.result()
        texto_ocr = future_ocr.result()
        texto_tabelas = future_tabelas.result()

    # Consolidação dos dados visuais/estruturais
    dados_extras = f"--- DADOS DE TABELAS ---\n{texto_tabelas}\n\n--- DADOS DE IMAGENS ---\n{texto_ocr}"
    resumo_final = resumo_ia

    # 2. Avaliação da IA sobre os dados extras (feita apenas após o resumo principal estar pronto)
    if len(texto_ocr) > 20 or len(texto_tabelas) > 10: 
        analise_complementar = avaliar_e_justificar_ocr(resumo_ia, dados_extras)
        
        # 3. Adiciona a justificativa/complemento ao resumo final se for relevante
        if "IRRELEVANTE" not in analise_complementar.upper():
            resumo_final = f"{resumo_ia} {analise_complementar}"

    paginas_ref = localizar_paginas_referencia(caminho_pdf, resumo_ia)

    return (
        f"**DE:** {meta['De']}\n"
        f"**PARA:** {meta['Para']}\n"
        f"**PÁGINAS DE ORIGEM:** {paginas_ref}\n"
        f"**RESUMO:** {resumo_final}"
    ), dados_extras