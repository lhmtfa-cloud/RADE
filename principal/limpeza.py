import fitz
import re
import os

def extrair_timeline_protocolo(caminho_pdf):
    doc = fitz.open(caminho_pdf)
    timeline = []
    
    for num_pagina, pagina in enumerate(doc, start=1):
        texto = pagina.get_text("text")
        if not texto.strip():
            continue
            
        evento_str = None
        
        # 1. TENTA IDENTIFICAR E-MAIL
        remetente_m = re.search(r'(?i)Remetente:\s*([^\n]+)', texto)
        data_email_m = re.search(r'(?i)Data:\s*(\d{2}/\d{2}/\d{4}.*?)(?=\n|$)', texto)
        para_m = re.search(r'(?i)Para:\s*([^\n]+)', texto)
        
        if remetente_m and data_email_m:
            remetente = remetente_m.group(1).replace('"', '').strip()
            data_email = data_email_m.group(1).strip()
            para = para_m.group(1).replace('"', '').strip() if para_m else "N/A"
            evento_str = f"E-MAIL | DE: {remetente} -> PARA: {para} (Data: {data_email})"
            
        else:
            # 2. TENTA IDENTIFICAR PADRÃO OFICIAL
            regex_titulo = re.compile(r'^\s*((?:DESPACHO|INFORMAÇÃO TÉCNICA|SOLICITAÇÃO|PARECER|OFÍCIO|MEMO(?:RANDO)?|ANEXO)[^\n]{0,80})$', re.MULTILINE | re.IGNORECASE)
            titulos = [re.sub(r'\s+', ' ', m.group(1).strip()).upper() for m in regex_titulo.finditer(texto)]
            tipo_doc = titulos[0] if titulos else ""
            
            data_match = re.search(r'(?i)(?:Data(?: da Informação Técnica)?|Em|Curitiba).*?(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4})', texto)
            data_evento = data_match.group(1).strip() if data_match else "Data não identificada"
            
            de_texto = ""
            para_texto = ""
            tramite_match = re.search(r'(?i)(?:De|Origem)\s*:\s*(.*?)\n.*?(?:Para|Destino|Ao|À)\s*:\s*(.*?)(?=\n|$)', texto, re.DOTALL)
            
            if tramite_match:
                de_texto = re.sub(r'\s+', ' ', tramite_match.group(1).strip())
                para_texto = re.sub(r'\s+', ' ', tramite_match.group(2).strip())
            else:
                interessado_match = re.search(r'(?i)Interessado:\s*([^\n]+)', texto)
                if interessado_match:
                    de_texto = re.sub(r'\s+', ' ', interessado_match.group(1).strip())
            
            if tipo_doc or de_texto or para_texto:
                evento_desc = tipo_doc if tipo_doc else "MOVIMENTAÇÃO"
                detalhes_atores = ""
                if de_texto and para_texto:
                    detalhes_atores = f" | DE: {de_texto} -> PARA: {para_texto}"
                elif de_texto:
                    detalhes_atores = f" | INTERESSADO: {de_texto}"
                    
                evento_str = f"{evento_desc}{detalhes_atores} (Data: {data_evento})"

        if evento_str:
            # Armazena o número da página para que a IA possa ler o conteúdo depois
            timeline.append({
                "pagina": num_pagina,
                "evento_str": evento_str
            })

    return timeline
def gerar_arquivo_eventos(timeline, diretorio_saida="output_pdfs"):
    os.makedirs(diretorio_saida, exist_ok=True)
    caminho_txt = os.path.join(diretorio_saida, "events.txt")
    
    with open(caminho_txt, "w", encoding="utf-8") as f:
        f.write("=== TIMELINE DO PROTOCOLO ===\n\n")
        if not timeline:
            f.write("Nenhum evento de tramitação encontrado no texto pesquisável do PDF.\n")
        else:
            for evento in timeline:
                f.write(f"{evento}\n")
                
    return caminho_txt



def extrair_texto_bruto_pdf(caminho_pdf):
    doc = fitz.open(caminho_pdf)
    texto = ""
    for pagina in doc:
        texto += pagina.get_text("text") + " \n"
    return texto

def limpar_texto_para_ia(texto):
    texto = re.sub(r'(?i)(?:Assinatura|Protocolo|Inserido|Autenticidade|Local|Folha|Código TTD|piweb).*', '', texto)
    texto = re.sub(r'(?i)Av\..*?Curitiba/PR.*?CEP\s*\d{5}-\d{3}', '', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def extrair_metadados_protocolo(texto_bruto):
    metadados = {"Para": "N/A", "De": "N/A", "Documento": "N/A", "Assunto": "N/A"}
    m_para = re.search(r'(?i)(?:Para:|Ao\s+Sr\.?|À\s+Sra\.?|Ao\s+Senhor|À\s+Senhora)\s*:?\s*\n?\s*([^\n]+)', texto_bruto)
    if m_para: 
        metadados["Para"] = m_para.group(1).strip()
        
    m_de = re.search(r'(?i)\b(?:De|Interessado\s*1?):\s*([\s\S]*?)(?=\n\s*(?:Para|Assunto|Data|Referência|Protocolo|Interessado|Telefone|E-?mail):|\n\s*\n|$)', texto_bruto)
    if m_de: 
        texto_de = m_de.group(1).strip()
        texto_de = re.sub(r'\s+', ' ', texto_de)
        
        m_doc = re.search(r'(?i)\(?((?:CNPJ|CPF|RG)\s*:\s*[\d\.\-\/Xx]+)\)?', texto_de)
        if m_doc:
            metadados["Documento"] = m_doc.group(1).upper().strip()
            texto_de = re.sub(r'(?i)\(?(?:CNPJ|CPF|RG)\s*:\s*[\d\.\-\/Xx]+\)?', '', texto_de).strip()
        
        texto_de = re.sub(r'(?i)\b(?:Interessado|Telefone|E-?mail)\b.*', '', texto_de).strip()
        
        texto_de = re.sub(r'^[-–\s]+|[-–\s]+$', '', texto_de).strip()
        metadados["De"] = texto_de
            
    for k, v in metadados.items():
        if len(v) > 250:
            metadados[k] = v[:247] + "..."
            
    return metadados