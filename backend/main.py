from pathlib import Path
import csv
import io
import json
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from backend.resume_builder import Resume, render_pdf, resume_filename
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('TRACKER_DATA_DIR', ROOT / 'data')).resolve()
RESUMES = DATA / 'resumes'
RESUMES.mkdir(parents=True, exist_ok=True)
CSV = DATA / 'applications.csv'
FIELDS = ['id', 'company', 'job_title', 'job_link', 'job_description', 'status', 'applied_date', 'created_at', 'resume_name', 'resume_path', 'status_history']
STATUSES = {'Applied', 'Online Assessment', 'Interviewing', 'Offer', 'Rejected', 'Ghosted', 'Withdrawn'}
LOCK = threading.RLock()
app = FastAPI(title='Apply Better application tracker')

def read_rows():
    with LOCK:
        if not CSV.exists():
            return []
        with CSV.open(newline='', encoding='utf-8') as file:
            rows = list(csv.DictReader(file))
        for row in rows:
            if not row.get('status_history'):
                row['status_history'] = json.dumps([{'status': row['status'], 'at': None}])
        return rows

def write_rows(rows):
    with LOCK:
        temp = CSV.with_suffix('.tmp')
        with temp.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
        temp.replace(CSV)

def migrate_storage():
    """Persist the history schema for old CSVs before serving any requests."""
    with LOCK:
        if not CSV.exists():
            write_rows([])
            return
        with CSV.open(newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames or []
            rows = list(reader)
        needs_migration = 'status_history' not in fields or any(not row.get('status_history') for row in rows)
        if not needs_migration:
            return
        # Preserve the exact original bytes once, before replacing the CSV.
        backup = CSV.with_suffix('.csv.pre-history.bak')
        if not backup.exists():
            with backup.open('xb') as file:
                file.write(CSV.read_bytes())
        for row in rows:
            if not row.get('status_history'):
                row['status_history'] = json.dumps([{'status': row['status'], 'at': None}])
        write_rows(rows)

migrate_storage()

def public(row):
    return {**{k: v for k, v in row.items() if k not in {'resume_path', 'status_history'}}, 'status_history': json.loads(row['status_history']), 'has_tailored_resume': (RESUMES / f"{row['id']}.json").is_file()}

@app.get('/api/applications')
def applications():
    return [public(r) for r in reversed(read_rows())]

@app.post('/api/applications', status_code=201)
def create(company: str = Form(...), job_title: str = Form(...), job_link: str = Form(...), job_description: str = Form(...), applied_date: str = Form(...), status: str = Form('Applied'), resume: UploadFile | None = File(None), tailored_resume: str | None = Form(None)):
    if not all(v.strip() for v in [company, job_title, job_link, job_description]):
        raise HTTPException(400, 'Please complete all required fields.')
    if not job_link.startswith(('https://', 'http://')):
        raise HTTPException(400, 'Job link must begin with https:// or http://.')
    try:
        date.fromisoformat(applied_date)
    except ValueError:
        raise HTTPException(400, 'Invalid application date.')
    if status not in STATUSES:
        raise HTTPException(400, 'Invalid status.')
    tailored = None
    if isinstance(tailored_resume, str):
        try:
            tailored = Resume.model_validate_json(tailored_resume)
        except ValidationError as exc:
            raise HTTPException(400, 'Invalid tailored resume.') from exc
        if not tailored.name.strip():
            raise HTTPException(400, 'Enter your full name in the tailored resume.')
        name = resume_filename(tailored.name)
        suffix = '.pdf'
        content = render_pdf(tailored)
    else:
        if resume is None or not hasattr(resume, 'file'):
            raise HTTPException(400, 'Select a Resume Builder resume.')
        name = Path((resume.filename or '').replace('\\', '/')).name
        suffix = Path(name).suffix.lower()
        if suffix not in {'.pdf', '.docx', '.doc'}:
            raise HTTPException(400, 'Upload a PDF, DOCX, or DOC resume.')
        content = resume.file.read(10 * 1024 * 1024 + 1)
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, 'Resume must be between 1 byte and 10 MB.')
        if suffix == '.pdf' and not content.startswith(b'%PDF-'):
            raise HTTPException(400, 'The uploaded file is not a valid PDF.')
    identifier = uuid.uuid4().hex
    path = RESUMES / f'{identifier}{suffix}'
    row = dict(id=identifier, company=company.strip(), job_title=job_title.strip(), job_link=job_link.strip(), job_description=job_description.strip(), status=status, applied_date=applied_date, created_at=datetime.now(timezone.utc).isoformat(), resume_name=name, resume_path=str(path.relative_to(DATA)), status_history=json.dumps([{'status': status, 'at': datetime.now(timezone.utc).isoformat()}]))
    with LOCK:
        path.write_bytes(content)
        if tailored is not None:
            path.with_suffix('.json').write_text(tailored.model_dump_json(), encoding='utf-8')
        try:
            write_rows(read_rows() + [row])
        except Exception:
            path.unlink(missing_ok=True)
            if tailored is not None: path.with_suffix('.json').unlink(missing_ok=True)
            raise
    return public(row)

