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
    metadados = {"Para": "N/A", "De": "N/A", "Assunto": "N/A"}
    
    m_para = re.search(r'(?i)\bPara:\s*([^\n]+)', texto_bruto)
    if m_para: 
        metadados["Para"] = m_para.group(1).strip()
        
    m_de = re.search(r'(?i)\b(?:De|Interessado[^\n:]*):\s*([^\n]+)', texto_bruto)
    if m_de: 
        metadados["De"] = m_de.group(1).strip()
        
        
    # Trava de segurança: impede que problemas de formatação do PDF puxem textos gigantes
    for k, v in metadados.items():
        if len(v) > 250:
            metadados[k] = v[:247] + "..."
            
    return metadados
