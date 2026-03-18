import fitz
import concurrent.futures
import pytesseract
import pdfplumber
import requests
import queue
import threading
import re
from PIL import Image, ImageEnhance, ImageOps
from .limpeza import extrair_metadados_protocolo, extrair_texto_bruto_pdf, limpar_texto_para_ia, gerar_arquivo_eventos

URL_GPU_1 = "http://llama-gpu:8001/v1/completions"
URL_GPU_2 = "http://llama-gpu-2:8003/v1/completions"
URL_CPU = "http://llama-cpu:8002/v1/completions"

http_session = requests.Session()

def chamar_llm_api(prompt, max_tokens=450, temperature=0.2, usar_cpu=False):
    url = URL_GPU_1
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stop": ["<|end|>"]
    }
    try:
        response = http_session.post(url, json=payload, timeout=300, proxies={"http": None, "https": None}) 
        response.raise_for_status()
        return response.json()['choices'][0]['text'].strip()
    except Exception:
        return "Erro ao processar com IA."

def processar_pagina_ocr(caminho_pdf, numero_pagina, config_tesseract):
    try:
        doc = fitz.open(caminho_pdf)
        pagina = doc[numero_pagina]
        if len(pagina.get_text("text").strip()) > 100:
            doc.close()
            return (numero_pagina, "")
        pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_gray = ImageOps.grayscale(img)
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(2.0)
        texto = pytesseract.image_to_string(img_contrast, lang="por", config=config_tesseract)
        doc.close()
        return (numero_pagina, texto + "\n")
    except Exception:
        return (numero_pagina, "")

def extrair_ocr_melhorado(caminho_pdf):
    texto_ocr = ""
    config_tesseract = "--psm 6" 
    try:
        doc_teste = fitz.open(caminho_pdf)
        limite = min(15, len(doc_teste))
        doc_teste.close()
        resultados = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futuros = [executor.submit(processar_pagina_ocr, caminho_pdf, i, config_tesseract) for i in range(limite)]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
        resultados.sort(key=lambda x: x[0])
        for _, texto in resultados:
            texto_ocr += texto
    except Exception:
        return ""
    return texto_ocr.strip()

def processar_pagina_tabela(caminho_pdf, idx):
    texto_local = ""
    try:
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futuros = [executor.submit(processar_pagina_tabela, caminho_pdf, idx) for idx in paginas_com_tabela]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())
        resultados.sort(key=lambda x: x[0])
        for _, texto in resultados:
            texto_tabelas += texto
    except Exception:
        return ""
    return texto_tabelas.strip()