@app.delete('/api/applications/{identifier}')
def delete_application(identifier: str):
    with LOCK:
        rows = read_rows()
        row = next((row for row in rows if row['id'] == identifier), None)
        if row is None:
            raise HTTPException(404, 'Application not found.')
        path = (DATA / row['resume_path']).resolve()
        if not path.is_relative_to(RESUMES):
            raise HTTPException(400, 'Invalid resume path.')
        files = [path, path.with_suffix('.json')]
        staged = []
        try:
            for file in files:
                if file.is_file():
                    temporary = file.with_name(file.name + '.deleting')
                    file.replace(temporary)
                    staged.append((file, temporary))
            write_rows([row for row in rows if row['id'] != identifier])
        except Exception:
            for original, temporary in reversed(staged):
                temporary.replace(original)
            raise
        for original, temporary in staged:
            temporary.unlink(missing_ok=True)
    return {'deleted': True}

@app.patch('/api/applications/{identifier}')
def update_status(identifier: str, payload: dict):
    supplied_history = payload.get('status_history')
    if supplied_history is not None:
        if not isinstance(supplied_history, list) or not supplied_history or len(supplied_history) > 100 or any(not isinstance(stage, str) or stage not in STATUSES for stage in supplied_history):
            raise HTTPException(400, 'History must contain 1–100 valid statuses in chronological order.')
        payload['status'] = supplied_history[-1]
    if payload.get('status') not in STATUSES:
        raise HTTPException(400, 'Invalid status.')
    with LOCK:
        rows = read_rows()
        row = next((r for r in rows if r['id'] == identifier), None)
        if row is None:
            raise HTTPException(404, 'Application not found.')
        if supplied_history is not None:
            # Backfilled stages have unknown dates; do not invent transition times.
            row['status_history'] = json.dumps([{'status': stage, 'at': None} for stage in supplied_history])
        elif row['status'] != payload['status']:
            history = json.loads(row['status_history'])
            history.append({'status': payload['status'], 'at': datetime.now(timezone.utc).isoformat()})
            row['status_history'] = json.dumps(history)
        row['status'] = payload['status']
        write_rows(rows)
    return public(row)

@app.get('/api/applications/{identifier}/resume')
def get_resume(identifier: str, download: bool = False):
    row = next((r for r in read_rows() if r['id'] == identifier), None)
    if row is None:
        raise HTTPException(404, 'Application not found.')
    path = (DATA / row['resume_path']).resolve()
    if not path.is_relative_to(RESUMES) or not path.is_file():
        raise HTTPException(404, 'Resume file not found.')
    name = row['resume_name']
    source = path.with_suffix('.json')
    if source.is_file():
        name = resume_filename(Resume.model_validate_json(source.read_text(encoding='utf-8')).name, path.suffix)
    elif path.suffix in {'.pdf', '.docx'}:
        from backend.resume_import import extract_document, parse_resume
        try:
            text, links = extract_document(path.read_bytes(), path.name)
            parsed = parse_resume(text, links, path.name)
            if parsed['name'] != path.stem:
                name = resume_filename(parsed['name'], path.suffix)
        except HTTPException:
            pass
    media = 'application/pdf' if path.suffix == '.pdf' else 'application/octet-stream'
    return FileResponse(path, media_type=media, filename=name, content_disposition_type='attachment' if download else 'inline', headers={'X-Content-Type-Options': 'nosniff'})

def application_source(identifier):
    if not any(row['id'] == identifier for row in read_rows()):
        raise HTTPException(404, 'Application not found.')
    if not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise HTTPException(404, 'Application not found.')
    return RESUMES / f'{identifier}.json'

@app.get('/api/applications/{identifier}/tailored-resume')
def get_tailored_resume(identifier: str):
    path = application_source(identifier)
    if not path.is_file():
        raise HTTPException(404, 'This application has no editable resume.')
    return json.loads(path.read_text(encoding='utf-8'))

@app.put('/api/applications/{identifier}/tailored-resume')
def save_tailored_resume(identifier: str, resume: Resume):
    application_source(identifier)
    raise HTTPException(403, 'The resume is locked after application submission.')

@app.get('/api/export')
def export_csv():
    # Prevent spreadsheet formula execution when opening exported user input.
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    for row in read_rows():
        writer.writerow({k: "'" + v if v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="applications.csv"'})

from backend.resume_builder import router_for
app.include_router(router_for(DATA, LOCK))

DIST = ROOT / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
