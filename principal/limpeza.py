import fitz
import re

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