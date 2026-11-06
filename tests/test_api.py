"""Integration checks with isolated storage; no user data is touched."""
import importlib
import csv
import asyncio
import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from fastapi import HTTPException, UploadFile

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ['TRACKER_DATA_DIR'] = self.temp.name
        from backend import main
        self.api = importlib.reload(main)

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop('TRACKER_DATA_DIR', None)

    def create(self, **overrides):
        args = dict(company='Example, Inc.', job_title='Engineer', job_link='https://example.com/job', job_description='Build things.\nCollaborate.', applied_date='2026-10-23', status='Applied', resume=UploadFile(filename='resume.pdf', file=io.BytesIO(b'%PDF-1.4\nexample')))
        args.update(overrides)
        return self.api.create(**args)

    def test_tailored_resume_is_locked_after_submission(self):
        source={'name':'Alex Morgan','title':'Master','skills':'Languages: Python, SQL'}
        row=self.create(resume=None, tailored_resume=json.dumps(source))
        self.assertTrue(row['has_tailored_resume'])
        self.assertEqual(row['resume_name'],'Alex Morgan.pdf')
        self.assertIn('Alex%20Morgan.pdf',self.api.get_resume(row['id'],True).headers['content-disposition'])
        saved=self.api.get_tailored_resume(row['id'])
        self.assertEqual(saved['skills'], source['skills'])
        from backend.resume_builder import Resume
        original_pdf=Path(self.api.get_resume(row['id'],True).path).read_bytes()
        with self.assertRaises(HTTPException) as rejected:
            self.api.save_tailored_resume(row['id'], Resume(**{**saved,'skills':'Languages: Python, R'}))
        self.assertEqual(rejected.exception.status_code,403)
        self.api=importlib.reload(self.api)
        self.assertEqual(self.api.get_tailored_resume(row['id'])['skills'],'Languages: Python, SQL')
        self.assertEqual(source['skills'],'Languages: Python, SQL')
        self.assertTrue(original_pdf.startswith(b'%PDF-'))
        self.assertEqual(Path(self.api.get_resume(row['id'],True).path).read_bytes(),original_pdf)
        self.assertEqual(list((self.api.DATA/'resume_drafts').glob('*.json')),[])
        other=self.create()
        with self.assertRaises(HTTPException):self.api.get_tailored_resume(other['id'])
        with self.assertRaises(HTTPException):self.api.save_tailored_resume('missing',Resume(**source))

    def test_delete_application_removes_its_files_only(self):
        row=self.create(resume=None,tailored_resume=json.dumps({'name':'Alex Morgan'}))
        other=self.create()
        pdf=Path(self.api.get_resume(row['id']).path)
        source=pdf.with_suffix('.json')
        self.assertTrue(source.exists())
        self.assertEqual(self.api.delete_application(row['id']),{'deleted':True})
        self.assertFalse(pdf.exists())
        self.assertFalse(source.exists())
        self.assertEqual([item['id'] for item in self.api.applications()],[other['id']])
        self.assertTrue(Path(self.api.get_resume(other['id']).path).exists())
        with self.assertRaises(HTTPException) as missing:self.api.delete_application(row['id'])
        self.assertEqual(missing.exception.status_code,404)

    def test_save_reload_status_and_download(self):
        row = self.create()
        self.assertNotIn('resume_path', row)
        self.assertEqual(self.api.applications()[0]['company'], 'Example, Inc.')
        self.assertEqual(self.api.read_rows()[0]['job_description'], 'Build things.\nCollaborate.')
        updated = self.api.update_status(row['id'], {'status': 'Interviewing'})
        self.assertEqual(updated['status'], 'Interviewing')
        response = self.api.get_resume(row['id'], True)
        self.assertEqual(Path(response.path).read_bytes(), b'%PDF-1.4\nexample')
        self.assertIn('attachment', response.headers['content-disposition'])
        self.assertIn('inline', self.api.get_resume(row['id']).headers['content-disposition'])
        self.assertIn('resume_path', self.api.export_csv().body.decode())

    def test_status_history_and_backfill(self):
        row = self.create()
        for stage in ['Online Assessment', 'Interviewing', 'Ghosted']:
            row = self.api.update_status(row['id'], {'status': stage})
        self.assertEqual([event['status'] for event in row['status_history']], ['Applied', 'Online Assessment', 'Interviewing', 'Ghosted'])
        self.api.update_status(row['id'], {'status': 'Ghosted'})
        self.assertEqual(len(self.api.applications()[0]['status_history']), 4)
        row = self.api.update_status(row['id'], {'status_history': ['Applied', 'Online Assessment', 'Rejected']})
        self.assertEqual(row['status'], 'Rejected')
        self.assertTrue(all(event['at'] is None for event in row['status_history']))
        for invalid in [[], ['Invalid'], 'Applied']:
            with self.assertRaises(HTTPException):
                self.api.update_status(row['id'], {'status_history': invalid})

    def test_startup_migrates_legacy_csv_without_changing_data(self):
        saved = self.create()
        legacy = self.api.read_rows()[0]
        del legacy['status_history']
        with self.api.CSV.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=list(legacy))
            writer.writeheader()
            writer.writerow(legacy)
        original = self.api.CSV.read_bytes()
        self.api = importlib.reload(self.api)
        with self.api.CSV.open(newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            self.assertIn('status_history', reader.fieldnames)
            migrated = next(reader)
        self.assertEqual({k:v for k,v in migrated.items() if k != 'status_history'}, legacy)
        self.assertEqual(json.loads(migrated['status_history']), [{'status':'Applied','at':None}])
        self.assertEqual(self.api.CSV.with_suffix('.csv.pre-history.bak').read_bytes(), original)
        after = self.api.CSV.read_bytes()
        self.api.migrate_storage()
        self.assertEqual(self.api.CSV.read_bytes(), after)
        self.api.update_status(saved['id'], {'status':'Online Assessment'})
        self.api = importlib.reload(self.api)
        history = self.api.applications()[0]['status_history']
        self.assertEqual([event['status'] for event in history], ['Applied','Online Assessment'])
        self.assertIsNotNone(history[-1]['at'])
        exported = list(csv.DictReader(io.StringIO(self.api.export_csv().body.decode())))
        self.assertEqual(json.loads(exported[0]['status_history']), history)

    def test_existing_history_is_not_replaced_on_restart(self):
        row = self.create()
        self.api.update_status(row['id'], {'status':'Online Assessment'})
        self.api.update_status(row['id'], {'status':'Ghosted'})
        original = self.api.CSV.read_bytes()
        self.api = importlib.reload(self.api)
        self.assertEqual(self.api.CSV.read_bytes(), original)
        self.assertEqual(self.api.applications()[0]['status'], 'Ghosted')

    def test_http_save_history_after_ghosting(self):
        row = self.create()
        async def patch_history():
            body = json.dumps({'status':'Offer','status_history':['Applied','Ghosted','Offer']}).encode()
            sent = []
            async def receive():
                return {'type':'http.request','body':body,'more_body':False}
            async def send(message):
                sent.append(message)
            await self.api.app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                'method':'PATCH','scheme':'http','path':f"/api/applications/{row['id']}",
                'raw_path':f"/api/applications/{row['id']}".encode(),'query_string':b'',
                'headers':[(b'content-type',b'application/json')],'server':('test',80),'client':('test',123)},receive,send)
            self.assertEqual(sent[0]['status'], 200)
            response = json.loads(b''.join(message.get('body', b'') for message in sent[1:]))
            self.assertEqual(response['status'], 'Offer')
            self.assertEqual([event['status'] for event in response['status_history']], ['Applied','Ghosted','Offer'])
        asyncio.run(patch_history())
        self.api = importlib.reload(self.api)
        self.assertEqual([event['status'] for event in self.api.applications()[0]['status_history']], ['Applied','Ghosted','Offer'])

    def test_invalid_upload_and_status(self):
        with self.assertRaises(HTTPException):
            self.create(resume=UploadFile(filename='bad.pdf', file=io.BytesIO(b'not pdf')))
        self.assertEqual(self.api.applications(), [])
        with self.assertRaises(HTTPException):
            self.create(status='Unknown')
        with self.assertRaises(HTTPException):
            self.api.get_resume('missing')

    def test_formula_safe_export_and_missing_resume(self):
        row = self.create(company='=1+1')
        self.assertIn("'=1+1", self.api.export_csv().body.decode())
        stored = self.api.read_rows()[0]
        (self.api.DATA / stored['resume_path']).unlink()
        with self.assertRaises(HTTPException):
            self.api.get_resume(row['id'])

if __name__ == '__main__':
    unittest.main()
