"""Local-only PDF/DOCX extraction and conservative resume section parsing."""
from io import BytesIO
from pathlib import Path
import re
import textwrap
import zipfile
from xml.etree import ElementTree as ET
from fastapi import HTTPException
from pypdf import PdfReader

ALIASES={
 'summary':'summary','professional summary':'summary','profile':'summary','objective':'summary','about me':'summary','career summary':'summary',
 'experience':'experience','professional experience':'experience','work experience':'experience','employment history':'experience','employment':'experience','work history':'experience',
 'education':'education','academic background':'education','qualifications':'education',
 'projects':'projects','personal projects':'projects','selected projects':'projects','academic projects':'projects',
 'skills':'skills','technical skills':'skills','core competencies':'skills','technical expertise':'skills','skills & expertise':'skills',
 'volunteering':'volunteering','volunteer experience':'volunteering','volunteer work':'volunteering',
 'achievements':'achievements','honors and awards':'achievements','awards':'achievements',
 'certifications':'certifications','certificates':'certifications','licenses and certifications':'certifications',
 'publications':'publications','publication':'publications','additional information':'additional',
}
MONTH=r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE=r'(?:(?:'+MONTH+r'\.?\s+)|(?:\d{1,2}/))?(?:19|20)\d{2}'
DATES=re.compile(r'\b((?:Expected\s+(?:Graduation\s+)?)?'+DATE+r'(?:\s*[-–—]\s*(?:'+DATE+r'|Present|Current|Now))?)\s*$',re.I)
SCHOOL=re.compile(r'\b(?:university|institute|college|school|polytechnic|academy)\b',re.I)
DEGREE=re.compile(r'\b(?:bachelor|master|doctor|ph\.?d|b\.?sc|m\.?sc|b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?a\.?|mba|degree|diploma|associate)\b',re.I)
BULLET=re.compile(r'^\s*[•●▪◦‣\uf0b7\u2022\-*]\s*')

def web_links(values):
    result=[]
    for value in values:
        value=value.strip().rstrip('.,;)')
        if not re.match(r'^https?://',value,re.I):value='https://'+value
        if not re.match(r'^https?://[^\s/]+',value,re.I):continue
        label='linkedin' if 'linkedin.com' in value.lower() else 'github' if 'github.com' in value.lower() else 'portfolio'
        if label not in {link['label'] for link in result}:result.append({'label':label,'url':value[:500]})
    return sorted(result,key=lambda link:['linkedin','github','portfolio'].index(link['label']))[:3]

def extract_document(content,filename):
    suffix=Path(filename).suffix.lower()
    urls=[]
    try:
        if suffix=='.pdf':
            if not content.startswith(b'%PDF-'):raise HTTPException(400,'This file is not a valid PDF.')
            reader=PdfReader(BytesIO(content))
            if reader.is_encrypted and not reader.decrypt(''):raise HTTPException(400,'Upload an unlocked PDF; this resume is password-protected.')
            if len(reader.pages)>30:raise HTTPException(400,'Please upload a resume with 30 pages or fewer.')
            pages=[]
            for page in reader.pages:
                pages.append(page.extract_text(extraction_mode='layout') or '')
                for annotation in page.get('/Annots',[]):
                    action=annotation.get_object().get('/A',{})
                    uri=action.get('/URI','')
                    if str(uri).lower().startswith(('https://','http://')):urls.append(str(uri))
            text='\n'.join(pages)
        elif suffix=='.docx':
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist())>30*1024*1024:raise HTTPException(400,'The Word document is too large when expanded.')
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                parts=[]
                names=['word/document.xml']+[name for name in archive.namelist() if re.match(r'word/(header|footer)\d+\.xml$',name)]
                for name in names:
                    root=ET.fromstring(archive.read(name))
                    for paragraph in root.findall('.//w:p',ns):
                        tokens=[]
                        for node in paragraph.iter():
                            tag=node.tag.rsplit('}',1)[-1]
                            if tag=='t':tokens.append(node.text or '')
                            elif tag=='tab':tokens.append('    ')
                            elif tag in {'br','cr'}:tokens.append('\n')
                        line=''.join(tokens)
                        if paragraph.find('w:pPr/w:numPr',ns) is not None:line='• '+line
                        if line.strip():parts.append(line)
                text='\n'.join(parts)
                for name in archive.namelist():
                    if name.endswith('.rels'):
                        root=ET.fromstring(archive.read(name))
                        for relation in root:
                            target=relation.attrib.get('Target','')
                            if relation.attrib.get('Type','').endswith('/hyperlink') and target.startswith(('https://','http://')):urls.append(target)
        else:raise HTTPException(400,'Upload a PDF or DOCX resume. Convert older .doc files to .docx first.')
    except HTTPException:raise
    except Exception as exc:raise HTTPException(400,'Unable to read this file. Try exporting your resume as a new PDF or DOCX.') from exc
    text=text.replace('\x00','').replace('\r','').strip()
    if len(re.sub(r'\s','',text))<30:raise HTTPException(400,'No readable resume text was found. Scanned/image-only PDFs need OCR first; upload a text-based PDF or DOCX.')
    if len(text)>100000:raise HTTPException(400,'This document contains too much text. Upload a shorter resume.')
    urls+=re.findall(r'(?:https?://|www\.)[^\s|<>]+',text)
    return text,web_links(urls)

