import os
import re
import requests
import fitz
import pytesseract
import concurrent.futures
import pdfplumber
import queue
import threading
from PIL import Image, ImageOps, ImageEnhance
from datetime import datetime as dt
from workalendar.america import Brazil
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from limpeza import extrair_texto_bruto_pdf, extrair_metadados_protocolo, limpar_texto_para_ia, gerar_arquivo_eventos

URL_GPU_1 = "http://llama-gpu:8001/v1/completions"
URL_GPU_2 = "http://llama-gpu-2:8003/v1/completions"
URL_CPU = "http://llama-cpu:8002/v1/completions"

http_session = requests.Session()

def consultar_legislacao_rag(query):
    try:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        persist_directory = "./chroma_db"

        if not os.path.exists(persist_directory):
            diretorio_leis = "./documentos/leis"
            
            if not os.path.exists(diretorio_leis):
                return "Erro: O diretório './documentos/leis' não foi encontrado."

            loader = DirectoryLoader(diretorio_leis, glob="**/*.md", loader_cls=TextLoader)
            documentos = loader.load()

            if not documentos:
                return "Aviso: Nenhum arquivo de resumo encontrado para indexação."

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,
                chunk_overlap=100,
                separators=["\n### ", "\n**", "\n\n", "\n", " "]
            )
            textos_fatiados = text_splitter.split_documents(documentos)

            vectorstore = Chroma.from_documents(
                documents=textos_fatiados,
                embedding=embeddings,
                persist_directory=persist_directory
            )
        else:
            vectorstore = Chroma(
                persist_directory=persist_directory,
                embedding_function=embeddings
            )

        docs_relvantes = vectorstore.similarity_search(query, k=3)
        contexto_extraido = "\n\n---\n\n".join([doc.page_content for doc in docs_relvantes])
        
        return contexto_extraido

    except Exception as e:
        return f"Erro no processamento RAG: {str(e)}"
    
def chamar_llm_api(prompt, max_tokens=800, temperature=0.0, usar_cpu=False):
    url = URL_GPU_1
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stop": ["<|end|>"]
    }
    try:
        response = http_session.post(url, json=payload, timeout=300, proxies={"http": None, "https": None}) 
        response.raise_for_status()
        texto = response.json()['choices'][0]['text'].strip()
        return texto
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
        f"Sua tarefa é extrair informações numéricas dos DADOS EXTRAS para complementar o RESUMO.\n"
        f"REGRAS OBRIGATÓRIAS:\n"
        f"1. Se não houver valores úteis, responda APENAS: 'IRRELEVANTE'.\n"
        f"2. Se houver, escreva UMA ÚNICA FRASE DIRETA com os valores, quantidades e produtos.\n"
        f"3. REGRA ABSOLUTA: PROIBIDO usar metalinguagem. NÃO escreva 'O resumo principal diz', 'Os dados extras mostram' ou 'A tabela indica'. Escreva apenas o fato direto.\n\n"
        f"RESUMO: {resumo_original}\n\n"
        f"DADOS EXTRAS:\n{dados_extras[:1500]}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    return chamar_llm_api(prompt, max_tokens=150, temperature=0.0, usar_cpu=False)

def gerar_resumo_phi(texto_limpo):
    prompt = (
        f"<|user|>\n"
        f"Sua tarefa é ler o documento abaixo.\n"
        f"Regra: Escreva UMA ÚNICA FRASE explicando qual é a ação administrativa exigida (quem pediu o quê). Não invente dados.\n\n"
        f"TEXTO PARA ANALISAR:\n"
        f"### INÍCIO ###\n{texto_limpo[:1500]}\n### FIM ###\n<|end|>\n"
        f"<|assistant|>\n"
        f"Resumo em português: "
    )
    return chamar_llm_api(prompt, max_tokens=200, temperature=0.0, usar_cpu=False)

