import fitz
import concurrent.futures
import pytesseract
import pdfplumber
import requests
import queue
import threading
from PIL import Image, ImageEnhance, ImageOps
from .limpeza import extrair_metadados_protocolo, extrair_texto_bruto_pdf, limpar_texto_para_ia, extrair_timeline_protocolo, gerar_arquivo_eventos

# Configurações das APIs Locais
URL_GPU = "http://llama-gpu:8001/v1/completions"
URL_CPU = "http://llama-cpu:8002/v1/completions"

num_threads = 4

def chamar_llm_api(prompt, max_tokens=200, temperature=0.2, usar_cpu=False):
    url = URL_CPU if usar_cpu else URL_GPU
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stop": ["<|end|>"]
    }
    try:
        # Adicionado proxies={"http": None, "https": None} para ignorar o proxy da SETI
        response = requests.post(
            url, 
            json=payload, 
            timeout=300, 
            proxies={"http": None, "https": None}
        ) 
        response.raise_for_status()
        return response.json()['choices'][0]['text'].strip()
    except Exception as e:
        print(f"Erro na API LLM (CPU={usar_cpu}): {e}")
        return "Erro ao processar com IA."

def localizar_paginas_referencia(caminho_pdf, resumo_ia):
    # ... (Mantenha o código original desta função) ...
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

def processar_pagina_ocr(caminho_pdf, numero_pagina, config_tesseract):
    try:
        # Abre uma instância independente do documento para evitar concorrência (PyMuPDF não é thread-safe)
        doc = fitz.open(caminho_pdf)
        pagina = doc[numero_pagina]
        
        if len(pagina.get_text("text").strip()) > 100:
            doc.close()
            return (numero_pagina, "") # Retorna tupla com índice para ordenar depois
            
        pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        img_gray = ImageOps.grayscale(img)
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(2.0)
        
        texto = pytesseract.image_to_string(img_contrast, lang="por", config=config_tesseract)
        doc.close()
        
        return (numero_pagina, texto + "\n")
    except Exception as e:
        print(f"Aviso no OCR pag {numero_pagina}: {e}")
        return (numero_pagina, "")

def extrair_ocr_melhorado(caminho_pdf):
    texto_ocr = ""
    config_tesseract = "--psm 6" 
    
    try:
        doc_teste = fitz.open(caminho_pdf)
        limite = min(15, len(doc_teste))
        doc_teste.close()
        
        resultados = []
        # Dispara todas as extrações de OCR simultaneamente
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futuros = [executor.submit(processar_pagina_ocr, caminho_pdf, i, config_tesseract) for i in range(limite)]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
                
        # Garante que o texto final fique na ordem correta das páginas
        resultados.sort(key=lambda x: x[0])
        for _, texto in resultados:
            texto_ocr += texto
            
    except Exception as e:
        print(f"Aviso no OCR: {e}")
        return ""
    
    return texto_ocr.strip()


def processar_pagina_tabela(caminho_pdf, idx):
    texto_local = ""
    try:
        # Abre o pdfplumber isolado para esta thread
        with pdfplumber.open(caminho_pdf) as pdf:
            tabelas = pdf.pages[idx].extract_tables()
            for tabela in tabelas:
                for linha in tabela:
                    linha_limpa = [str(celula).strip() for celula in linha if celula is not None and str(celula).strip()]
                    if linha_limpa:
                        texto_local += " | ".join(linha_limpa) + "\n"
                texto_local += "\n"
    except Exception:
        pass
    return (idx, texto_local)

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

        resultados = []
        # Dispara a extração pesada do pdfplumber em paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futuros = [executor.submit(processar_pagina_tabela, caminho_pdf, idx) for idx in paginas_com_tabela]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
        
        resultados.sort(key=lambda x: x[0])
        for _, texto in resultados:
            texto_tabelas += texto
            
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
    return chamar_llm_api(prompt, max_tokens=150, temperature=0.2, usar_cpu=False) # Mantém na GPU

def gerar_resumo_phi(texto_limpo):
    prompt = (
        f"<|user|>\n"
        f"Você é um assistente administrativo da SETI/PR. Sua tarefa é ler o documento abaixo e responder EXCLUSIVAMENTE em Português do Brasil.\n"
        f"Regra: Escreva uma única frase direta. Não invente campos extras.\n\n"
        f"TEXTO PARA ANALISAR:\n"
        f"### INÍCIO ###\n{texto_limpo[:1500]}\n### FIM ###\n<|end|>\n"
        f"<|assistant|>\n"
        f"Resumo em português: " # Força o início da resposta no idioma correto
    )
    return chamar_llm_api(prompt, max_tokens=120, temperature=0.1, usar_cpu=False)


    
