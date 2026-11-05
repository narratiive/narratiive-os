"""Approved v4 drawing geometry, adapted mechanically from approved_layout_source.py.

All text and imagery are supplied by the validated renderer. No workflow effects.
"""
from io import BytesIO
from PIL import Image
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph


def draw(c, copy, images, palette, check_paragraph, check_line):
    W, H = 595.28, 841.89
    paper, ink, green, bronze, muted, rule = (palette[k] for k in
        ('paper', 'ink', 'green', 'bronze', 'muted', 'rule'))
    def rect(x, y, w, h, col):
        c.setFillColor(HexColor(col))
        c.rect(x, H - y - h, w, h, fill=1, stroke=0)

    def line(x, y, x2, y2, col=rule, width=0.45):
        c.setStrokeColor(HexColor(col))
        c.setLineWidth(width)
        c.line(x, H - y, x2, H - y2)

    def txt(s, x, y, size=10, font='Sans', col=ink):
        c.setFillColor(HexColor(col))
        c.setFont(font, size)
        check_line(s, x, y, size, font)
        c.drawString(x, H - y - size, s)

    def para(s, x, y, w, size=10, leading=14, font='Sans', col=ink):
        st = ParagraphStyle('x', fontName=font, fontSize=size, leading=leading, textColor=HexColor(col))
        q = Paragraph(s, st)
        aw, ah = q.wrap(w, H)
        check_paragraph(s, x, y, w, ah)
        q.drawOn(c, x, H - y - ah)
        return ah

    def label(s, x, y, col=ink, size=7):
        c.setFillColor(HexColor(col))
        t = c.beginText(x, H - y - size)
        t.setFont('Bold', size)
        t.setCharSpace(1.45)
        check_line(s, x, y, size, 'Bold', tracking=1.45)
        t.textLine(s)
        c.drawText(t)
        c._code.append('0 Tc')

    def photo(name, x, y, w, h, anchor=(0.5, 0.5)):
        anchor = tuple(images[name]['anchor'])
        im = Image.open(images[name]['path'])
        iw, ih = im.size
        ratio = max(w / iw, h / ih)
        cw, ch = (w / ratio, h / ratio)
        left = (iw - cw) * anchor[0]
        top = (ih - ch) * anchor[1]
        im = im.crop((left, top, left + cw, top + ch))
        im.thumbnail((1600, 1600))
        buf = BytesIO()
        im.convert('RGB').save(buf, format='JPEG', quality=91)
        buf.seek(0)
        c.drawImage(ImageReader(buf), x, H - y - h, w, h, mask='auto')

    def base(page):
        rect(0, 0, W, H, paper)
        txt(copy['brand'], 32, 23, 19, 'Sans')
        label(copy['brand_descriptor'], 33, 49, size=6)
        label(copy['review_status'], 358, 27, size=6.5)
        txt(copy['fictional_notice'], 358, 42, 7.3, col=muted)
        line(32, 69, W - 32, 69)
        line(32, 794, W - 32, 794)
        label(copy['brand'], 32, 805, size=8)
        txt(copy['brand_footer'], 32, 819, 6.4)
        txt(f'REVIEW v4  /  {page:02d} / 02', 438, 813, 6.7, col=muted)
    P = 'partners-in-craft-existing-concept.png'
    base(1)
    label(copy['client_label'], 32, 91, bronze, 8)
    para(copy['headline'], 32, 117, 275, 38, 39, 'Serif')
    para(copy['introduction'], 33, 260, 253, 11.2, 15)
    line(33, 333, 65, 333, bronze, 1.7)
    para(copy['evidence_status'], 33, 344, 253, 7.5, 10, col=muted)
    photo(P, 310, 88, 253, 258, (0.3, 0.5))
    para(copy['hero_caption'], 310, 350, 253, 7, 9, col=muted)
    rect(32, 384, 261, 210, green)
    label(copy['opportunity_label'], 48, 400, paper)
    para(copy['opportunity_title'], 48, 421, 230, 26, 28, 'Serif', paper)
    para(copy['opportunity_body'], 48, 495, 227, 10, 14, col=paper)
    label(copy['model_status'], 313, 400, bronze, size=6.5)
    para(copy['model_central'], 313, 417, 238, 43, 45, 'Serif', bronze)
    label(copy['model_metric'], 313, 468, size=6.1)
    para(copy['model_formula'], 313, 490, 233, 9.6, 13)
    line(313, 527, 555, 527)
    para(copy['model_sensitivity'], 313, 537, 235, 12, 15, 'Serif')
    para(copy['model_limitations'], 313, 559, 235, 7.5, 10)
    label(copy['evidence_heading'], 32, 610, size=6.5)
    line(32, 627, 563, 627)
    cols = [('01', copy['evidence_1_title'], copy['evidence_1_body']), ('02', copy['evidence_2_title'], copy['evidence_2_body']), ('03', copy['evidence_3_title'], copy['evidence_3_body'])]
    for i, (num, title, body) in enumerate(cols):
        x = 32 + i * 181
        if i:
            line(x - 10, 644, x - 10, 762)
        txt(num, x, 641, 28, 'Serif', bronze)
        para(title, x, 679, 166, 13, 15, 'Serif')
        para(body, x, 711, 166, 8.5, 11.2)
    para(copy['sources'], 32, 773, 530, 7, 9, col=muted)
    c.showPage()
    base(2)
    label(copy['proposal_label'], 32, 88, size=7)
    para(copy['page_2_headline'], 32, 108, 379, 28, 30, 'Serif')
    line(423, 115, 423, 239)
    para(copy['editorial_pull_line'], 437, 124, 121, 19, 22, 'Serif')
    label(copy['editorial_attribution'], 437, 225, bronze, size=5.7)
    para(copy['scope_introduction'], 32, 211, 366, 10.5, 14)
    line(32, 252, 64, 252, bronze, 1.6)
    label(copy['outputs_heading'], 32, 274, size=7)
    line(32, 291, 563, 291)
    for i, (im, title, body, a) in enumerate([('origin-audience-editorial-v4.png', copy['output_1_title'], copy['output_1_body'], (0.25, 0.5)), ('origin-value-editorial-v4.png', copy['output_2_title'], copy['output_2_body'], (0.65, 0.75)), ('origin-activation-editorial-v4.png', copy['output_3_title'], copy['output_3_body'], (0.95, 0.6))]):
        x = 32 + i * 181
        photo(im, x, 305, 169, 84, a)
        rect(x, 305, 31, 27, green)
        txt('0' + str(i + 1), x + 7, 306, 19, 'Serif', paper)
        para(title, x, 402, 165, 16, 18, 'Serif')
        para(body, x, 462, 163, 8.7, 11.7)
        if i:
            line(x - 7, 305, x - 7, 519)
    txt(copy['image_disclosure'], 32, 527, 7, col=muted)
    photo('origin-service-editorial-v4.png', 0, 544, W, 108, (0.5, 0.5))
    c.setFillColor(Color(0.04, 0.09, 0.065, alpha=0.76))
    c.rect(0, H - 652, W, 108, fill=1, stroke=0)
    para(copy['closing_headline'], 32, 555, 535, 25, 28, 'Serif', paper)
    txt(copy['closing_subtitle'], 32, 631, 8, col=paper)
    label(copy['investment_heading'], 32, 671, size=7)
    line(32, 688, 563, 688)
    for i, (la, head, body) in enumerate([(copy['delivery_label'], copy['delivery_duration'], copy['delivery_body']), (copy['fee_label'], copy['fee_display'], copy['fee_status']), (copy['next_step_label'], copy['next_step_title'], copy['next_step_body'])]):
        x = 32 + i * 181
        if i:
            line(x - 10, 701, x - 10, 762)
        label(la, x, 699, bronze, size=5.5)
        txt(head, x, 713, 16, 'Serif')
        para(body, x, 737, 164, 8, 10.5)
    para(copy['prerequisites'], 32, 773, 531, 7, 9, col=muted)
    c.save()