def gerar_assunto_curto_ia(resumo):
    prompt = (
        f"<|user|>\n"
        f"Leia o resumo abaixo e defina um 'Assunto' oficial e curto (no máximo 5 palavras).\n"
        f"Responda APENAS com o texto do assunto, SEM ESCREVER a palavra 'Assunto:'.\n\n"
        f"RESUMO: {resumo}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    resposta = chamar_llm_api(prompt, max_tokens=30, temperature=0.0, usar_cpu=False)
    return re.sub(r'(?i)^assunto:\s*', '', resposta).strip()

def classificar_natureza_processo(resumo, assunto):
    prompt = (
        f"<|user|>\n"
        f"Classifique a natureza do processo em APENAS UMA das categorias abaixo, baseando-se no resumo e assunto:\n"
        f"- Licitação/Compras (Gatilhos: Pregão, Ata, Compra, Dispensa)\n"
        f"- RH (Gatilhos: Férias, Licença, Cargo, Progressão)\n"
        f"- Prestação de Contas (Gatilhos: TED, Relatório Financeiro)\n"
        f"- Ouvidoria/Denúncia (Gatilhos: Reclamação, Ética)\n"
        f"- Financiamento/Pesquisa (Gatilhos: Fomento, Projeto)\n"
        f"- Gestão Orçamentária (Gatilhos: PPA, LOA, Cota)\n\n"
        f"Resumo: {resumo}\nAssunto: {assunto}\n"
        f"Responda EXATAMENTE com o nome de uma das categorias acima.\n<|end|>\n<|assistant|>\n"
    )
    return chamar_llm_api(prompt, max_tokens=20, temperature=0.0, usar_cpu=False).strip()

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
    calendario_br = Brazil()
    
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
    inconsistencias_resultado = "Fluxo processual íntegro."
    resumo_desde_seti = "Sem movimentações recentes."
    inconsistencias_seti = "Fluxo recente íntegro."
    decisao_dg = "Nenhuma manifestação da Diretoria Geral encontrada."
    debug_texto_blocos = "=== DEBUG DE TEXTOS E PROMPTS ENVIADOS PARA A IA ===\n\n"
    resultado_calculos = "Nenhum cálculo a ser analisado."
    alertas_sla_texto = ""
    
    if movimentacoes:
        blocos = []
        for mov in movimentacoes:
            texto_bloco = ""
            for p in range(mov['pag_inicio'] - 1, mov['pag_fim']):
                texto_bloco += doc_leitura[p].get_text("text") + " "
            texto_bloco = re.sub(r'\s+', ' ', texto_bloco).strip()
            
            match_data_mov = re.search(r'(?i)(\d{2}/\d{2}/\d{4})', texto_bloco)
            match_prazo_mov = re.search(r'(?i)(\d+)\s+dias?\s+úteis', texto_bloco)
            
            if match_data_mov and match_prazo_mov:
                try:
                    dias_prazo = int(match_prazo_mov.group(1))
                    data_ref = dt.strptime(match_data_mov.group(1), "%d/%m/%Y").date()
                    data_limite_sla = calendario_br.add_working_days(data_ref, dias_prazo)
                    alertas_sla_texto += f"\n[SLA ALERTA - Mov {mov['mov']}]: Detectado prazo de {dias_prazo} dias úteis a partir de {match_data_mov.group(1)}. Limite calculado: {data_limite_sla.strftime('%d/%m/%Y')}."
                except Exception:
                    pass
            
            prompt = (
                f"<|user|>\n"
                f"Você é um assistente analítico. Analise APENAS o texto da Movimentação {mov['mov']} abaixo.\n\n"
                f"REGRAS:\n"
                f"1. RESPONDA EXCLUSIVAMENTE EM PORTUGUÊS DO BRASIL.\n"
                f"2. O resumo deve ter no máximo 2 frases curtas.\n\n"
                f"Responda estritamente neste formato:\n"
                f"- **Tipo de Documento:**\n"
                f"- **Remetente:**\n"
                f"- **Destinatário:**\n"
                f"- **Resumo:**\n\n"
                f"TEXTO:\n{texto_bloco[:3000]}\n<|end|>\n"
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
                resumo_bloco = chamar_llm_api(bloco_atual["prompt"], 300, 0.0, usar_cpu)
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
            if "SETI" in resumos_puros[i].upper() or "SECTI" in resumos_puros[i].upper():
                idx_seti = i
                break

        trecho_pos_seti = resumos_puros[idx_seti:] if idx_seti != -1 else resumos_puros
        texto_pos_seti = "\n".join(trecho_pos_seti)
        
        prompt_resumo_seti = (
            f"<|user|>\nResuma EXATAMENTE a última ação administrativa (o que foi pedido e por quem) neste trecho.\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- Escreva UMA ÚNICA FRASE.\n"
            f"- Não misture informações antigas.\n"
            f"TEXTO:\n{texto_pos_seti[:3000]}\n<|end|>\n<|assistant|>\n"
        )
        resumo_desde_seti = chamar_llm_api(prompt_resumo_seti, 200, 0.0, False).replace('\n', ' ').strip()
        
        prompt_inconsistencias_seti = (
            f"<|user|>\nExistem erros processuais explícitos neste trecho final?\n"
            f"TEXTO:\n{texto_pos_seti[:3000]}\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- Se não houver erros, a sua resposta deve ser EXATAMENTE a frase: 'Fluxo recente íntegro.' NÃO adicione nenhuma explicação ou justificativa.\n"
            f"<|end|>\n<|assistant|>\n"
        )
        inconsistencias_seti = chamar_llm_api(prompt_inconsistencias_seti, 100, 0.0, False).replace('\n', ' ').strip()
        if re.search(r'(?i)íntegro', inconsistencias_seti) and not re.search(r'(?i)erro|inconsistência|falha', inconsistencias_seti):
            inconsistencias_seti = "Fluxo recente íntegro."

        texto_todos_resumos = "\n".join(eventos_resumidos)
        prompt_inconsistencias = (
            f"<|user|>\n"
            f"Analise a cronologia de movimentações abaixo em busca de erros lógicos:\n"
            f"LINHA DO TEMPO DAS MOVIMENTAÇÕES:\n{texto_todos_resumos[:3500]}\n\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- Se não houver erros explícitos, a sua resposta deve ser EXATAMENTE a frase: 'Fluxo processual íntegro.' NÃO adicione explicações.\n"
            f"<|end|>\n"
            f"<|assistant|>\n"
        )
        inconsistencias_resultado = chamar_llm_api(prompt_inconsistencias, 300, 0.0, False).strip()
        if re.search(r'(?i)íntegro', inconsistencias_resultado) and not re.search(r'(?i)erro|inconsistência|falha', inconsistencias_resultado):
            inconsistencias_resultado = "Fluxo processual íntegro."
        
        prompt_decisao_dg = (
            f"<|user|>\nProcure na linha do tempo abaixo a ÚLTIMA manifestação da Diretoria Geral.\n"
            f"TEXTO:\n{texto_todos_resumos[:3500]}\n\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"- Escreva no máximo 2 frases.\n"
            f"- Se não houver, responda apenas 'Nenhuma manifestação da Diretoria Geral encontrada.'\n<|end|>\n"
            f"<|assistant|>\n"
        )
        decisao_dg = chamar_llm_api(prompt_decisao_dg, 200, 0.0, False).replace('\n', ' ').strip()

        prompt_calculos = (
            f"<|user|>\n"
            f"Extraia os valores financeiros e verifique a matemática.\n"
            f"DADOS:\n{texto_tabelas[:1500]}\n{texto_ocr[:1000]}\n{corpo_limpo[:1500]}\n\n"
            f"REGRAS OBRIGATÓRIAS:\n"
            f"1. Encontre a Quantidade, Valor Unitário e Valor Total declarado.\n"
            f"2. Se faltar algum desses três, responda APENAS a palavra: AUSENTE.\n"
            f"3. Multiplique Quantidade x Valor Unitário.\n"
            f"4. Compare o resultado matemático com o Valor Total declarado. ATENÇÃO: R$ 1441,50 é o mesmo que R$ 1.441,50. Ignore o ponto de milhar.\n"
            f"5. Escreva sua conclusão em UMA ÚNICA FRASE. Comece a frase com 'Valores batem:' ou 'Divergência:'. Não crie listas enumeradas.\n"
            f"<|end|>\n<|assistant|>\n"
        )
        resultado_calculos = chamar_llm_api(prompt_calculos, 200, 0.0, False).strip()
        if "AUSENTE" in resultado_calculos.upper():
            resultado_calculos = "Nenhum cálculo a ser analisado."

    caminho_events_txt = gerar_arquivo_eventos(timeline_para_txt if movimentacoes else [])
    dados_extras = f"--- DADOS DE TABELAS ---\n{texto_tabelas}\n\n--- DADOS DE IMAGENS ---\n{texto_ocr}"
    resumo_final = resumo_ia

    if len(texto_ocr) > 20 or len(texto_tabelas) > 10: 
        analise_complementar = avaliar_e_justificar_ocr(resumo_ia, dados_extras)
        if "IRRELEVANTE" not in analise_complementar.upper():
            resumo_final = f"{resumo_ia} {analise_complementar}"

    meta['Assunto_IA'] = gerar_assunto_curto_ia(resumo_final)

    resumo_eventos_str = "\n".join(eventos_resumidos) if movimentacoes and eventos_resumidos else "Nenhuma movimentação detalhada encontrada."
    doc_leitura.close()
    
    legislacao_rag = consultar_legislacao_rag(resumo_final)
    
    prompt_legal = (
        f"<|user|>\n"
        f"Você é um parecerista. Faça uma análise legal deste processo com base na lei aplicável.\n"
        f"PROCESSO: {resumo_final}\n"
        f"LEI RECUPERADA PELO RAG: {legislacao_rag}\n"
        f"REGRA OBRIGATÓRIA: Escreva no máximo 2 frases. Aplique a lei ao resumo fornecido. Diga se o pedido principal parece legalmente fundamentado.\n"
        f"<|end|>\n<|assistant|>\n"
    )
    analise_legal = chamar_llm_api(prompt_legal, 300, 0.0, False).strip()

    natureza_processo = classificar_natureza_processo(resumo_final, meta.get('Assunto', ''))
    
    texto_limpo_checklist = re.sub(r'\*\*Pág.*?\|\s*Movimentação.*?\*\*\n?', '', texto_todos_resumos)

    prompt_checklist = (
        f"<|user|>\n"
        f"Atue como um auditor rigoroso. Categoria: {natureza_processo}.\n"
        f"DADOS PARA ANÁLISE:\n{texto_tabelas[:1000]}\n{texto_limpo_checklist[:2000]}\n\n"
        f"Responda 'SIM', 'NÃO' ou 'NÃO CONSTA' para cada item abaixo, seguido de uma justificativa curta.\n"
    )
    
    if "Licitação" in natureza_processo or "Compras" in natureza_processo:
        prompt_checklist += (
            "Item 1: Existem no mínimo 3 propostas de preço (orçamentos) válidas de empresas diferentes?\n"
            "Item 2: Existem certidões de regularidade (CND, FGTS)?\n"
            "Item 3: Há documento de empenho e ele possui data posterior à nota fiscal?\n"
        )
    elif "RH" in natureza_processo:
        prompt_checklist += (
            "Item 1: O período aquisitivo está correto?\n"
            "Item 2: Existem assinaturas avançadas?\n"
        )
    elif "Prestação" in natureza_processo:
        prompt_checklist += (
            "Item 1: Existem sobras no Saldo Disponível?\n"
        )
    else:
        prompt_checklist += "Item 1: A documentação está completa?\n"
        
    prompt_checklist += (
        "\nSiga EXATAMENTE este modelo de resposta:\n"
        "- Item 1: [SIM/NÃO/NÃO CONSTA] - [Sua justificativa]\n"
    )
    if "Licitação" in natureza_processo or "Compras" in natureza_processo:
        prompt_checklist += "- Item 2: [SIM/NÃO/NÃO CONSTA] - [Sua justificativa]\n- Item 3: [SIM/NÃO/NÃO CONSTA] - [Sua justificativa]\n"
    elif "RH" in natureza_processo:
        prompt_checklist += "- Item 2: [SIM/NÃO/NÃO CONSTA] - [Sua justificativa]\n"

    prompt_checklist += f"<|end|>\n<|assistant|>\n"
    
    analise_checklist_raw = chamar_llm_api(prompt_checklist, 200, 0.0, False).strip()
    
    analise_checklist_raw = analise_checklist_raw.replace('**', '').replace('[', '').replace(']', '')
    resultado_calculos = resultado_calculos.replace('**', '').replace('[', '').replace(']', '')
    
    if "Licitação" in natureza_processo or "Compras" in natureza_processo:
        analise_checklist_raw = re.sub(r'(?i)Item 1\s*:', 'Mínimo de 3 orçamentos:', analise_checklist_raw)
        analise_checklist_raw = re.sub(r'(?i)Item 2\s*:', 'Certidões de regularidade:', analise_checklist_raw)
        analise_checklist_raw = re.sub(r'(?i)Item 3\s*:', 'Empenho posterior à NF:', analise_checklist_raw)
    elif "RH" in natureza_processo:
        analise_checklist_raw = re.sub(r'(?i)Item 1\s*:', 'Período aquisitivo:', analise_checklist_raw)
        analise_checklist_raw = re.sub(r'(?i)Item 2\s*:', 'Assinaturas avançadas:', analise_checklist_raw)
    elif "Prestação" in natureza_processo:
        analise_checklist_raw = re.sub(r'(?i)Item 1\s*:', 'Sobras no Saldo Disponível:', analise_checklist_raw)
    else:
        analise_checklist_raw = re.sub(r'(?i)Item 1\s*:', 'Documentação completa:', analise_checklist_raw)

    prompt_texto_corrido = (
        f"<|user|>\n"
        f"Reescreva os apontamentos de auditoria abaixo em um texto corrido (um único parágrafo fluido).\n"
        f"APONTAMENTOS:\n{analise_checklist_raw}\n\n"
        f"REGRAS ABSOLUTAS:\n"
        f"1. NÃO INVENTE, NÃO ADICIONE E NÃO CRIE nomes, cargos, documentos, datas ou valores que não estejam explicitamente no texto de APONTAMENTOS acima. Limite-se aos fatos.\n"
        f"2. Não use listas, marcadores, tópicos ou quebras de linha.\n"
        f"<|end|>\n<|assistant|>\n"
    )
    
    analise_checklist = chamar_llm_api(prompt_texto_corrido, 250, 0.0, False).strip()
    analise_checklist = analise_checklist.replace('\n', ' ')
    
    analise_checklist = re.sub(r'(?i)\bentandom\b', 'entanto, o', analise_checklist)
    analise_checklist = re.sub(r'(?i)\b(entanto|contudo|todavia)m\b', r'\1,', analise_checklist)

    corpo_resposta = (
        f"I. Este documento é de caráter de {natureza_processo}, no qual trata de: {resumo_final}\n\n"
        f"II. Durante a análise, foram identificadas as seguintes questões operacionais e legais:\n"
        f"- Análise Documental: {analise_checklist}\n"
        f"- Inconsistências Lógicas: {inconsistencias_resultado}\n"
        f"- Análise de Cálculos: {resultado_calculos}\n"
        f"- Parecer Legal: {analise_legal}\n\n"
        f"III. Em face das inconsistências e da base legal apontada, sugere-se [INSIRA AQUI A AÇÃO CORRETIVA].\n\n"
        f"IV. O setor [INSIRA AQUI] declara que [INSIRA AQUI] e encaminha esse protocolo para [INSIRA AQUI]."
    )
    
    texto_tabela_final = (
        f"**INTERESSADO**\n{meta.get('De', 'Não identificado')}\n\n"
        f"**DOCUMENTO**\n{meta.get('Documento', 'Não identificado')}\n\n"
        f"**DESTINATÁRIO**\n{meta.get('Para', 'Não identificado')}\n\n"
        f"**NATUREZA DO PROCESSO**\n{natureza_processo}\n\n"
        f"**RESUMO PRINCIPAL**\n{resumo_final}\n\n"
        f"**ANÁLISE TÉCNICA E CHECKLIST**\n{analise_checklist}\n\n"
        f"**INCONSISTÊNCIAS IDENTIFICADAS**\n{inconsistencias_resultado}\n\n"
        f"**ANÁLISE DE CÁLCULOS**\n{resultado_calculos}\n\n"
        f"**FUNDAMENTAÇÃO LEGAL**\n{analise_legal}\n\n"
        f"{resumo_eventos_str}"
    )

    return texto_tabela_final, dados_extras, caminho_events_txt, debug_texto_blocos, corpo_resposta, meta