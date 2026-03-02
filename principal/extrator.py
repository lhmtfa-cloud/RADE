import sys

def extrair_texto(pdf_path: str) -> str:
    print(f"Lendo documento de forma otimizada: {pdf_path}...")
    text = ""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text("text") + " "
        
        num_palavras = len(text.split())
        print(f"Sucesso! Extraídas aproximadamente {num_palavras} palavras do PDF.")
        
        if num_palavras < 50:
            print("[AVISO] O PDF parece estar vazio ou é feito de imagens.")
            
        return text
        
    except ImportError:
        print("\n[ERRO CRÍTICO] A biblioteca PyMuPDF não está instalada!")
        sys.exit()
    except Exception as e:
        print(f"\n[ERRO CRÍTICO] Falha ao abrir o PDF: {e}")
        sys.exit()