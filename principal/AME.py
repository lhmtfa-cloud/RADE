import fitz
import concurrent.futures
import pytesseract
import pdfplumber
from PIL import Image, ImageEnhance, ImageOps
from llama_cpp import Llama
from .limpeza import extrair_metadados_protocolo, extrair_texto_bruto_pdf, limpar_texto_para_ia, extrair_timeline_protocolo, gerar_arquivo_eventos

MODEL_PATH = r"./app/models/phi_pt_f16.gguf"                 

num_threads = 4

llm = Llama(
model_path=MODEL_PATH,
    n_gpu_layers=-1,
    n_ctx=4096,
    n_threads=8,          
    n_batch=512,         
    use_mlock=True,       
    verbose=True
)

def localizar_paginas_referencia(caminho_pdf, resumo_ia):
    doc = fitz.open(caminho_pdf)
    palavras_chave = [w for w in resumo_ia.lower().split() if len(w) > 5] 
    
    paginas_encontradas = []
    
    for i, pagina in enumerate(doc):
        texto_pag = pagina.get_text("text").lower()
        matches = sum(1 for p in palavras_chave if p in texto_pag)
        if matches > len(palavras_chave) * 0.3:
            paginas_encontradas.append(str(i + 1))
            
    doc.close()
    return ", ".join(paginas_encontradas) if paginas_encontradas else "Não identificada"

def extrair_ocr_melhorado(caminho_pdf):
    texto_ocr = ""
    config_tesseract = "--psm 6" 
    
    try:
        doc = fitz.open(caminho_pdf)
        limite = min(15, len(doc))
        
        for i in range(limite):
            pagina = doc[i]
            
            if len(pagina.get_text("text").strip()) > 100:
                continue 
                
            pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            img_gray = ImageOps.grayscale(img)
            img_contrast = ImageEnhance.Contrast(img_gray).enhance(2.0)
            
            texto_ocr += pytesseract.image_to_string(img_contrast, lang="por", config=config_tesseract) + "\n"
            
        doc.close()
    except Exception as e:
        print(f"Aviso no OCR: {e}")
        return ""
    
    return texto_ocr.strip()

def extrair_tabelas_pdf(caminho_pdf):
    texto_tabelas = ""
    try:
        doc_teste = fitz.open(caminho_pdf)
        paginas_com_tabela = []
        palavras_chave = ["r$", "valor", "quantidade", "total", "unitário", "descrição", "preço"]
        
        for i in range(min(15, len(doc_teste))):
            texto_pag = doc_teste[i].get_text("text").lower()
            if any(p in texto_pag for p in palavras_chave):
                paginas_com_tabela.append(i)
        doc_teste.close()

        if not paginas_com_tabela:
            return ""

        with pdfplumber.open(caminho_pdf) as pdf:
            for idx in paginas_com_tabela:
                tabelas = pdf.pages[idx].extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
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
    
    output = llm(
        prompt,
        max_tokens=150,
        temperature=0.2,
        repeat_penalty=1.1,
        echo=False
    )
    return output['choices'][0]['text'].strip()

def gerar_resumo_phi(texto_limpo):
    prompt = (
        f"<|user|>\n"
        f"Você é um assistente administrativo da SETI/PR. Abaixo está o conteúdo de um documento oficial. "
        f"Resuma o objetivo principal deste documento de forma direta e profissional em uma única frase. "
        f"Ignore cabeçalhos, números de protocolo e assinaturas.\n\n"
        f"CONTEÚDO DO DOCUMENTO:\n{texto_limpo[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    
    output = llm(
        prompt,
        max_tokens=120,
        temperature=0.2,
        repeat_penalty=1.1,
        echo=False
    )
    return output['choices'][0]['text'].strip()

def processar_documento_final(caminho_pdf):
    doc_leitura = fitz.open(caminho_pdf)
    texto_bruto = extrair_texto_bruto_pdf(caminho_pdf)
    if not texto_bruto.strip(): return "Erro: PDF sem texto.", "", ""

    meta = extrair_metadados_protocolo(texto_bruto)
    corpo_limpo = limpar_texto_para_ia(texto_bruto)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_resumo = executor.submit(gerar_resumo_phi, corpo_limpo)
        future_ocr = executor.submit(extrair_ocr_melhorado, caminho_pdf)
        future_tabelas = executor.submit(extrair_tabelas_pdf, caminho_pdf)
        future_timeline = executor.submit(extrair_timeline_protocolo, caminho_pdf)
        
        resumo_ia = future_resumo.result()
        texto_ocr = future_ocr.result()
        texto_tabelas = future_tabelas.result()
        timeline_data = future_timeline.result()

    eventos_resumidos = []
    timeline_para_txt = []
    
    if timeline_data:
        for item in timeline_data:
            texto_pag = doc_leitura[item['pagina'] - 1].get_text("text")
            prompt = (
                f"<|user|>\n"
                f"Com base no conteúdo da página abaixo, resuma em uma única frase curta e direta o que aconteceu ou o que foi solicitado.\n"
                f"Contexto: {item['evento_str']}\n\n"
                f"CONTEÚDO DA PÁGINA:\n{texto_pag[:2000]}\n<|end|>\n"
                f"<|assistant|>\n"
            )
            
            res = llm(
                prompt,
                max_tokens=100,
                temperature=0.2,
                echo=False
            )
            
            resumo_evento = res['choices'][0]['text'].strip()
            num_pag = item['pagina']
            evento_str = item['evento_str']
            
            linha_pdf = f"Página {num_pag:03d}: {resumo_evento}"
            eventos_resumidos.append(linha_pdf)
            timeline_para_txt.append(f"Página {num_pag:04d} | {evento_str}")

    caminho_events_txt = gerar_arquivo_eventos(timeline_para_txt)

    dados_extras = f"--- DADOS DE TABELAS ---\n{texto_tabelas}\n\n--- DADOS DE IMAGENS ---\n{texto_ocr}"
    resumo_final = resumo_ia

    if len(texto_ocr) > 20 or len(texto_tabelas) > 10: 
        analise_complementar = avaliar_e_justificar_ocr(resumo_ia, dados_extras)
        if "IRRELEVANTE" not in analise_complementar.upper():
            resumo_final = f"{resumo_ia} {analise_complementar}"

    paginas_ref = localizar_paginas_referencia(caminho_pdf, resumo_ia)
    resumo_eventos_str = "\n".join(eventos_resumidos) if eventos_resumidos else "Nenhuma movimentação detalhada encontrada."

    doc_leitura.close()

    return (
        f"**DE:** {meta['De']}\n"
        f"**DOCUMENTO:** {meta.get('Documento', 'Não identificado')}\n"
        f"**PARA:** {meta['Para']}\n"
        f"**PÁGINAS DE ORIGEM:** {paginas_ref}\n"
        f"**RESUMO:** {resumo_final}\n"
        f"**EVENTOS:**\n{resumo_eventos_str}"
    ), dados_extras, caminho_events_txt