def join_lines(lines):
    result=''
    for line in lines:
        line=line.strip()
        if not line:continue
        result+=('' if not result or result.endswith('-') else ' ')+line
    return result

def split_date(line):
    match=DATES.search(line.strip())
    if not match:return line.strip(),''
    return line[:match.start()].strip(' |,\t'),match.group(1)

def parse_header(line,kind):
    row=dict(title='',organization='',location='',dates='',description='',gpa='')
    if kind=='education':
        gpa=re.search(r'\bGPA\s*:?\s*([0-9.]+\s*(?:/\s*[0-9.]+)?)',line,re.I)
        if gpa:
            row['gpa']=gpa.group(1)
            line=(line[:gpa.start()]+line[gpa.end():]).strip(' ·|,')
    main,row['dates']=split_date(line)
    parts=[part.strip() for part in re.split(r'\s*\|\s*',main) if part.strip()]
    if len(parts)>1:
        if kind=='education':
            row['organization']=parts[0]
            row['title']=parts[1]
            row['location']=' | '.join(parts[2:])
        elif kind=='projects':
            row['title']=parts[0]
            row['organization']=' | '.join(parts[1:])
        else:
            # Older imported resumes use "Title, Company | Location".
            if len(parts)==2 and ', ' in parts[0]:
                row['title'],row['organization']=parts[0].split(', ',1)
                row['location']=parts[1]
            else:
                row['title']=parts[0]
                row['organization']=parts[1]
                row['location']=' | '.join(parts[2:])
        return row
    if kind=='education':
        parts=re.split(r'\s+[-–—]\s+',main,maxsplit=1)
        if len(parts)>1 and DEGREE.search(parts[1]):row['organization'],row['title']=parts
        elif DEGREE.search(main) and not SCHOOL.search(main):row['title']=main
        else:
            parts=main.split(', ',1)
            row['organization']=parts[0]
            if len(parts)>1:row['location']=parts[1]
    elif kind=='projects':row['title']=main
    else:
        parts=main.split(', ',1)
        row['title']=parts[0]
        if len(parts)>1:row['organization']=parts[1]
    return row


def parse_pasted_entries(lines,kind):
    """Blank-separated paragraphs are bullets; only structural lines start entries."""
    rows=[];current=None;paragraph=[];bullets=[]
    def flush_paragraph():
        if paragraph:
            bullets.append(join_lines(paragraph));paragraph.clear()
    def finish():
        flush_paragraph()
        if current is not None:
            current['description']='\n'.join(bullets)
            rows.append(current)
        bullets.clear()
    for raw in lines:
        line=raw.strip()
        if not line:
            flush_paragraph();continue
        marked=bool(BULLET.match(raw))
        _,date=split_date(line)
        if kind=='education':
            header=not marked and bool(SCHOOL.search(line)) and (bool(DEGREE.search(line)) or len(line)<150)
        elif kind=='projects':
            header=not marked and (' | ' in line or (len(line)<90 and not re.search(r'[.!?]$',line) and not paragraph))
        else:
            header=not marked and bool(date) and ('|' in line or len(line)<180)
        if header or current is None:
            finish();current=parse_header(line,kind);continue
        if kind=='education' and not current['title'] and DEGREE.search(line):
            degree,dates=split_date(BULLET.sub('',line))
            current['title']=degree
            if dates:current['dates']=dates
        elif kind=='education' and re.match(r'^GPA\b',line,re.I):
            current['gpa']=re.sub(r'^GPA\s*:?\s*','',line,flags=re.I)
        else:
            if marked:flush_paragraph()
            paragraph.append(BULLET.sub('',raw).strip() if marked else line)
    finish()
    return rows


