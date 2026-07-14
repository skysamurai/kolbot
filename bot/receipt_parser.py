"""
DeepSeek API integration for receipt parsing.
Fetches receipt URL, then sends content to DeepSeek for parsing.
"""
import os, json, re
from html.parser import HTMLParser
from dotenv import load_dotenv
import httpx

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'

OUR_PRODUCTS = [
    'варежка', 'варежки', 'варежек', 'варежками',
    'рукавица', 'рукавицы', 'рукавиц',
    'mitten', 'mittens',
]

RECEIPT_PARSE_PROMPT = """Ты — парсер чеков. Извлеки из текста чека следующую информацию.

Важно: ищи ТОЛЬКО эти товары (или похожие названия): варежки, варежка, рукавицы, рукавица, mittens, mitten.

Верни ТОЛЬКО JSON без пояснений:
{
  "receipt_number": "номер чека или null если не найден",
  "products": [
    {"name": "название товара", "quantity": количество (число), "price": цена за единицу (число или null)}
  ],
  "total": общая сумма чека (число или null),
  "store": "название магазина или null",
  "date": "дата чека в ISO формате или null",
  "error": null если всё OK, или описание ошибки
}

Если не можешь прочитать чек, поставь error с описанием проблемы.
Если в чеке нет наших товаров, верни products = []."""


class TextExtractor(HTMLParser):
    """Extract visible text from HTML."""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script', 'style', 'meta', 'link', 'head'}
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            stripped = data.strip()
            if stripped:
                self.text.append(stripped)


def _call_deepseek(user_content: str, image_base64: str = None) -> dict:
    """Call DeepSeek API with text and optional image."""
    if not DEEPSEEK_API_KEY:
        return {'error': 'DeepSeek API key not configured'}

    messages = [
        {
            'role': 'system',
            'content': 'Ты парсер чеков. Отвечай ТОЛЬКО валидным JSON, без markdown и пояснений.'
        },
    ]

    if image_base64:
        # Vision request — send image + text
        messages.append({
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {'url': f'data:image/jpeg;base64,{image_base64}'}
                },
                {
                    'type': 'text',
                    'text': f'{RECEIPT_PARSE_PROMPT}\n\nПроанализируй изображение чека.'
                }
            ]
        })
    else:
        messages.append({
            'role': 'user',
            'content': f'{RECEIPT_PARSE_PROMPT}\n\nТекст чека:\n{user_content[:8000]}'
        })

    payload = {
        'model': 'deepseek-chat',
        'messages': messages,
        'temperature': 0.1,
        'max_tokens': 2000,
    }

    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json',
    }

    r = httpx.post(DEEPSEEK_API_URL, json=payload, headers=headers, timeout=90)
    r.raise_for_status()
    result = r.json()
    content = result['choices'][0]['message']['content'].strip()

    # Strip markdown code fences
    if content.startswith('```'):
        content = content.split('\n', 1)[1]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


def parse_receipt(receipt_url: str) -> dict:
    """Fetch receipt URL and parse with DeepSeek. Returns structured data."""
    if not DEEPSEEK_API_KEY:
        return {'receipt_number': None, 'products': [], 'error': 'DeepSeek API key not configured'}

    # Step 1: Fetch the URL
    try:
        response = httpx.get(receipt_url, timeout=30, follow_redirects=True,
                             headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'})
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {'receipt_number': None, 'products': [],
                'error': f'Страница недоступна (HTTP {e.response.status_code}). Попробуйте скопировать текст чека и вставить сюда.'}
    except Exception as e:
        # If we can't fetch, ask DeepSeek to try with just the URL (may work for known domains)
        return _try_deepseek_with_url(receipt_url)

    content_type = response.headers.get('content-type', '').lower()

    # Step 2: Check if it's an image
    if any(t in content_type for t in ('image/jpeg', 'image/png', 'image/webp', 'image/gif')):
        import base64
        img_b64 = base64.b64encode(response.content).decode('utf-8')
        try:
            return _call_deepseek('', image_base64=img_b64)
        except Exception as e:
            return {'receipt_number': None, 'products': [],
                    'error': f'Не удалось распознать изображение чека: {e}'}

    # Step 3: Parse text content
    raw_text = response.text

    # If HTML, extract text
    if 'text/html' in content_type or raw_text.strip().startswith('<!') or raw_text.strip().startswith('<html'):
        extractor = TextExtractor()
        try:
            extractor.feed(raw_text)
            raw_text = '\n'.join(extractor.text)
        except Exception:
            pass  # use raw HTML if extraction fails

    # Basic text cleanup
    raw_text = re.sub(r'\s+', ' ', raw_text).strip()

    if len(raw_text) < 50:
        return {'receipt_number': None, 'products': [],
                'error': 'На странице недостаточно текста. Возможно, это не чек. Пришлите прямую ссылку на чек.'}

    # Step 4: Send to DeepSeek
    try:
        return _call_deepseek(raw_text)
    except Exception as e:
        return {'receipt_number': None, 'products': [],
                'error': f'Ошибка распознавания: {e}'}


def _try_deepseek_with_url(receipt_url: str) -> dict:
    """Fallback: ask DeepSeek to parse using just the URL (last resort)."""
    try:
        return _call_deepseek(f'Ссылка на чек: {receipt_url}')
    except Exception as e:
        return {'receipt_number': None, 'products': [],
                'error': f'Не удалось получить доступ к чеку по ссылке. Попробуйте скопировать текст чека и вставить сюда.'}


def parse_receipt_text(receipt_text: str) -> dict:
    """Parse receipt from user-provided text."""
    if not DEEPSEEK_API_KEY:
        return {'receipt_number': None, 'products': [], 'error': 'DeepSeek API key not configured'}

    try:
        return _call_deepseek(receipt_text)
    except Exception as e:
        return {'receipt_number': None, 'products': [], 'error': f'Parse error: {e}'}


def matches_our_products(product_name: str) -> bool:
    """Check if a product name matches our target products."""
    name_lower = product_name.lower().strip()
    for target in OUR_PRODUCTS:
        if target in name_lower:
            return True
    return False
