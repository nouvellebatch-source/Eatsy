import unittest
import os
from unittest.mock import patch
import pymupdf as fitz
from fastapi.testclient import TestClient
from app.main import create_app, get_db, get_user
from app.menu_import import extract_menu, parse_menu, MenuReadError

class Cursor:
    def __init__(self, allowed=True): self.allowed=allowed; self.calls=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params): self.calls.append((sql,params))
    def fetchone(self): return {'role':'owner'} if self.allowed else None
class DB:
    def __init__(self,allowed=True): self.c=Cursor(allowed); self.committed=False
    def cursor(self): return self.c
    def begin(self): pass
    def commit(self): self.committed=True
    def rollback(self): pass

class MenuImportTests(unittest.TestCase):
    def test_parse_prices_and_ignore_ambiguous_decimals(self):
        self.assertEqual(parse_menu('PIZZAS\nMargarita $ 25.000\nPorción 12.50\nAgua 5000'),[
          {'name':'Margarita','description':'','category':'PIZZAS','price':25000},
          {'name':'Agua','description':'','category':'PIZZAS','price':5000}])
    def test_text_pdf_is_read_without_ocr(self):
        doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),'PIZZAS\nPizza clasica 25000\nHamburguesa especial 18000'); content=doc.tobytes(); doc.close()
        result=extract_menu(content); self.assertEqual(result['ocr_pages'],0); self.assertEqual([x['price'] for x in result['items']],[25000,18000])
    def test_invalid_file_is_rejected(self):
        with self.assertRaises(MenuReadError): extract_menu(b'not a pdf')
    def test_scanned_pdf_uses_ocr(self):
        doc=fitz.open(); doc.new_page(); content=doc.tobytes(); doc.close()
        with patch('app.menu_import.local_ocr',return_value='BEBIDAS\nAgua 5000'):
            result=extract_menu(content)
        self.assertEqual(result['ocr_pages'],1); self.assertEqual(result['items'][0]['price'],5000)
    @patch('app.main._write_request_log')
    def test_real_local_ocr_reads_scanned_pdf_and_price(self, _):
        source=fitz.open();page=source.new_page(width=700,height=330)
        page.insert_text((45,70),'MENU DEL RESTAURANTE',fontsize=27)
        page.insert_text((45,145),'Pizza Margarita                 $ 25.000',fontsize=22)
        page.insert_text((45,220),'TOTAL                                $ 25.000',fontsize=22)
        image=page.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png')
        scanned=fitz.open();scanned.new_page(width=700,height=330).insert_image(fitz.Rect(0,0,700,330),stream=image)
        data=scanned.tobytes();source.close();scanned.close()
        result=extract_menu(data)
        self.assertEqual(result['ocr_pages'],1)
        self.assertTrue(any('Pizza' in item['name'] and item['price']==25000 for item in result['items']))
        self.assertFalse(any(item['name'].upper()=='TOTAL' for item in result['items']))
        client,_db=self.client()
        response=client.post('/gestion/restaurantes/1/facturas/leer',content=data,headers={'content-type':'application/pdf'})
        self.assertEqual(response.status_code,200)
        self.assertIn('25.000', response.json()['text'])
        self.assertEqual(response.json()['ocr_pages'],1)
    def test_mistral_requires_explicit_configuration(self):
        doc=fitz.open();doc.new_page();content=doc.tobytes();doc.close()
        with patch.dict(os.environ, {'MISTRAL_API_KEY':''}):
            with self.assertRaises(MenuReadError): extract_menu(content, 'mistral')
    @patch.dict(os.environ, {'MISTRAL_API_KEY':'test-key'})
    @patch('app.menu_import.requests.post')
    def test_mistral_sends_pdf_and_parses_markdown_table(self,post):
        doc=fitz.open();doc.new_page();content=doc.tobytes();doc.close()
        response=post.return_value.__enter__.return_value
        response.status_code=200
        response.iter_content.return_value=[b'{"pages":[{"markdown":"# Pizzas\\n| Pizza | $ 25.000 |"}]}']
        result=extract_menu(content,'mistral')
        self.assertEqual(result['items'][0]['price'],25000)
        self.assertEqual(result['items'][0]['category'],'Pizzas')
        self.assertTrue(post.call_args.kwargs['json']['document']['document_url'].startswith('data:application/pdf;base64,'))
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
    @patch.dict(os.environ, {'MISTRAL_API_KEY':'test-key'})
    @patch('app.menu_import.requests.post')
    def test_mistral_errors_are_not_forwarded_with_secrets(self,post):
        doc=fitz.open();doc.new_page();content=doc.tobytes();doc.close()
        post.return_value.__enter__.return_value.status_code=401
        with self.assertRaises(MenuReadError) as error: extract_menu(content,'mistral')
        self.assertNotIn('test-key',str(error.exception))
    def client(self,allowed=True):
        db=DB(allowed); app=create_app(); app.dependency_overrides[get_db]=lambda:db; app.dependency_overrides[get_user]=lambda:{'id':4,'rol':'staff'}
        return TestClient(app),db
    @patch('app.main._write_request_log')
    def test_only_owner_can_extract_or_publish(self,_):
        client,db=self.client(False)
        self.assertEqual(client.post('/gestion/restaurantes/1/carta/extraer',content=b'%PDF-abc',headers={'content-type':'application/pdf'}).status_code,403)
        self.assertEqual(client.post('/gestion/restaurantes/1/carta/publicar',json={'items':[{'name':'A','category':'B','price':100}]}).status_code,403)
        self.assertFalse(db.committed)
        self.assertEqual(client.post('/gestion/restaurantes/1/facturas/leer',content=b'%PDF-abc',headers={'content-type':'application/pdf'}).status_code,403)
    @patch('app.main._write_request_log')
    def test_invoice_text_response_is_not_cached_or_persisted(self,_):
        client,db=self.client()
        doc=fitz.open(); page=doc.new_page();page.insert_text((72,72),'Comprobante de compra por veinte mil pesos');content=doc.tobytes();doc.close()
        response=client.post('/gestion/restaurantes/1/facturas/leer',content=content,headers={'content-type':'application/pdf'})
        self.assertEqual(response.status_code,200)
        self.assertIn('Comprobante',response.json()['text'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertFalse(db.committed)
    @patch('app.main._write_request_log')
    def test_publish_only_reviewed_fields_and_commits(self,_):
        client,db=self.client()
        response=client.post('/gestion/restaurantes/12/carta/publicar',json={'items':[{'name':'Pizza','category':'Pizzas','price':25000}]})
        self.assertEqual(response.status_code,201); self.assertEqual(response.json()['created'],1); self.assertTrue(db.committed)
        self.assertEqual(db.c.calls[-1][1],(12,'Pizza','','Pizzas',25000))
    @patch('app.main._write_request_log')
    def test_rejects_wrong_media_and_oversized_pdf(self,_):
        client,_db=self.client()
        self.assertEqual(client.post('/gestion/restaurantes/1/carta/extraer',content=b'x').status_code,415)
        self.assertEqual(client.post('/gestion/restaurantes/1/carta/extraer',content=b'%PDF-'+b'x'*(5*1024*1024),headers={'content-type':'application/pdf'}).status_code,413)
    @patch('app.main._write_request_log')
    def test_catalog_update_is_scoped_to_restaurant_and_requires_owner(self,_):
        payload={'name':'Pizza','category':'Pizzas','description':'','price':20000,'available':False}
        client,db=self.client()
        response=client.put('/gestion/restaurantes/12/carta/34',json=payload)
        self.assertEqual(response.status_code,200)
        update=next((sql,params) for sql,params in db.c.calls if sql.strip().startswith('UPDATE menu_products'))
        self.assertIn('WHERE id=%s AND restaurant_id=%s',update[0])
        self.assertEqual(update[1][-2:],(34,12))
        client,db=self.client(False)
        self.assertEqual(client.put('/gestion/restaurantes/12/carta/34',json=payload).status_code,403)
        self.assertFalse(any(sql.strip().startswith('UPDATE') for sql,_ in db.c.calls))

if __name__=='__main__': unittest.main()