def avaliar_e_justificar_ocr(resumo_original, dados_extras):
    prompt = (
        f"<|user|>\n"
        f"Você possui o RESUMO PRINCIPAL de um documento e DADOS EXTRAS extraídos de tabelas e imagens anexas.\n"
        f"REGRAS OBRIGATÓRIAS: RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL. NÃO USE OUTROS IDIOMAS.\n"
        f"Se os DADOS EXTRAS não adicionarem informações úteis de valores, empresas ou quantitativos ao resumo, responda APENAS com a palavra 'IRRELEVANTE'.\n"
        f"Se os DADOS EXTRAS contiverem valores financeiros, quantidades importantes ou dados técnicos pertinentes, crie UMA ÚNICA FRASE como justificativa ou complemento ao resumo principal.\n\n"
        f"RESUMO PRINCIPAL: {resumo_original}\n\n"
        f"DADOS EXTRAS:\n{dados_extras[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    return chamar_llm_api(prompt, max_tokens=150, temperature=0.2, usar_cpu=False)

def gerar_resumo_phi(texto_limpo):
    prompt = (
        f"<|user|>\n"
        f"Você é um assistente administrativo da SETI/PR. Sua tarefa é ler o documento abaixo e responder EXCLUSIVAMENTE em Português do Brasil.\n"
        f"Regra: Escreva uma única frase direta e completa. Não invente campos extras. NÃO USE OUTROS IDIOMAS.\n\n"
        f"TEXTO PARA ANALISAR:\n"
        f"### INÍCIO ###\n{texto_limpo[:1500]}\n### FIM ###\n<|end|>\n"
        f"<|assistant|>\n"
        f"Resumo em português: "
    )
    return chamar_llm_api(prompt, max_tokens=200, temperature=0.1, usar_cpu=False)

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

def processar_documento_final(caminho_pdf):
    doc_leitura = fitz.open(caminho_pdf)
    total_paginas = len(doc_leitura)
    texto_bruto = extrair_texto_bruto_pdf(caminho_pdf)
    
    if not texto_bruto.strip(): 
        return "Erro: PDF sem texto.", "", "", "", "", {}

    meta = extrair_metadados_protocolo(texto_bruto)
    corpo_limpo = limpar_texto_para_ia(texto_bruto)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_resumo = executor.submit(gerar_resumo_phi, corpo_limpo)
        future_ocr = executor.submit(extrair_ocr_melhorado, caminho_pdf)
        future_tabelas = executor.submit(extrair_tabelas_pdf, caminho_pdf)
        
        resumo_ia = future_resumo.result()
        texto_ocr = future_ocr.result()
        texto_tabelas = future_tabelas.result()

    mapa_paginas = {}
    mov_atual = 1

    for i in range(total_paginas):
        pagina = doc_leitura[i]
        w = pagina.rect.width
        h = pagina.rect.height
        rect_superior = fitz.Rect(0, 0, w, h * 0.35)
        texto_superior = pagina.get_text("text", clip=rect_superior)
        num_mov_encontrado = None

        match_carimbo = re.search(r'(?i)(?:Fls|FIs|Fls\.|FIs\.)[.\s_]*\d+[a-zA-Z]?[\s\S]{0,40}?Mov[.\s_]*(\d+)', texto_superior)
        if not match_carimbo:
            match_carimbo = re.search(r'(?i)PROTOCOLO[\s\S]{0,40}?Mov[.\s_]*(\d+)', texto_superior)

        if match_carimbo:
            num_mov_encontrado = int(match_carimbo.group(1))
        else:
            rect_canto_direito = fitz.Rect(w * 0.6, 0, w, h * 0.3)
            texto_canto = pagina.get_text("text", clip=rect_canto_direito)
            linhas_canto = [linha.strip() for linha in texto_canto.split('\n') if linha.strip()]
            for idx in range(len(linhas_canto) - 1):
                if re.match(r'^\d+[a-zA-Z]?$', linhas_canto[idx]) and re.match(r'^\d+$', linhas_canto[idx+1]):
                    num_mov_encontrado = int(linhas_canto[idx+1])
                    break
            if num_mov_encontrado is None:
                texto_completo = pagina.get_text("text")
                match_strict = re.search(r'(?i)PROTOCOLO[\s\S]{0,40}?(?:Fls|FIs)[.\s_]*\d+[a-zA-Z]?[\s\S]{0,40}?Mov[.\s_]*(\d+)[\s\S]{0,40}?INTEGRADO', texto_completo)
                if match_strict:
                    num_mov_encontrado = int(match_strict.group(1))

        if num_mov_encontrado is not None and num_mov_encontrado >= mov_atual:
            mov_atual = num_mov_encontrado
        mapa_paginas[i + 1] = mov_atual

    mov_starts = {}
    for pag in range(1, total_paginas + 1):
        mov = mapa_paginas[pag]
        if mov not in mov_starts:
            mov_starts[mov] = pag

    movs_ordenados = sorted(mov_starts.keys(), key=lambda m: mov_starts[m])
    movimentacoes = []
    
    for idx, mov in enumerate(movs_ordenados):
        pag_inicio = mov_starts[mov]
        if idx < len(movs_ordenados) - 1:
            proxima_mov = movs_ordenados[idx + 1]
            pag_fim = mov_starts[proxima_mov] - 1
        else:
            pag_fim = total_paginas
        movimentacoes.append({
            'mov': str(mov),
            'pag_inicio': pag_inicio,
            'pag_fim': pag_fim
        })

    eventos_resumidos_raw = []
    timeline_para_txt_raw = []
    inconsistencias_resultado = "Não foi possível analisar inconsistências."
    resumo_desde_seti = "Sem movimentações recentes."
    inconsistencias_seti = "Sem inconsistências."
    debug_texto_blocos = "=== DEBUG DE TEXTOS E PROMPTS ENVIADOS PARA A IA ===\n\n"
    
    if movimentacoes:
        blocos = []
        for mov in movimentacoes:
            texto_bloco = ""
            for p in range(mov['pag_inicio'] - 1, mov['pag_fim']):
                texto_bloco += doc_leitura[p].get_text("text") + " "
            texto_bloco = re.sub(r'\s+', ' ', texto_bloco).strip()
            prompt = (
                f"<|user|>\n"
                f"Você é um assistente técnico e analítico rigoroso. Analise APENAS o texto da Movimentação {mov['mov']} abaixo.\n\n"
                f"REGRAS DE SEGURANÇA:\n"
                f"1. RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL. NÃO USE ESPANHOL OU INGLÊS.\n"
                f"2. Extraia EXCLUSIVAMENTE as informações contidas no texto. Se algo não constar, escreva 'Não informado'.\n"
                f"3. NUNCA invente nomes, dados financeiros, leis, políticos ou fatos externos ao documento.\n"
                f"4. O resumo deve ter no máximo 3 frases, focando puramente na ação administrativa solicitada.\n\n"
                f"Responda estritamente neste formato:\n"
                f"- **Tipo de Documento:**\n"
                f"- **Remetente/Assinante:**\n"
                f"- **Destinatário:**\n"
                f"- **Assunto/Resumo da Movimentação:**\n\n"
                f"TEXTO DA MOVIMENTAÇÃO:\n{texto_bloco[:4000]}\n<|end|>\n"
                f"<|assistant|>\n"
            )
            debug_texto_blocos += f"--- MOVIMENTAÇÃO {mov['mov']} (Págs {mov['pag_inicio']} a {mov['pag_fim']}) ---\n"
            debug_texto_blocos += f"TEXTO EXTRAÍDO BRUTO:\n{texto_bloco}\n"
            debug_texto_blocos += f"PROMPT FINAL ENVIADO:\n{prompt}\n"
            debug_texto_blocos += "="*80 + "\n\n"
            
            blocos.append({
                "mov": mov['mov'],
                "prompt": prompt,
                "pag_inicio": mov['pag_inicio'],
                "paginas": f"Págs {mov['pag_inicio']} a {mov['pag_fim']}" if mov['pag_inicio'] != mov['pag_fim'] else f"Pág {mov['pag_inicio']}"
            })

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
                resumo_bloco = chamar_llm_api(bloco_atual["prompt"], 450, 0.2, usar_cpu)
                linha_pdf = f"**{bloco_atual['paginas']} | Movimentação {bloco_atual['mov']}**\n{resumo_bloco}\n"
                linha_txt = f"{bloco_atual['paginas']} | Movimentação {bloco_atual['mov']} | {resumo_bloco.replace(chr(10), ' ')}"
                with lock:
                    eventos_resumidos_raw.append((bloco_atual['pag_inicio'], linha_pdf, resumo_bloco))
                    timeline_para_txt_raw.append((bloco_atual['pag_inicio'], linha_txt))
                fila_tarefas.task_done()

        threads = []
        for _ in range(3):
            t = threading.Thread(target=worker, args=(False,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        eventos_resumidos_raw.sort(key=lambda x: x[0])
        timeline_para_txt_raw.sort(key=lambda x: x[0])
        
        eventos_resumidos = [x[1] for x in eventos_resumidos_raw]
        resumos_puros = [x[2] for x in eventos_resumidos_raw]
        timeline_para_txt = [x[1] for x in timeline_para_txt_raw]
        
        idx_seti = -1
        for i in range(len(resumos_puros) - 1, -1, -1):
            if "SETI" in resumos_puros[i].upper():
                idx_seti = i
                break

        trecho_pos_seti = resumos_puros[idx_seti:] if idx_seti != -1 else resumos_puros
        texto_pos_seti = "\n".join(trecho_pos_seti)
        
        prompt_resumo_seti = (
            f"<|user|>\nResuma o que aconteceu no processo desde que ele passou pela SETI pela última vez.\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL. NÃO USE ESPANHOL OU INGLÊS.\n"
            f"- Escreva um ÚNICO parágrafo contínuo e direto.\n"
            f"- NÃO use tópicos, hifens ou quebras de linha.\n\n"
            f"TEXTO:\n{texto_pos_seti[:3000]}\n<|end|>\n<|assistant|>\n"
        )
        resumo_desde_seti = chamar_llm_api(prompt_resumo_seti, 250, 0.2, False).replace('\n', ' ').strip()
        
        prompt_inconsistencias_seti = (
            f"<|user|>\nExistem erros de fluxo ou datas contraditórias especificamente neste trecho final (após passar pela SETI)?\n"
            f"TEXTO:\n{texto_pos_seti[:3000]}\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL. NÃO USE OUTROS IDIOMAS.\n"
            f"- Se não houver, responda apenas 'Fluxo recente íntegro'.\n"
            f"- Se houver, descreva em um ÚNICO parágrafo, sem tópicos ou quebras de linha.\n<|end|>\n<|assistant|>\n"
        )
        inconsistencias_seti = chamar_llm_api(prompt_inconsistencias_seti, 250, 0.1, False).replace('\n', ' ').strip()

        texto_todos_resumos = "\n".join(eventos_resumidos)
        prompt_inconsistencias = (
            f"<|user|>\n"
            f"Analise a cronologia de movimentações abaixo em busca de erros lógicos ou processuais:\n"
            f"1. **Anacronismo:** Datas inconsistentes.\n"
            f"2. **Contradição:** Conflitos envolvendo pedidos, remetentes ou destinatários.\n"
            f"3. **Ruptura de Fluxo:** Saltos entre órgãos ou pessoas que não fazem sentido administrativo.\n\n"
            f"LINHA DO TEMPO DAS MOVIMENTAÇÕES:\n{texto_todos_resumos[:3500]}\n\n"
            f"REGRAS OBRIGATÓRIAS: RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL. NÃO USE ESPANHOL.\n"
            f"Se não houver erros, responda: 'Fluxo processual íntegro.'\n"
            f"Se houver erros, descreva-os de forma técnica e breve.\n<|end|>\n"
            f"<|assistant|>\n"
        )
        inconsistencias_resultado = chamar_llm_api(prompt_inconsistencias, 300, 0.1, False)

    caminho_events_txt = gerar_arquivo_eventos(timeline_para_txt if movimentacoes else [])
    dados_extras = f"--- DADOS DE TABELAS ---\n{texto_tabelas}\n\n--- DADOS DE IMAGENS ---\n{texto_ocr}"
    resumo_final = resumo_ia

    if len(texto_ocr) > 20 or len(texto_tabelas) > 10: 
        analise_complementar = avaliar_e_justificar_ocr(resumo_ia, dados_extras)
        if "IRRELEVANTE" not in analise_complementar.upper():
            resumo_final = f"{resumo_ia} {analise_complementar}"

    resumo_eventos_str = "\n".join(eventos_resumidos) if movimentacoes and eventos_resumidos else "Nenhuma movimentação detalhada encontrada."
    doc_leitura.close()

    prompt_resposta = (
        f"<|user|>\n"
        f"Com base EXCLUSIVAMENTE no resumo principal abaixo, redija o corpo de um ofício ou memorando.\n"
        f"RESUMO: {resumo_final}\n\n"
        f"REGRAS OBRIGATÓRIAS DE SEGURANÇA:\n"
        f"1. APENAS O TEXTO DO CORPO. SEM cabeçalho, SEM saudação, SEM data, SEM assinatura.\n"
        f"2. NUNCA invente justificativas, laboratórios, projetos, nomes ou fatos.\n"
        f"3. Não 'encha linguiça'. Se a situação for simples (ex: compra interna de mantimentos), a resposta deve ser curta e direta.\n"
        f"4. Idioma: Português do Brasil.\n"
        f"5. Escreva um texto completo, NUNCA deixe frases cortadas ou incompletas no final.\n"
        f"<|end|>\n"
        f"<|assistant|>\n"
    )
    corpo_resposta = chamar_llm_api(prompt_resposta, 600, 0.1, False).strip()

    return (
        f"**INTERESSADO:** {meta.get('De', 'Não identificado')}\n"
        f"**DOCUMENTO:** {meta.get('Documento', 'Não identificado')}\n"
        f"**DESTINATÁRIO:** {meta.get('Para', 'Não identificado')}\n"
        f"**RESUMO PRINCIPAL:** {resumo_final}\n\nResumo desde passagem pela SETI: {resumo_desde_seti}\n"
        f"**INCONSISTÊNCIAS IDENTIFICADAS:**\nDesde a SETI: {inconsistencias_seti}\nGerais: {inconsistencias_resultado}\n\n"
        f"**DETALHAMENTO POR BLOCOS:**\n{resumo_eventos_str}"
    ), dados_extras, caminho_events_txt, debug_texto_blocos, corpo_resposta, meta