def processar_documento_final(caminho_pdf):
    doc_leitura = fitz.open(caminho_pdf)
    total_paginas = len(doc_leitura)
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

    eventos_resumidos_raw = []
    timeline_para_txt_raw = []
    inconsistencias_resultado = "Não foi possível analisar inconsistências (sem eventos)."
    
    if timeline_data:
        num_eventos = len(timeline_data)
        blocos = []
        
        # 1. Monta os blocos de texto entre um evento e outro
        for i in range(num_eventos):
            evento_atual = timeline_data[i]
            pagina_inicio = evento_atual['pagina']
            
            # Se não for o último evento, o bloco vai até a página anterior do próximo evento
            if i + 1 < num_eventos:
                pagina_fim = timeline_data[i+1]['pagina'] - 1
            else:
                pagina_fim = total_paginas
            
            # Garante que a página fim não seja menor que a início (caso eventos ocorram na mesma página)
            pagina_fim = max(pagina_inicio, pagina_fim)
            
            texto_bloco = ""
            for p in range(pagina_inicio - 1, pagina_fim):
                texto_bloco += doc_leitura[p].get_text("text") + "\n"
                
            prompt = (
                f"<|user|>\n"
                f"Analise o bloco de um processo administrativo abaixo.\n"
                f"Resuma de forma direta e em tópicos curtos:\n"
                f"- O que foi enviado/anexado\n"
                f"- O que foi dito/informado\n"
                f"- O que foi pedido/solicitado\n\n"
                f"CABEÇALHO DO EVENTO: {evento_atual['evento_str']}\n\n"
                f"TEXTO DO BLOCO:\n{texto_bloco[:3000]}\n<|end|>\n"
                f"<|assistant|>\n"
                f"Resumo do bloco:\n"
            )
            
            blocos.append({
                "item": evento_atual,
                "prompt": prompt,
                "paginas": f"Págs {pagina_inicio} a {pagina_fim}" if pagina_inicio != pagina_fim else f"Pág {pagina_inicio}"
            })

        # 2. Processamento em paralelo dos blocos (mesma lógica de balanceamento anterior)
        fila_tarefas = queue.Queue()
        for bloco in blocos:
            fila_tarefas.put(bloco)

        lock = threading.Lock()

        def worker(usar_cpu):
            while not fila_tarefas.empty():
                try:
                    bloco_atual = fila_tarefas.get_nowait()
                except queue.Empty:
                    break
                
                # Aumentei o max_tokens para 200 pois a resposta exigirá tópicos
                resumo_bloco = chamar_llm_api(bloco_atual["prompt"], 200, 0.2, usar_cpu)
                
                linha_pdf = f"**{bloco_atual['paginas']} | {bloco_atual['item']['evento_str']}**\n{resumo_bloco}\n"
                linha_txt = f"{bloco_atual['paginas']} | {bloco_atual['item']['evento_str']} | {resumo_bloco.replace(chr(10), ' ')}"
                
                with lock:
                    eventos_resumidos_raw.append((bloco_atual['item']['pagina'], linha_pdf))
                    timeline_para_txt_raw.append((bloco_atual['item']['pagina'], linha_txt))
                
                fila_tarefas.task_done()

        threads = []
        for _ in range(8):
            t = threading.Thread(target=worker, args=(False,))
            threads.append(t)
            t.start()
        for _ in range(2):
            t = threading.Thread(target=worker, args=(True,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Ordena os resultados pela página
        eventos_resumidos_raw.sort(key=lambda x: x[0])
        timeline_para_txt_raw.sort(key=lambda x: x[0])
        
        eventos_resumidos = [x[1] for x in eventos_resumidos_raw]
        timeline_para_txt = [x[1] for x in timeline_para_txt_raw]
        
        # 3. Análise final de inconsistências
        texto_todos_resumos = "\n".join(eventos_resumidos)
        prompt_inconsistencias = (
            f"<|user|>\n"
            f"Analise a linha do tempo resumida de um processo administrativo abaixo.\n"
            f"Sua tarefa é identificar estritamente se existem INCONSISTÊNCIAS LÓGICAS (ex: contradições de atores, quem enviou vs quem diz que enviou, saltos inexplicáveis no trâmite).\n"
            f"Se TUDO estiver correto e coerente, responda APENAS: 'Nenhuma inconsistência lógica detectada no fluxo do processo.'\n"
            f"Se houver contradições, liste-as de forma direta.\n\n"
            f"LINHA DO TEMPO:\n{texto_todos_resumos[:3500]}\n<|end|>\n"
            f"<|assistant|>\n"
            f"Análise de Inconsistências:\n"
        )
        # Envia a verificação de inconsistência para a GPU
        inconsistencias_resultado = chamar_llm_api(prompt_inconsistencias, 250, 0.1, False)

    caminho_events_txt = gerar_arquivo_eventos(timeline_para_txt if timeline_data else [])

    dados_extras = f"--- DADOS DE TABELAS ---\n{texto_tabelas}\n\n--- DADOS DE IMAGENS ---\n{texto_ocr}"
    resumo_final = resumo_ia

    if len(texto_ocr) > 20 or len(texto_tabelas) > 10: 
        analise_complementar = avaliar_e_justificar_ocr(resumo_ia, dados_extras)
        if "IRRELEVANTE" not in analise_complementar.upper():
            resumo_final = f"{resumo_ia} {analise_complementar}"

    paginas_ref = localizar_paginas_referencia(caminho_pdf, resumo_ia)
    resumo_eventos_str = "\n".join(eventos_resumidos) if timeline_data and eventos_resumidos else "Nenhuma movimentação detalhada encontrada."

    doc_leitura.close()

    # Adicionado o campo "INCONSISTÊNCIAS" no retorno final que vai para o PDF
    return (
        f"**DE:** {meta['De']}\n"
        f"**DOCUMENTO:** {meta.get('Documento', 'Não identificado')}\n"
        f"**PARA:** {meta['Para']}\n"
        f"**PÁGINAS DE ORIGEM:** {paginas_ref}\n"
        f"**RESUMO PRINCIPAL:** {resumo_final}\n"
        f"**INCONSISTÊNCIAS IDENTIFICADAS:**\n{inconsistencias_resultado}\n\n"
        f"**DETALHAMENTO POR BLOCOS:**\n{resumo_eventos_str}"
    ), dados_extras, caminho_events_txt