"""Add deterministic demo applications without replacing existing records."""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.main import DATA, RESUMES, LOCK, read_rows, write_rows


def pdf_resume(role):
    lines = ['DEMO RESUME - SAMPLE DATA', 'Alex Morgan', role,
             'alex@example.com | Portfolio: example.com',
             'Experience: Built analytics products and collaborated across teams.',
             'Skills: Python, SQL, communication, and product development.',
             'This fictional resume is for testing the application tracker.']
    content = 'BT /F1 14 Tf 50 760 Td 24 TL\n'
    for index, line in enumerate(lines):
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        content += ('T* ' if index else '') + f'({escaped}) Tj\n'
    content += 'ET'
    stream = content.encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream']
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(output)


def seed(as_of):
    rng = random.Random(42)
    roles = ['Data Scientist', 'Data Analyst', 'Machine Learning Engineer', 'Software Engineer', 'Analytics Engineer']
    companies = ['Northstar Labs', 'Cedar Analytics', 'Meridian Health', 'Atlas Systems', 'Juniper Finance', 'Orbit Technologies', 'Willow Data', 'Summit Cloud', 'Harbor AI', 'Lumen Research']
    # Growing activity, a summer peak, and a quieter current month.
    monthly_counts = [4, 6, 8, 11, 14, 17, 22, 27, 32, 26, 19, 14]
    first = as_of.year * 12 + as_of.month - 1 - 11
    new_rows = []
    for offset, count in enumerate(monthly_counts):
        month_index = first + offset
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        start = date(year, month, 1)
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        last_day = as_of.day if (year, month) == (as_of.year, as_of.month) else (next_month - timedelta(days=1)).day
        for index in range(count):
            applied = start + timedelta(days=rng.randrange(last_day))
            role = rng.choices(roles, weights=[35, 25, 18, 14, 8])[0]
            status = rng.choices(['Applied', 'Interviewing', 'Offer', 'Rejected', 'Withdrawn'], weights=[42, 25, 8, 20, 5])[0]
            identifier = f'demo-{year}-{month:02d}-{index:03d}'
            resume_path = RESUMES / f'{identifier}.pdf'
            new_rows.append(dict(id=identifier, company='Demo - ' + rng.choice(companies), job_title=role,
                job_link='https://example.com/jobs/' + identifier,
                job_description=f'SAMPLE APPLICATION\n\nWe are seeking a {role} to build reliable data products, collaborate with cross-functional teams, and communicate actionable insights.\n\nRequirements\n- Strong analytical and problem-solving skills\n- Experience with Python and SQL\n- Clear communication and attention to detail\n\nThis is fictional demo data.',
                status=status, applied_date=applied.isoformat(), created_at=datetime(applied.year, applied.month, applied.day, 12, tzinfo=timezone.utc).isoformat(),
                resume_name=f'Demo Resume - {role}.pdf', resume_path=str(resume_path.relative_to(DATA)),
                status_history=json.dumps([{'status':status,'at':None}])))
    with LOCK:
        existing = read_rows()
        ids = {row['id'] for row in existing}
        additions = sorted([row for row in new_rows if row['id'] not in ids], key=lambda row: row['applied_date'])
        for row in additions:
            (DATA / row['resume_path']).write_bytes(pdf_resume(row['job_title']))
        write_rows(existing + additions)
    print(f'Added {len(additions)} demo applications with sample PDFs. Preserved {len(existing)} existing applications.')
    print('Demo records use IDs beginning with demo- and company names beginning with Demo - .')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    seed(parser.parse_args().as_of)
