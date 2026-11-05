from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image
from io import BytesIO
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'pdf/Origin-Coffee-Fieldwork-internal-review-v4.pdf'
for n,f in [('Serif','Baskerville.ttc'),('Sans','Arial.ttf'),('Bold','Arial Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(n,'/System/Library/Fonts/Supplemental/'+f,subfontIndex=0))
W,H=595.28,841.89
paper='#F4F0E7'; ink='#131C18'; green='#19372D'; bronze='#A66B27'; muted='#60655D'; rule='#C4C5BA'
c=canvas.Canvas(str(OUT),pagesize=(W,H))
c.setTitle('Origin Coffee | Fieldwork | Fictional internal review v4')
c.setAuthor('Narratiive - internal review candidate')
def rect(x,y,w,h,col):
    c.setFillColor(HexColor(col)); c.rect(x,H-y-h,w,h,fill=1,stroke=0)
def line(x,y,x2,y2,col=rule,width=.45):
    c.setStrokeColor(HexColor(col)); c.setLineWidth(width);c.line(x,H-y,x2,H-y2)
def txt(s,x,y,size=10,font='Sans',col=ink):
    c.setFillColor(HexColor(col));c.setFont(font,size); c.drawString(x,H-y-size,s)
def para(s,x,y,w,size=10,leading=14,font='Sans',col=ink):
    st=ParagraphStyle('x',fontName=font,fontSize=size,leading=leading,textColor=HexColor(col))
    q=Paragraph(s,st); aw,ah=q.wrap(w,H);q.drawOn(c,x,H-y-ah);return ah

def label(s,x,y,col=ink,size=7):
    c.setFillColor(HexColor(col)); t=c.beginText(x,H-y-size);t.setFont('Bold',size);t.setCharSpace(1.45);t.textLine(s);c.drawText(t); c._code.append("0 Tc")
def photo(name,x,y,w,h,anchor=(.5,.5)):
    im=Image.open(ROOT/'assets'/name); iw,ih=im.size;ratio=max(w/iw,h/ih);cw,ch=w/ratio,h/ratio
    left=(iw-cw)*anchor[0];top=(ih-ch)*anchor[1]
    im=im.crop((left,top,left+cw,top+ch))
    im.thumbnail((1600,1600)); buf=BytesIO(); im.convert("RGB").save(buf,format="JPEG",quality=91); buf.seek(0)
    c.drawImage(ImageReader(buf),x,H-y-h,w,h,mask='auto')
def base(page):
    rect(0,0,W,H,paper)
    txt('NARRATIIVE',32,23,19,'Sans');label('STRATEGY / CREATIVE / GROWTH',33,49,size=6)
    label('FICTIONAL / INTERNAL REVIEW',358,27,size=6.5)
    txt('TEST / Origin has not engaged Narratiive.',358,42,7.3,col=muted)
    line(32,69,W-32,69)
    line(32,794,W-32,794)
    label('NARRATIIVE',32,805,size=8)
    txt('THE GROWTH AGENCY FOR AMBITIOUS BRANDS',32,819,6.4)
    txt(f'REVIEW v4  /  {page:02d} / 02',438,813,6.7,col=muted)
D='daily-discovery-existing-concept.png';P='partners-in-craft-existing-concept.png'
base(1)
label('ORIGIN COFFEE',32,91,bronze,8)
para('Sell the<br/>confidence<br/>behind the coffee.',32,117,275,38,39,'Serif')
para('Win established hospitality businesses by making Origin’s expertise a compelling reason to choose their next coffee partner.',33,260,253,11.2,15)
line(33,333,65,333,bronze,1.7)
para('A marketing hypothesis grounded in public evidence. Fictional test; no discovery statements or Origin financial data.',33,344,253,7.5,10,col=muted)
photo(P,310,88,253,258,(.3,.5))
para('Existing concept illustration; not Origin photography or staff.',310,350,253,7,9,col=muted)
rect(32,384,261,210,green)
label('THE MARKETING OPPORTUNITY',48,400,paper)
para('Win the operators<br/>already serving.',48,421,230,26,28,'Serif',paper)
para('Target established cafés and boutique hotel groups ready to upgrade. Turn Origin’s training, equipment and operational expertise into persuasive proof of a more confident coffee service—and a credible reason to switch.',48,495,227,10,14,col=paper)
label('ILLUSTRATIVE / ASSUMED DATA',313,400,bronze,size=6.5)
para('+£119k',313,417,238,43,45,'Serif',bronze)
label('INCREMENTAL YEAR-ONE REVENUE',313,468,size=6.1)
para('12 additional accounts × £22,000 net annual account revenue × 45% year-one ramp.',313,490,233,9.6,13)
line(313,527,555,527)
para('Sensitivity: ~£62k to ~£194k',313,537,235,12,15,'Serif')
para('8–16 accounts; 35–55% ramp. All assumed, not Origin results or a forecast. Revenue, not profit; implementation costs separate. No guaranteed return.',313,559,235,7.5,10)
label('A LARGE MARKET. A MORE PRECISE WAY TO WIN.',32,610,size=6.5)
line(32,627,563,627)
cols=[('01','A £6.8bn battleground','UK branded coffee shops recorded £6.8bn in sales and 12,313 outlets in 2025. The opportunity deserves a sharper audience choice than “anyone serving coffee”. [1]'),('02','Look beyond new openings','Meaningful Vision reports opening growth of 0.8% in H1 2026, down from 4.5% in H1 2024. Established operators merit attention alongside start-ups. [2]'),('03','Make support mean more','Origin offers training, equipment and support. Union and Extract do too. The marketing task: make the value to a specific operator more compelling and demonstrable. [3]')]
for i,(num,title,body) in enumerate(cols):
    x=32+i*181
    if i:line(x-10,644,x-10,762)
    txt(num,x,641,28,'Serif',bronze)
    para(title,x,679,166,13,15,'Serif')
    para(body,x,711,166,8.5,11.2)
para('[1] WCP / Retail Gazette, 2026: 2025 branded market. [2] Meaningful Vision, 10 Sep 2026: separate series, not directly comparable. [3] Official Origin / Union wholesale and Extract FAQs, accessed 4 Nov 2026. Market signals do not establish competitive advantage.',32,773,530,7,9,col=muted)
c.showPage()
base(2)
label('ORIGIN COFFEE / FIELDWORK PROPOSAL',32,88,size=7)
para('Find the customers.<br/>Build the advantage.<br/>Show the way to growth.',32,108,379,28,30,'Serif')
line(423,115,423,239)
para('Expertise that<br/>earns a place<br/>behind the bar.',437,124,121,19,22,'Serif')
label('NARRATIIVE VIEW',437,225,bronze,size=5.7)
para('A focused wholesale growth strategy: choose the right operators, give them a stronger reason to switch, and build the marketing to reach them.',32,211,366,10.5,14)
line(32,252,64,252,bronze,1.6)
label('THREE OUTPUTS. ONE WHOLESALE GROWTH STRATEGY.',32,274,size=7)
line(32,291,563,291)
for i,(im,title,body,a) in enumerate([
    ('origin-audience-editorial-v4.png','Find the growth audience','Prioritise established cafés and boutique hotel groups: buyer needs, supplier-switching triggers and reachable account opportunity. Know who to pursue first and why.',(.25,.5)),
    ('origin-value-editorial-v4.png','Make Origin the compelling choice','Define competitive whitespace, positioning, message strategy, proof and creative direction. Make Origin’s practical expertise matter to the operators it can serve best.',(.65,.75)),
    ('origin-activation-editorial-v4.png','Build the route to market','Set channel, content and partnership strategy, investment priorities and a measurable 90-day growth plan to turn the proposition into qualified wholesale demand.',(.95,.6))]):
    x=32+i*181
    photo(im,x,305,169,84,a)
    rect(x,305,31,27,green);txt('0'+str(i+1),x+7,306,19,'Serif',paper)
    para(title,x,402,165,16,18,'Serif')
    para(body,x,462,163,8.7,11.7)
    if i:line(x-7,305,x-7,519)
txt('Images: AI-generated editorial illustrations, not Origin assets or evidence.',32,527,7,col=muted)
photo('origin-service-editorial-v4.png',0,544,W,108,(.5,.5))
c.setFillColor(Color(0.04,.09,.065,alpha=.76));c.rect(0,H-652,W,108,fill=1,stroke=0)
para('Find the opportunity.<br/>Turn evidence into marketing that works.',32,555,535,25,28,'Serif',paper)
txt('A clear audience. A compelling proposition. A practical route to growth.',32,631,8,col=paper)
label('THE INVESTMENT',32,671,size=7)
line(32,688,563,688)
for i,(la,head,body) in enumerate([
    ('DELIVERY','7 working days','From agreed inputs and completed prerequisites. Includes strategy presentation and evidence/model handoff.'),
    ('INVESTMENT','£9,800 ex VAT','Internal proposal amount pending Matt’s approval. Not an authorised quotation.'),
    ('NEXT STEP',"Let’s get started",'Agree the scope, complete the inputs and commission Fieldwork. We’ll confirm the start and delivery dates.')]):
    x=32+i*181
    if i:line(x-10,701,x-10,762)
    label(la,x,699,bronze,size=5.5)
    txt(head,x,713,16,'Serif')
    para(body,x,737,164,8,10.5)
para('Start: accepted scope/terms, agreed initial payment, required data, permissions and stakeholder access. UK wholesale strategy; excludes primary field research, production, implementation and media spend. Fictional draft; no guaranteed revenue outcome.',32,773,531,7,9,col=muted)
c.save()
print(OUT)
