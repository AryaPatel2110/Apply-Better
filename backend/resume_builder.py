"""Local resume drafts and paginated PDF rendering."""
from io import BytesIO
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
import re
from xml.sax.saxutils import escape
from typing import Literal
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def resume_filename(name, suffix='.pdf'):
    clean=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '', name)
    clean=re.sub(r'\s+', ' ', clean).strip(' .')[:160].rstrip(' .')
    return (clean or 'resume') + suffix


def resume_disposition(name):
    return 'attachment; filename*=UTF-8\'\'' + quote(name, safe='')


class ResumeTextInput(BaseModel):
    text: str = Field(min_length=1, max_length=100000)


class Entry(BaseModel):
    title: str = Field(default='', max_length=200)
    organization: str = Field(default='', max_length=200)
    location: str = Field(default='', max_length=200)
    dates: str = Field(default='', max_length=100)
    gpa: str = Field(default='', max_length=200)
    description: str = Field(default='', max_length=10000)

SECTION_LABELS = {'summary':'SUMMARY','experience':'PROFESSIONAL EXPERIENCE','education':'EDUCATION','projects':'PROJECTS','skills':'SKILLS','volunteering':'VOLUNTEERING','achievements':'ACHIEVEMENTS','certifications':'CERTIFICATIONS','publications':'PUBLICATIONS','additional':'ADDITIONAL INFORMATION'}
SectionKey = Literal['summary','experience','education','projects','skills','volunteering','achievements','certifications','publications','additional']

class ContactLink(BaseModel):
    label: str = Field(default='', max_length=100)
    url: str = Field(default='', max_length=500)

