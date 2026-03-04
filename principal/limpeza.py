import fitz
import re

def extrair_texto_bruto_pdf(caminho_pdf):
    doc = fitz.open(caminho_pdf)
    texto = ""
    for pagina in doc:
        # Adiciona quebra de linha dupla para preservar separação de parágrafos e tabelas
        texto += pagina.get_text("text") + "\n\n"
    return texto

def limpar_texto_para_ia(texto):
    # Remove cabeçalhos repetitivos
    texto = re.sub(r'(?i)(ESTADO DO PARANÁ ePROTOCOLO|GOVERNO DO ESTADO|SECRETARIA DA CIÊNCIA,.*?ENSINO SUPERIOR)', '', texto, flags=re.DOTALL)
    
    # Remove rodapés longos e multilinhas (Assinaturas, validação de eProtocolo, Decretos)
    texto = re.sub(r'(?i)(Assinatura Avançada realizada por:.*?|Inserido ao protocolo.*?|Documento assinado nos termos.*?|A autenticidade deste documento pode ser validada.*?código: [a-f0-9]+)', '', texto, flags=re.DOTALL)
    
    # Remove URLs soltas e endereços físicos
    texto = re.sub(r'https?://[^\s]+', '', texto)
    texto = re.sub(r'(?i)Av\..*?Curitiba/PR.*?CEP\s*\d{5}-\d{3}', '', texto)
    
    # Remove termos isolados de burocracia
    texto = re.sub(r'(?i)\b(Folha \d+|Código TTD:.*?|Órgão Cadastro:.*?|piweb)\b', '', texto)
    
    # Normaliza múltiplos espaços e quebras de linha para um único espaço
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def extrair_metadados_protocolo(texto_bruto):
    metadados = {"Para": "N/A", "De": "N/A", "Assunto": "N/A"}
    
    m_para = re.search(r'(?i)\bPara:\s*([^\n]+)', texto_bruto)
    if m_para: 
        metadados["Para"] = m_para.group(1).strip()
        
    # Ampliado para capturar diferentes formatos de remetente no eProtocolo
    m_de = re.search(r'(?i)\b(?:De|Interessado \d?|Solicitante|Órgão ou Entidade Requisitante)[:\s]+([^\n]+)', texto_bruto)
    if m_de: 
        metadados["De"] = m_de.group(1).strip()
        
    # Adicionada a extração do Assunto/Objeto que estava ausente
    m_assunto = re.search(r'(?i)\b(?:Assunto|Objeto):\s*([^\n]+)', texto_bruto)
    if m_assunto:
        metadados["Assunto"] = m_assunto.group(1).strip()
        
    # Trunca metadados muito longos para evitar quebra de layout no PDF
    for k, v in metadados.items():
        if len(v) > 250:
            metadados[k] = v[:247] + "..."
            
    return metadados