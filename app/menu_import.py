"""Lectura acotada de cartas PDF. Las propuestas siempre requieren revisión humana."""
import os
import re
import base64
from functools import lru_cache
from threading import Lock

import pymupdf as fitz
import requests

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
PRICE = re.compile(r'^(.{2,160}?)\s+(?:\$\s*)?([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]{3,9})\s*(?:COP)?\s*$', re.I)


class MenuReadError(ValueError):
    pass


_ocr_lock = Lock()


@lru_cache(maxsize=1)
def _local_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)


def local_ocr(image: bytes) -> str:
    """Reconoce imágenes sin enviar el documento fuera del servidor."""
    try:
        with _ocr_lock:
            results, _ = _local_ocr_engine()(image)
    except Exception as exc:
        raise MenuReadError('No fue posible iniciar el OCR local. Comprueba las dependencias del servidor.') from exc
    if not results:
        return ''
    # El detector puede devolver nombre y precio en cajas separadas. Se agrupan
    # por línea para conservar la relación entre ambos al proponer productos.
    boxes = []
    for polygon, text, _confidence in results:
        xs, ys = zip(*polygon)
        boxes.append((min(xs), sum(ys) / len(ys), max(ys) - min(ys), text))
    boxes.sort(key=lambda box: (box[1], box[0]))
    lines = []
    for x, y, height, text in boxes:
        group = next((line for line in lines if abs(y - line['y']) <= max(height, line['height']) * 0.5), None)
        if group is None:
            lines.append({'y': y, 'height': height, 'words': [(x, text)]})
        else:
            group['words'].append((x, text))
    return '\n'.join(' '.join(word for _, word in sorted(line['words'])) for line in lines)


def parse_menu(text: str) -> list[dict]:
    result = []
    category = 'General'
    for line in text.splitlines():
        line = ' '.join(line.split())
        if not line:
            continue
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip().strip('*') for cell in line.strip('|').split('|')]
            if len(cells) >= 2:
                line = f'{cells[0]} {cells[-1]}'
        elif line.startswith('#'):
            line = line.lstrip('#').strip()
        match = PRICE.fullmatch(line)
        if match:
            name, raw = match.groups()
            if name.strip(' .-').casefold() in {'total', 'subtotal', 'iva', 'propina', 'impuesto', 'descuento'}:
                continue
            price = int(raw.replace('.', '').replace(',', ''))
            if price <= 1000000000:
                result.append({'name': name.strip(' .-'), 'description': '', 'category': category, 'price': price})
            if len(result) >= 100:
                break
        elif len(line) <= 60 and not any(c.isdigit() for c in line):
            category = line
    return result


def mistral_ocr(data: bytes, api_key: str) -> list[str]:
    payload = {'model': 'mistral-ocr-latest', 'document': {'type': 'document_url',
        'document_url': 'data:application/pdf;base64,' + base64.b64encode(data).decode('ascii')},
        'include_image_base64': False, 'include_blocks': False}
    try:
        with requests.post('https://api.mistral.ai/v1/ocr', json=payload,
                           headers={'Authorization': f'Bearer {api_key}'},
                           timeout=(5, 90), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise MenuReadError('Mistral OCR no pudo procesar el documento. Revisa la configuración o intenta más tarde.')
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    raise MenuReadError('La respuesta de OCR excede el tamaño permitido.')
        import json
        result = json.loads(content)
        pages = result['pages']
        if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
            raise ValueError('invalid pages')
        texts = [page['markdown'] for page in pages]
        if not all(isinstance(text, str) for text in texts):
            raise ValueError('invalid text')
        return texts
    except MenuReadError:
        raise
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise MenuReadError('No se pudo obtener una respuesta válida de Mistral OCR.') from exc


def extract_document(data: bytes, provider: str = 'local') -> dict:
    if len(data) > MAX_BYTES or not data.startswith(b'%PDF-'):
        raise MenuReadError('El archivo debe ser un PDF de máximo 5 MB.')
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise MenuReadError('No se pudo abrir el PDF.') from exc
    with doc:
        if doc.needs_pass or not 1 <= len(doc) <= MAX_PAGES:
            raise MenuReadError('El PDF no puede estar protegido y debe tener entre 1 y 10 páginas.')
        if provider == 'mistral':
            key = os.environ.get('MISTRAL_API_KEY', '').strip()
            if not key:
                raise MenuReadError('Mistral OCR no está configurado en el servidor.')
            pages = mistral_ocr(data, key)
            if len(pages) != len(doc):
                raise MenuReadError('Mistral OCR no devolvió todas las páginas del documento.')
            return {'text': '\n\n'.join(pages), 'pages': len(pages), 'ocr_pages': len(pages)}
        if provider != 'local':
            raise MenuReadError('Proveedor de OCR no válido.')
        pages, ocr_pages = [], 0
        for page in doc:
            text = page.get_text('text')
            if len(text.strip()) < 30:
                if page.rect.width > 2000 or page.rect.height > 2000:
                    raise MenuReadError('Una página excede el tamaño permitido para OCR.')
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                text = local_ocr(pix.tobytes('png'))
                ocr_pages += 1
            pages.append(text)
    return {'text': '\n\n'.join(pages), 'pages': len(pages), 'ocr_pages': ocr_pages}


def extract_menu(data: bytes, provider: str = 'local') -> dict:
    result = extract_document(data, provider)
    return {'items': parse_menu(result['text']), 'pages': result['pages'], 'ocr_pages': result['ocr_pages']}