def parse_entries(lines,kind):
    lines=textwrap.dedent('\n'.join(lines)).splitlines()
    rows=[];current=None;description=[];last_bullet=False
    def finish():
        if current is not None:
            current['description']='\n'.join(description).strip()
            rows.append(current)
    for raw in lines:
        line=raw.strip()
        if not line:continue
        is_bullet=bool(BULLET.match(raw))
        _,date=split_date(line)
        school=kind=='education' and bool(SCHOOL.search(line)) and len(line)<250
        project=kind=='projects' and (' | ' in line or (not raw[:1].isspace() and len(line)<180 and not is_bullet))
        new_header=not is_bullet and (bool(date) or school or project)
        # A wrapped bullet can end in a year; indentation keeps it in its current bullet.
        if current and last_bullet and raw.startswith('  ') and not school:new_header=False
        if current is None or new_header:
            finish();current=parse_header(line,kind);description=[];last_bullet=False;continue
        if is_bullet:
            value=BULLET.sub('',raw).strip()
            if kind=='education' and not current['title'] and DEGREE.search(value):current['title']=value
            else:description.append(value)
            last_bullet=True
        elif kind=='education' and DEGREE.search(line) and not current['title']:
            current['title']=line;last_bullet=False
        elif kind=='education' and re.match(r'^GPA\b',line,re.I):
            current['gpa']=re.sub(r'^GPA\s*:?\s*','',line,flags=re.I)
        elif last_bullet and description:
            description[-1]+=('' if description[-1].endswith('-') else ' ')+line
        elif not current['organization'] and len(line)<180 and kind!='education':
            current['organization']=line
        else:description.append(line)
    finish()
    return rows

def parse_resume(text,links,filename,*,pasted=False):
    sections={};preamble=[];active=None;order=[]
    for raw in text.splitlines():
        normalized=re.sub(r'\s+',' ',raw.strip()).strip(' :_-–—').lower()
        key=ALIASES.get(normalized)
        if key:
            active=key
            if key not in order:order.append(key)
            sections.setdefault(key,[])
        elif active:sections[active].append(raw)
        elif raw.strip():preamble.append(raw)
    contact=' | '.join(preamble[:6])
    emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',contact)
    phone=re.search(r'(?:\+\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}',contact)
    name=next((line.strip() for line in preamble[:4] if not re.search(r'[@|\d]|https?://|linkedin|github',line,re.I)),Path(filename).stem)
    location=''
    for part in re.split(r'\s*[|]\s*',contact):
        if re.search(r'\b[A-Za-z .-]+,\s*[A-Z]{2}\b',part) and not re.search(r'[@/]|https',part):location=part.strip();break
    result=dict(title=Path(filename).stem+' — imported',name=name[:200],email=emails[0][:200] if emails else '',phone=phone.group().strip()[:100] if phone else '',location=location[:200],links=links,source_filename=Path(filename).name,imported_text=text,section_order=order or ['summary'])
    overflow=[]
    for key,lines in sections.items():
        if key in {'experience','education','projects','volunteering'}:
            parsed=parse_pasted_entries(lines,key) if pasted else parse_entries(lines,key)
            for row in parsed:
                for field in ['title','organization','location','gpa']:
                    if len(row[field])>200:overflow.append(row[field]);row[field]=row[field][:200]
                if len(row['dates'])>100:overflow.append(row['dates']);row['dates']=row['dates'][:100]
                if len(row['description'])>10000:overflow.append(row['description'][10000:]);row['description']=row['description'][:10000]
            result[key]=parsed[:30]
            if len(parsed)>30:overflow.extend(json_text(row) for row in parsed[30:])
        else:
            content='\n'.join(line.strip() for line in lines if line.strip()) if key in {'skills','certifications','achievements','publications','additional'} else join_lines(lines)
            result[key]=content[:10000]
            if len(content)>10000:overflow.append(content[10000:])
    if not sections:
        result['summary']=join_lines(preamble[1:])[:10000]
    if overflow:
        result['additional']=(result.get('additional','')+'\n'+'\n'.join(overflow))[:10000]
        if 'additional' not in result['section_order']:result['section_order'].append('additional')
    result['import_warnings']=['Review the extracted text and section grouping before saving or exporting; original layouts are not retained.']
    return result

def json_text(row):
    return ' | '.join(str(value) for value in row.values() if value)
