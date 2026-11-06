"""Replace tracker data with the exact 100-application funnel example."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.main import CSV, DATA, RESUMES, LOCK, write_rows, read_rows
from scripts.seed_demo import pdf_resume


def replace_demo(as_of):
    paths = (
        [['Applied', 'Ghosted']] * 80
        + [['Applied', 'Rejected']] * 10
        + [['Applied', 'Online Assessment', 'Rejected']] * 7
        + [['Applied', 'Online Assessment', 'Interviewing', 'Ghosted']]
        + [['Applied', 'Online Assessment', 'Interviewing', 'Offer']]
        + [['Applied', 'Online Assessment', 'Interviewing', 'Rejected']]
    )
    roles = ['Data Scientist', 'Data Analyst', 'Machine Learning Engineer', 'Software Engineer', 'Analytics Engineer']
    companies = ['Northstar Labs', 'Cedar Analytics', 'Atlas Systems', 'Juniper Finance', 'Harbor AI', 'Summit Cloud']
    rng = random.Random(23)
    rng.shuffle(paths)
    rows = []
    for index, path in enumerate(paths, 1):
        role = rng.choices(roles, weights=[35, 25, 18, 14, 8])[0]
        # Leave time for all transitions before the supplied as-of date.
        applied = as_of - timedelta(days=rng.randint(14, 160))
        history = [{'status': stage, 'at': datetime.combine(applied + timedelta(days=step * 4), datetime.min.time(), tzinfo=timezone.utc).replace(hour=12).isoformat()} for step, stage in enumerate(path)]
        identifier = f'flow-demo-{index:03d}'
        resume = RESUMES / f'{identifier}.pdf'
        rows.append(dict(id=identifier, company='Demo - ' + rng.choice(companies), job_title=role,
            job_link=f'https://example.com/jobs/{identifier}',
            job_description=f'FICTIONAL DEMO APPLICATION\n\nRole: {role}\nBuild analytics products, work with Python and SQL, and collaborate with cross-functional teams.\n\nRecorded stages: ' + ' -> '.join(path),
            status=path[-1], applied_date=applied.isoformat(), created_at=history[0]['at'],
            resume_name=f'Demo Resume - {role}.pdf', resume_path=str(resume.relative_to(DATA)),
            status_history=json.dumps(history)))
    rows.sort(key=lambda row: (row['applied_date'], row['id']))
    with LOCK:
        # Generate every replacement file before committing the new application CSV.
        for row in rows:
            (DATA / row['resume_path']).write_bytes(pdf_resume(row['job_title']))
        write_rows(rows)
        keep = {row['resume_path'] for row in rows}
        for file in RESUMES.rglob('*'):
            if file.is_file() and str(file.relative_to(DATA)) not in keep:
                file.unlink()
        # The user requested clearing all previous data, including the migration backup.
        CSV.with_suffix('.csv.pre-history.bak').unlink(missing_ok=True)
        (DATA / '.DS_Store').unlink(missing_ok=True)
    saved = read_rows()
    assert len(saved) == 100
    actual = Counter(tuple(event['status'] for event in json.loads(row['status_history'])) for row in saved)
    assert actual == Counter(tuple(path) for path in paths)
    assert len(list(RESUMES.glob('*.pdf'))) == 100
    for row in saved:
        assert (DATA / row['resume_path']).read_bytes().startswith(b'%PDF-')
        assert json.loads(row['status_history'])[-1]['status'] == row['status']
    print('Replaced all applications with 100 demo records and 100 sample PDF resumes.')
    print('Current statuses:', dict(Counter(row['status'] for row in saved)))
    print('Verified paths:')
    for path, count in actual.items():
        print(f'  {count}: ' + ' -> '.join(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace', action='store_true', help='Required: deletes existing applications and resumes.')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    if not args.replace:
        parser.error('--replace is required because this clears existing data')
    replace_demo(args.as_of)
