import re
import os
import uuid
import textwrap
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

try:
    # Ajuste para funcionar tanto no Windows quanto no Linux (Docker)
    arial_path = 'arial.ttf' 
    arial_bold_path = 'arialbd.ttf'

    if not os.path.exists(arial_path) and os.name == 'nt':
        arial_path_windows = 'C:/Windows/Fonts/arial.ttf'
        if os.path.exists(arial_path_windows):
            arial_path = arial_path_windows

    if not os.path.exists(arial_bold_path) and os.name == 'nt':
        arial_bold_path_windows = 'C:/Windows/Fonts/arialbd.ttf'
        if os.path.exists(arial_bold_path_windows):
            arial_bold_path = arial_bold_path_windows
    
    pdfmetrics.registerFont(TTFont('Arial', arial_path))
    pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
    FONT_FAMILY = 'Arial'
    FONT_FAMILY_BOLD = 'Arial-Bold'
except Exception as e:
    print(f"Alerta: Fonte Arial não encontrada. Usando Helvetica padrão. Erro: {e}")
    FONT_FAMILY = 'Helvetica'
    FONT_FAMILY_BOLD = 'Helvetica-Bold'


SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
ABSOLUTE_LOGO_PATH = os.path.join(SCRIPT_DIRECTORY, "logo.png")

class PDFGenerator:
    LOGO_FILE_PATH = ABSOLUTE_LOGO_PATH 
    LOGO_MAX_HEIGHT_MM = 15 
    HEADER_PADDING_ABOVE_LOGO_MM = 5
    HEADER_PADDING_BELOW_LOGO_MM = 5

    def __init__(self, output_dir="output_pdfs"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _add_page_header(self, canvas, doc):
        if not os.path.exists(self.LOGO_FILE_PATH): 
            return
        try:
            logo = ImageReader(self.LOGO_FILE_PATH)
            img_original_width, img_original_height = logo.getSize()
            if img_original_height == 0: return
            aspect_ratio = img_original_width / float(img_original_height)
            logo_display_height = self.LOGO_MAX_HEIGHT_MM * mm
            logo_display_width = logo_display_height * aspect_ratio
            page_width = doc.pagesize[0]
            x_centered = (page_width - logo_display_width) / 2.0
            padding_above_logo = self.HEADER_PADDING_ABOVE_LOGO_MM * mm
            y_pos = doc.pagesize[1] - padding_above_logo - logo_display_height
            
            canvas.saveState()
            canvas.drawImage(logo, x_centered, y_pos, width=logo_display_width, height=logo_display_height, mask='auto', preserveAspectRatio=True)
            canvas.restoreState()
        except Exception:
            pass

    def _prepare_data_for_table(self, result_text: str, styles: dict) -> list:
        processed_data = []
        matches = re.findall(r'\*\*(.*?)\*\*(?:\s*:)?\s*(.*?)(?=\n\*\*|$)', result_text, re.DOTALL)
        
        for key, value in matches:
            key_clean = key.replace(':', '').strip()
            
            # Divide o valor inicialmente pelas quebras de linha reais
            linhas_brutas = [linha for linha in value.split('\n') if linha.strip()]
            
            if not linhas_brutas:
                linhas_brutas = [""]
                
            # Força a divisão de linhas gigantes para evitar células maiores que a página
            linhas_valor = []
            for linha in linhas_brutas:
                # Quebra blocos contínuos a cada 400 caracteres
                pedacos = textwrap.wrap(linha, width=400)
                if pedacos:
                    linhas_valor.extend(pedacos)
                else:
                    linhas_valor.append("")

            key_paragraph = Paragraph(key_clean, styles['key_style'])
            
            primeira_linha = Paragraph(linhas_valor[0].strip(), styles['value_style'])
            processed_data.append([key_paragraph, primeira_linha])
            
            for linha in linhas_valor[1:]:
                linha_paragrafo = Paragraph(linha.strip(), styles['value_style'])
                processed_data.append(['', linha_paragrafo])

        return processed_data
    
    def create_summary_pdf(self, structured_summary: str, codigo_rastreio: str = None) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        nome_arquivo = f"resumo_{codigo_rastreio}.pdf" if codigo_rastreio else f"{uuid.uuid4().hex}.pdf"
        caminho_pdf = os.path.join(self.output_dir, nome_arquivo)
        
        doc = SimpleDocTemplate(caminho_pdf, pagesize=A4,
                                leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=30*mm, bottomMargin=20*mm) 
        
        styles = {}
        base_style = getSampleStyleSheet()['Normal']
        base_style.fontName = FONT_FAMILY
        base_style.fontSize = 11
        base_style.leading = 14

        styles['key_style'] = ParagraphStyle(name='KeyStyle', parent=base_style, fontName=FONT_FAMILY_BOLD, alignment=TA_LEFT)
        styles['value_style'] = ParagraphStyle(name='ValueStyle', parent=base_style, alignment=TA_LEFT)

        try:
            prepared_data = self._prepare_data_for_table(structured_summary, styles)
            if not prepared_data:
                # Se não houver dados no formato esperado, apenas joga o texto na tela
                p = Paragraph(structured_summary.replace('\n', '<br/>'), styles['value_style'])
                doc.build([p], onFirstPage=self._add_page_header, onLaterPages=self._add_page_header)
                return caminho_pdf

            table = Table(prepared_data, colWidths=[doc.width * 0.25, doc.width * 0.75])
            
            style_commands = [
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4*mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4*mm),
                ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ]

            for i, row_data in enumerate(prepared_data):
                if i > 0 and row_data[0] == '':
                    style_commands.append(('LINEABOVE', (0, i), (0, i), 1, colors.whitesmoke))
                    style_commands.append(('LINEABOVE', (1, i), (1, i), 1, colors.white))

            table.setStyle(TableStyle(style_commands))

            doc.build([table], onFirstPage=self._add_page_header, onLaterPages=self._add_page_header)
            return caminho_pdf
            
        except Exception as e:
            print(f"Erro ao gerar PDF: {e}")
            raise