class Resume(BaseModel):
    title: str = Field(default='Untitled resume', max_length=200)
    name: str = Field(default='', max_length=200)
    headline: str = Field(default='', max_length=200)
    headline_url: str = Field(default='', max_length=500)
    email: str = Field(default='', max_length=200)
    phone: str = Field(default='', max_length=100)
    location: str = Field(default='', max_length=200)
    website: str = Field(default='', max_length=300)
    summary: str = Field(default='', max_length=10000)
    skills: str = Field(default='', max_length=10000)
    experience: list[Entry] = Field(default_factory=list, max_length=30)
    education: list[Entry] = Field(default_factory=list, max_length=30)
    projects: list[Entry] = Field(default_factory=list, max_length=30)
    volunteering: list[Entry] = Field(default_factory=list, max_length=30)
    achievements: str = Field(default='', max_length=10000)
    certifications: str = Field(default='', max_length=10000)
    publications: str = Field(default='', max_length=10000)
    links: list[ContactLink] = Field(default_factory=list, max_length=10)
    additional: str = Field(default='', max_length=10000)
    source_filename: str = Field(default='', max_length=255)
    imported_text: str = Field(default='', max_length=100000)
    import_warnings: list[str] = Field(default_factory=list, max_length=20)
    section_order: list[SectionKey] = Field(default_factory=lambda:['summary','experience','education','projects','skills'], max_length=10)
    template: Literal['compact','classic'] = 'compact'
    font_family: Literal['Times New Roman','Arial','Georgia'] = 'Times New Roman'
    font_size: float = Field(default=10, ge=8, le=16)
    heading_size: float = Field(default=10, ge=10, le=24)
    heading_spacing: float = Field(default=2, ge=0, le=30)
    entry_spacing: float = Field(default=2, ge=0, le=24)
    bullet_spacing: float = Field(default=1, ge=0, le=16)
    line_spacing: float = Field(default=1, ge=1, le=1.8)
    section_spacing: float = Field(default=2, ge=0, le=24)
    margin: float = Field(default=36, ge=18, le=108)
    alignment: Literal['left','justify'] = 'justify'
    paper_size: Literal['Letter','A4','Legal'] = 'Letter'

    @field_validator('section_order')
    @classmethod
    def unique_sections(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Each section may appear only once.')
        return value



def render_pdf(resume):
    family = resume.font_family
    regular, bold = ('Times-Roman','Times-Bold') if family != 'Arial' else ('Helvetica','Helvetica-Bold')
    italic = 'Times-Italic' if family != 'Arial' else 'Helvetica-Oblique'
    candidates = {
        'Times New Roman': [('/System/Library/Fonts/Supplemental/Times New Roman.ttf','/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'),('/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf','/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf')],
        'Arial': [('/System/Library/Fonts/Supplemental/Arial.ttf','/System/Library/Fonts/Supplemental/Arial Bold.ttf'),('/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf')],
        'Georgia': [('/System/Library/Fonts/Supplemental/Georgia.ttf','/System/Library/Fonts/Supplemental/Georgia Bold.ttf')],
    }
    for normal_path, bold_path in candidates[family]:
        if Path(normal_path).exists() and Path(bold_path).exists():
            regular, bold = family.replace(' ','')+'Regular', family.replace(' ','')+'Bold'
            if regular not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(regular,normal_path))
                pdfmetrics.registerFont(TTFont(bold,bold_path))
            italic_path = normal_path.replace('-Regular.ttf','-Italic.ttf') if '-Regular.ttf' in normal_path else normal_path.replace('.ttf',' Italic.ttf')
            if Path(italic_path).exists():
                italic = family.replace(' ','')+'Italic'
                if italic not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(italic,italic_path))
            break
    page_size = {'Letter':(612,792),'Legal':(612,1008),'A4':(595.276,841.89)}[resume.paper_size]
    width = page_size[0] - 2 * resume.margin
    compact = resume.template == 'compact'
    font_size = resume.font_size
    body = ParagraphStyle('body',fontName=regular,fontSize=font_size,leading=font_size*resume.line_spacing,textColor=colors.black,spaceAfter=0,alignment=TA_JUSTIFY if resume.alignment=='justify' else TA_LEFT,splitLongWords=True)
    heading = ParagraphStyle('heading',parent=body,fontName=bold,fontSize=resume.heading_size,leading=resume.heading_size*resume.line_spacing,spaceBefore=resume.section_spacing,spaceAfter=0 if compact else resume.heading_spacing,keepWithNext=True,alignment=TA_LEFT,textColor=colors.black if compact else colors.HexColor('#1160b7'))
    title = ParagraphStyle('name',parent=body,fontName=bold,fontSize=font_size*1.8,leading=font_size*2,alignment=TA_CENTER,spaceAfter=3)
    centered = ParagraphStyle('contact',parent=body,alignment=TA_CENTER,fontSize=font_size,leading=font_size*1.2,spaceAfter=2)
    entry_title = ParagraphStyle('entry',parent=body,fontName=bold,alignment=TA_LEFT,keepWithNext=True)
    dates = ParagraphStyle('dates',parent=entry_title,alignment=TA_RIGHT)
    bullet = ParagraphStyle('bullet',parent=body,leftIndent=12,firstLineIndent=0,bulletIndent=3,bulletFontName=regular,bulletFontSize=font_size,spaceAfter=resume.bullet_spacing)
    education_bullet = ParagraphStyle('education-bullet',parent=bullet,fontName=italic,spaceAfter=0)
    last_bullet = ParagraphStyle('last-bullet',parent=bullet,spaceAfter=0)
    education_dates = ParagraphStyle('education-dates',parent=dates,fontName=regular)
    safe=lambda text:escape(text).replace('\n','<br/>')
    story=[Paragraph(safe(resume.name or 'Your name'),title)]
    def web_url(value):
        value=value.strip()
        if not value: return ''
        if not re.match(r'^[a-z][a-z0-9+.-]*:',value,re.I): value='https://'+value
        return value if re.match(r'^https?://[^/\s]+',value,re.I) else ''
    def linked_text(text,url):
        valid=web_url(url)
        if not valid: return safe(text)
        href=escape(valid,{chr(34):'&quot;'})
        return f'<link href="{href}" color="#1160b7">{safe(text)}</link>'

    contact=[]
    for value in [resume.phone,resume.email,resume.location]:
        if not value: continue
        if value==resume.email:
            contact.append(f'<link href="mailto:{escape(value, {chr(34): "&quot;"})}" color="#1160b7">{safe(value)}</link>')
        elif value==resume.website: contact.append(linked_text(value,value))
        else: contact.append(safe(value))
    for link in resume.links[:3]:
        if not link.label: continue
        contact.append(linked_text(link.label,link.url))
    if contact: story.append(Paragraph(' | '.join(contact),centered))
    for field in dict.fromkeys(resume.section_order):
        value=getattr(resume,field)
        entries=[entry for entry in value if any(entry.model_dump().values())] if isinstance(value,list) else None
        if not entries and not (isinstance(value,str) and value.strip()): continue
        story.append(Paragraph(SECTION_LABELS[field],heading))
        if compact:
            rule=HRFlowable(width='100%',thickness=.4,color=colors.black,spaceAfter=resume.heading_spacing)
            rule.keepWithNext=True
            story.append(rule)
        if entries is None:
            if field == 'skills':
                lines=[]
                for line in value.split('\n'):
                    label,colon,details=line.partition(':')
                    lines.append(f'<b>{safe(label)}</b>:{safe(details)}' if colon and label else safe(line))
                story.append(Paragraph('<br/>'.join(lines),body))
            else:
                story.append(Paragraph(safe(value),body))
            continue
        for entry in entries:
            if field == 'education':
                school=f'<b>{safe(entry.organization)}</b>'
                if entry.location: school+=', '+safe(entry.location)
                degree=('•  '+safe(entry.title)) if entry.title.strip() else ''
                gpa=('GPA: '+safe(entry.gpa)) if entry.gpa else ''
                rows=[[Paragraph(school,body),Paragraph(safe(entry.dates),education_dates)],
                      [Paragraph(degree,education_bullet),Paragraph(gpa,education_dates)]]
                row=Table(rows,colWidths=[width*.76,width*.24])
                row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
                story.append(row)
                for line in entry.description.splitlines():
                    if line.strip(): story.append(Paragraph(safe(line.lstrip('•- ').strip()),education_bullet,bulletText='•'))
                story.append(Spacer(1,resume.entry_spacing))
                continue
            if field == 'education':
                first = f'<b>{safe(entry.organization)}</b>'
                if entry.location: first += ', '+safe(entry.location)
            else:
                first = safe((' | ' if field=='projects' else ', ').join(v for v in [entry.title,entry.organization] if v))
                if entry.location: first += ' | '+safe(entry.location)
            if first or entry.dates or (field=='education' and entry.gpa):
                right_text = safe(entry.dates)
                if field=='education' and entry.gpa:
                    right_text += ('<br/>' if right_text else '')+'GPA: '+safe(entry.gpa)
                row=Table([[Paragraph(first,body if field=='education' else entry_title),Paragraph(right_text,education_dates if field=='education' else dates)]],colWidths=[width*.76,width*.24] if right_text else [width,0])
                row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
                row.keepWithNext=bool(entry.description.strip() or (field=='education' and entry.title.strip()))
                story.append(row)
            if field=='education' and entry.title.strip():
                story.append(Paragraph(safe(entry.title),education_bullet,bulletText='•'))
            bullet_lines=[line for line in entry.description.splitlines() if line.strip()]
            for index,line in enumerate(bullet_lines):
                style=last_bullet if index==len(bullet_lines)-1 else bullet
                story.append(Paragraph(safe(line.lstrip('•- ').strip()),style,bulletText='•'))
            story.append(Spacer(1,resume.entry_spacing))
    output=BytesIO()
    doc=BaseDocTemplate(output,pagesize=page_size,rightMargin=resume.margin,leftMargin=resume.margin,topMargin=resume.margin,bottomMargin=resume.margin,title=resume.title,author=resume.name)
    frame=Frame(doc.leftMargin,doc.bottomMargin,doc.width,doc.height,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='resume',frames=[frame]))
    doc.build(story)
    return output.getvalue()


