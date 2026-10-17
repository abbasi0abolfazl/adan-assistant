"""Regenerate the committed, synthetic sample PDFs from plain JSON source."""
import json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]


def generate():
    source = json.loads((ROOT / 'data/source/documents.json').read_text())
    output = ROOT / 'data/pdfs'
    output.mkdir(parents=True, exist_ok=True)
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=11, leading=17,
                          textColor=colors.HexColor('#243244'))
    for doc in source:
        pdf = canvas.Canvas(str(output / doc['filename']), pagesize=A4, invariant=1)
        pdf.setTitle(doc['title'])
        pdf.setAuthor('Nava Demo Dataset')
        width, height = A4
        for i, page in enumerate(doc['pages'], 1):
            pdf.setFillColor(colors.HexColor('#5C6778'))
            pdf.setFont('Helvetica', 9)
            pdf.drawString(54, height-44, 'NAVA INTERNAL HANDBOOK | VERSION 1.0')
            pdf.setFillColor(colors.HexColor('#142D45'))
            pdf.setFont('Helvetica-Bold', 21)
            pdf.drawString(54, height-90, doc['title'])
            pdf.setFont('Helvetica-Bold', 14)
            pdf.drawString(54, height-132, page['heading'])
            y = height-160
            for text in page['paragraphs']:
                paragraph = Paragraph(text, body)
                _, h = paragraph.wrap(width-108, y-85)
                if y-h < 85:
                    raise RuntimeError('PDF layout overflow; shorten the source page.')
                paragraph.drawOn(pdf, 54, y-h)
                y -= h + 18
            pdf.setFillColor(colors.HexColor('#5C6778'))
            pdf.setFont('Helvetica', 9)
            pdf.drawString(54, 43, 'Synthetic demonstration data | Not a real commercial policy')
            pdf.drawRightString(width-54, 43, f'Page {i} of {len(doc["pages"])}')
            pdf.showPage()
        pdf.save()
        print(output / doc['filename'])


if __name__ == '__main__':
    generate()
