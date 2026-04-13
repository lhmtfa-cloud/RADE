import re
import os
import uuid
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

try:
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
except Exception:
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

    def _prepare_data_for_table(self, result_text: str, styles: dict) -> tuple:
        result_text = re.sub(r'(?i)\*?\*?\s*DETALHAMENTO POR BLOCOS\s*\*?\*?[\s:\-]*', '', result_text).strip()
        
        pattern = re.compile(
            r'(?:^|\n)\s*\*\*\s*(INTERESSADO|DOCUMENTO|DESTINATÁRIO|RESUMO PRINCIPAL|ANÁLISE DE CÁLCULOS|INCONSISTÊNCIAS IDENTIFICADAS|Pág.*?\|\s*Movimentação.*?)\s*:?\s*\*\*(?:\s*:)?',
            re.IGNORECASE
        )
        
        parts = pattern.split(result_text)
        
        processed_data = []
        block_boundaries = []
        current_row = 0
        
        for i in range(1, len(parts), 2):
            key_clean = parts[i].strip()
            value = parts[i+1].strip() if i+1 < len(parts) else ""
            
            value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            value = value.replace('**', '')
            
            value = re.sub(r'\n+(?=\s*-)', '\n\n', value)
            
            value_html = value.replace('\n', '<br/>')

            key_paragraph = Paragraph(key_clean, styles['key_style'])
            value_paragraph = Paragraph(value_html, styles['value_style'])
            
            processed_data.append([key_paragraph, value_paragraph])
            block_boundaries.append((current_row, current_row))
            current_row += 1

        return processed_data, block_boundaries
    
    def create_summary_pdf(self, structured_summary: str, codigo_rastreio: str = None, username: str = "", corpo_resposta: str = "", meta: dict = None) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        nome_arquivo = f"resumo_{codigo_rastreio}.pdf" if codigo_rastreio else f"{uuid.uuid4().hex}.pdf"
        caminho_pdf = os.path.join(self.output_dir, nome_arquivo)
        
        doc = SimpleDocTemplate(caminho_pdf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=30*mm, bottomMargin=20*mm) 
        
        styles = {}
        base_style = getSampleStyleSheet()['Normal']
        base_style.fontName = FONT_FAMILY
        base_style.fontSize = 11
        base_style.leading = 14

        styles['key_style'] = ParagraphStyle(name='KeyStyle', parent=base_style, fontName=FONT_FAMILY_BOLD, alignment=TA_LEFT)
        styles['value_style'] = ParagraphStyle(name='ValueStyle', parent=base_style, alignment=TA_LEFT)
        
        memo_style = ParagraphStyle(name='MemoStyle', parent=base_style, alignment=TA_LEFT, spaceAfter=12)
        memo_indent = ParagraphStyle(name='MemoIndent', parent=base_style, alignment=TA_JUSTIFY, spaceAfter=12, leftIndent=28, bulletIndent=0)
        memo_center = ParagraphStyle(name='MemoCenter', parent=base_style, alignment=TA_CENTER, spaceAfter=5)
        memo_center_bold = ParagraphStyle(name='MemoCenterBold', parent=base_style, fontName=FONT_FAMILY_BOLD, alignment=TA_CENTER, spaceAfter=2)

        prepared_data, block_boundaries = self._prepare_data_for_table(structured_summary, styles)
        
        elements = []
        if prepared_data:
            table = Table(prepared_data, colWidths=[doc.width * 0.30, doc.width * 0.70])
            style_commands = [
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4*mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4*mm),
                ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
                ('BOX', (0, 0), (-1, -1), 1, colors.grey),
                ('LINEAFTER', (0, 0), (0, -1), 1, colors.grey),
            ]
            for start_row, end_row in block_boundaries:
                if end_row < len(prepared_data) - 1:
                    style_commands.append(('LINEBELOW', (0, end_row), (-1, end_row), 1, colors.grey))
            table.setStyle(TableStyle(style_commands))
            elements.append(table)
        else:
            elements.append(Paragraph(structured_summary.replace('\n', '<br/>'), styles['value_style']))

        elements.append(PageBreak())
        
        ano_atual = datetime.now().year
        num_memo = codigo_rastreio[:4].upper() if codigo_rastreio else "0000"
        elements.append(Paragraph(f"Memo n.º {num_memo}/{ano_atual}/SETI-<b>[INSIRA AQUI]</b>", memo_style))
        
        para_nome = "<b>[INSIRA AQUI]</b>"
        
        assunto_final = meta.get('Assunto_IA', 'Documento Oficial').strip()
            
        elements.append(Paragraph(f"Para: {para_nome}", memo_style))
        elements.append(Paragraph(f"Assunto: {assunto_final}", memo_style))
        elements.append(Spacer(1, 5*mm))
        
        elements.append(Paragraph("Senhor(a),", memo_style))
        
        if corpo_resposta:
            corpo_formatado = corpo_resposta.replace('[INSERIR AQUI]', '<b>[INSIRA AQUI]</b>').replace('[INSIRA AQUI]', '<b>[INSIRA AQUI]</b>')
            for p in corpo_formatado.split('\n'):
                if p.strip():
                    match = re.match(r'^(I|II|III)\.\s+(.*)', p.strip())
                    if match:
                        p_text = f"<bullet>{match.group(1)}.</bullet>{match.group(2)}"
                        elements.append(Paragraph(p_text, memo_indent))
                    else:
                        elements.append(Paragraph(p.strip(), memo_indent))
        
        elements.append(Spacer(1, 15*mm))
        
        meses = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        hoje = datetime.now()
        data_str = f"Curitiba, {hoje.day} de {meses[hoje.month]} de {hoje.year}."
        
        elements.append(Paragraph(data_str, memo_center))
        elements.append(Spacer(1, 20*mm))
        
        elements.append(Paragraph(username.upper() if username else "USUÁRIO", memo_center_bold))
        elements.append(Paragraph("<b>[INSIRA AQUI]</b>/Seti", memo_center))

        doc.build(elements, onFirstPage=self._add_page_header, onLaterPages=self._add_page_header)
        return caminho_pdf