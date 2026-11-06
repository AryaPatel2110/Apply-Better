import asyncio
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from fastapi import FastAPI
from backend.resume_builder import router_for

class ResumeBuilderTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.app=FastAPI()
        self.app.include_router(router_for(self.directory,threading.RLock()))

    def tearDown(self):self.temp.cleanup()

    def request(self,method,path,payload=None):
        async def run():
            sent=[]
            async def receive():return {'type':'http.request','body':json.dumps(payload or {}).encode(),'more_body':False}
            async def send(message):sent.append(message)
            await self.app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','headers':[(b'content-type',b'application/json')],'server':('test',80),'client':('test',123)},receive,send)
            return sent[0],b''.join(message.get('body',b'') for message in sent[1:])
        return asyncio.run(run())

    def test_create_edit_and_restart(self):
        response,body=self.request('POST','/api/resume-drafts',{'title':'Engineering','name':'Alex Morgan','experience':[{'title':'Engineer','organization':'Example','description':'Built products.'}]})
        self.assertEqual(response['status'],201)
        created=json.loads(body)
        self.assertEqual(created['name'],'Alex Morgan')
        response,body=self.request('PUT','/api/resume-drafts/'+created['id'],{**created,'summary':'Updated summary'})
        self.assertEqual(response['status'],200)
        self.app=FastAPI()
        self.app.include_router(router_for(self.directory,threading.RLock()))
        response,body=self.request('GET','/api/resume-drafts')
        drafts=json.loads(body)
        self.assertEqual(len(drafts),1)
        self.assertEqual(drafts[0]['summary'],'Updated summary')
        self.assertEqual(drafts[0]['experience'][0]['organization'],'Example')
        self.assertEqual(len(list((self.directory/'resume_drafts').glob('*.json'))),1)

    def test_pdf_with_escaped_content_and_multiple_pages(self):
        resume={'name':'Alex Morgan','title':'Resume','summary':'Research & development <systems>','experience':[{'title':'Engineer','description':'\n'.join('Delivered useful products and documented reliable systems.' for _ in range(160))}]}
        response,body=self.request('POST','/api/resume-drafts/pdf',resume)
        self.assertEqual(response['status'],200)
        self.assertTrue(body.startswith(b'%PDF-'))
        self.assertTrue(body.rstrip().endswith(b'%%EOF'))
        self.assertIn((b'content-type',b'application/pdf'),response['headers'])
        self.assertTrue(any(b'Alex%20Morgan.pdf' in value for key,value in response['headers'] if key==b'content-disposition'))
        self.assertGreater(len(re.findall(rb'/Type\s*/Page\b',body)),1)
        self.assertEqual(list((self.directory/'resume_drafts').glob('*.json')),[])

    def test_layout_and_optional_sections_persist_and_export(self):
        payload={'name':'Alex Morgan','paper_size':'A4','font_family':'Georgia','font_size':12,
            'alignment':'left','margin':40,'line_spacing':1.3,'section_spacing':10,'template':'classic',
            'links':[{'label':'Portfolio','url':'https://example.com/work'}],
            'section_order':['skills','certifications','experience','summary'],
            'summary':'Summary content.','skills':'Python, SQL','certifications':'AWS Certified',
            'experience':[{'title':'Engineer','organization':'Example','location':'Chicago, IL','dates':'2024 – Present','description':'Built products.'}]}
        response,body=self.request('POST','/api/resume-drafts',payload)
        saved=json.loads(body)
        self.assertEqual(response['status'],201)
        for key,value in payload.items():
            if key != 'experience':self.assertEqual(saved[key],value)
        self.assertEqual(saved['experience'][0]['location'],'Chicago, IL')
        response,pdf=self.request('POST','/api/resume-drafts/pdf',saved)
        self.assertEqual(response['status'],200)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'example.com/work',pdf)
        # Different physical paper sizes must reach the PDF, rather than just the preview.
        self.assertRegex(pdf,rb'/MediaBox\s*\[\s*0\s+0\s+595\.27[0-9]*\s+841\.89')

    def test_parse_pasted_text_without_saving_base_resume(self):
        text='Alex Morgan\nalex@example.com | Chicago, IL\n\n## SUMMARY\nUpdated data scientist summary.\n\n**SKILLS**\nLanguages: Python, SQL'
        response,body=self.request('POST','/api/resume-drafts/parse-text',{'text':text})
        self.assertEqual(response['status'],200)
        parsed=json.loads(body)
        self.assertEqual(parsed['name'],'Alex Morgan')
        self.assertEqual(parsed['summary'],'Updated data scientist summary.')
        self.assertEqual(parsed['skills'],'Languages: Python, SQL')
        self.assertEqual(parsed['section_order'],['summary','skills'])
        self.assertEqual(list((self.directory/'resume_drafts').glob('*.json')),[])
        response,_=self.request('POST','/api/resume-drafts/parse-text',{'text':'   '})
        self.assertEqual(response['status'],400)

    def test_full_pasted_resume_preserves_every_entry_and_bullet(self):
        from io import BytesIO
        from pypdf import PdfReader
        text=(Path(__file__).parent/'fixtures'/'pasted_resume.txt').read_text()
        response,body=self.request('POST','/api/resume-drafts/parse-text',{'text':text})
        self.assertEqual(response['status'],200)
        parsed=json.loads(body)
        self.assertEqual(parsed['section_order'],['summary','education','experience','projects','skills'])
        self.assertEqual(parsed['name'],'Arya Patel')
        self.assertEqual(parsed['location'],'Chicago, IL')
        self.assertEqual(parsed['email'],'aryajpatel83@gmail.com')
        self.assertEqual(parsed['phone'],'+1 (312) 284-9308')
        self.assertEqual([link['url'] for link in parsed['links']],['https://linkedin.com/in/aryapatel21','https://github.com/AryaPatel2110','https://patelarya.com'])
        schools=parsed['education']
        self.assertEqual([(e['organization'],e['title'],e['dates'],e['gpa']) for e in schools],[
            ('Illinois Institute of Technology','Master of Science, Data Science','May 2026','3.9/4.0'),
            ('Gujarat Technological University','Bachelor of Engineering, Information Technology','May 2024','3.9/4.0')])
        jobs=parsed['experience']
        self.assertEqual([(e['title'],e['organization'],e['location'],e['dates']) for e in jobs],[
            ('Data Scientist Intern','LabelMaster','Chicago, IL','Jan 2026 – May 2026'),
            ('Data Scientist Intern','Shoptaki','Staten Island, NY','May 2025 – Aug 2025'),
            ('Data Scientist','Algobazar','Gujarat, India','Jul 2022 – Aug 2024')])
        self.assertEqual([len(e['description'].splitlines()) for e in jobs],[5,3,5])
        projects=parsed['projects']
        self.assertEqual([e['title'] for e in projects],['E-Commerce Funnel Analysis & A/B Experimentation','CardShield'])
        self.assertEqual([len(e['description'].splitlines()) for e in projects],[2,2])
        # Every achievement paragraph must survive verbatim, once, in its original entry.
        for section,entries,end in [('WORK EXPERIENCE',jobs,'PROJECTS'),('PROJECTS',projects,'SKILLS')]:
            source=text.split('\n'+section+'\n',1)[1].split('\n'+end+'\n',1)[0]
            paragraphs=[p.strip() for p in source.split('\n\n') if p.strip()]
            cursor=0
            for entry in entries:
                self.assertIn(entry['title'],paragraphs[cursor]);cursor+=1
                actual=entry['description'].splitlines()
                self.assertEqual(actual,paragraphs[cursor:cursor+len(actual)])
                cursor+=len(actual)
            self.assertEqual(cursor,len(paragraphs))
        self.assertEqual(len(parsed['skills'].splitlines()),5)
        response,pdf=self.request('POST','/api/resume-drafts/pdf',parsed)
        self.assertEqual(response['status'],200)
        extracted=' '.join(' '.join(page.extract_text().split()) for page in PdfReader(BytesIO(pdf)).pages)
        for entry in jobs+projects:
            for bullet in entry['description'].splitlines():
                self.assertIn(' '.join(bullet.split()),extracted)
        self.assertEqual(list((self.directory/'resume_drafts').glob('*.json')),[])

    def test_pasted_marked_bullets_keep_wrapped_lines_together(self):
        text='Alex Morgan\nWORK EXPERIENCE\nEngineer | Example | Chicago, IL | Jan 2024 – Present\n• Built reliable systems\n  across three teams.\n• Improved delivery.\nPROJECTS\nService | Python\n- Built a service\n  used by customers.\n- Documented it.'
        response,body=self.request('POST','/api/resume-drafts/parse-text',{'text':text})
        self.assertEqual(response['status'],200)
        parsed=json.loads(body)
        self.assertEqual(parsed['experience'][0]['description'].splitlines(),['Built reliable systems across three teams.','Improved delivery.'])
        self.assertEqual(parsed['projects'][0]['description'].splitlines(),['Built a service used by customers.','Documented it.'])

    def test_reject_invalid_layout(self):
        for invalid in [{'font_size':50},{'font_family':'Unknown'},{'paper_size':'Unknown'},
                        {'section_order':['summary','summary']},{'section_order':['unknown']},
                        {'margin':0},{'line_spacing':5}]:
            response,_=self.request('POST','/api/resume-drafts',invalid)
            self.assertEqual(response['status'],422)

    def test_validation_and_missing_draft(self):
        response,_=self.request('POST','/api/resume-drafts',{'name':'x'*201})
        self.assertEqual(response['status'],422)
        response,_=self.request('PUT','/api/resume-drafts/'+'a'*32,{'name':'Alex'})
        self.assertEqual(response['status'],404)
        response,_=self.request('PUT','/api/resume-drafts/invalid',{'name':'Alex'})
        self.assertEqual(response['status'],404)