def router_for(data_dir,lock):
    router=APIRouter(prefix='/api/resume-drafts',tags=['Resume Builder'])
    directory=data_dir/'resume_drafts'
    directory.mkdir(parents=True,exist_ok=True)
    def path_for(identifier):
        if not re.fullmatch(r'[a-f0-9]{32}',identifier): raise HTTPException(404,'Resume draft not found.')
        return directory/f'{identifier}.json'
    def store(identifier,resume):
        record={**resume.model_dump(),'id':identifier,'updated_at':datetime.now(timezone.utc).isoformat()}
        path=path_for(identifier)
        with lock:
            temp=path.with_suffix('.tmp')
            with temp.open('w',encoding='utf-8') as file:
                json.dump(record,file,ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            temp.replace(path)
        return record
    @router.get('')
    def list_drafts():
        with lock:
            drafts=[json.loads(path.read_text(encoding='utf-8')) for path in directory.glob('*.json')]
        return sorted(drafts,key=lambda draft:draft['updated_at'],reverse=True)
    @router.post('',status_code=201)
    def create_draft(resume:Resume):return store(uuid4().hex,resume)
    @router.post('/parse-text')
    def parse_text(payload: ResumeTextInput):
        from backend.resume_import import parse_resume, web_links
        text=payload.text.strip()
        if not text:
            raise HTTPException(400, 'Paste your resume text first.')
        text=re.sub(r'(?m)^\s*#{1,6}\s+', '', text).replace('**','')
        urls=re.findall(r'(?:https?://|www\.)[^\s|<>]+|(?:linkedin\.com|github\.com)/[^\s|<>]+|(?<=Portfolio: )[^\s|<>]+',text,re.I)
        values=parse_resume(text,web_links(urls),"pasted-resume.txt",pasted=True)
        if values['name']=='pasted-resume': values['name']=''
        return Resume(**values).model_dump()

    @router.post('/import',status_code=201)
    def import_resume(file:UploadFile=File(...)):
        from backend.resume_import import extract_document,parse_resume
        filename=Path((file.filename or 'resume').replace('\\','/')).name
        content=file.file.read(10*1024*1024+1)
        if not content or len(content)>10*1024*1024:
            raise HTTPException(400,'Upload a nonempty resume up to 10 MB.')
        text,links=extract_document(content,filename)
        values=parse_resume(text,links,filename)
        try:
            resume=Resume(**values)
        except ValueError as exc:
            raise HTTPException(400,'The resume contains sections that are too large to import. Upload a shorter version.') from exc
        return store(uuid4().hex,resume)
    @router.delete('/{identifier}',status_code=204)
    def delete_draft(identifier:str):
        path=path_for(identifier)
        with lock:
            if not path.is_file():raise HTTPException(404,'Resume draft not found.')
            path.unlink()
        return Response(status_code=204)
    @router.put('/{identifier}')
    def update_draft(identifier:str,resume:Resume):
        if not path_for(identifier).is_file():raise HTTPException(404,'Resume draft not found.')
        return store(identifier,resume)
    @router.post('/pdf')
    def pdf(resume:Resume):
        name=resume_filename(resume.name)
        return Response(render_pdf(resume),media_type='application/pdf',headers={'Content-Disposition':resume_disposition(name)})
    return router
