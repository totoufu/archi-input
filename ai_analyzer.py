"""
AI Analyzer – Scrape URLs and extract architectural info via Gemini API.
"""
import json
import re
import time
import traceback

import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import errors as genai_errors, types as genai_types

import config

# ---------------------------------------------------------------------------
# Gemini client (singleton)
# ---------------------------------------------------------------------------
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _call_gemini(prompt: str, image_data: bytes = None, image_mime: str = 'image/jpeg', max_retries: int = 3) -> str:
    """Call Gemini API with retry logic for rate limits. Optionally include an image."""
    models_to_try = [config.GEMINI_MODEL, 'gemini-2.5-flash', 'gemini-2.0-flash']
    client = _get_client()

    # Build contents: text + optional image
    if image_data:
        contents = [
            genai_types.Part.from_text(text=prompt),
            genai_types.Part.from_bytes(data=image_data, mime_type=image_mime),
        ]
    else:
        contents = prompt

    for model in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                )
                return response.text.strip()
            except genai_errors.ClientError as e:
                if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                    wait_time = (attempt + 1) * 8
                    print(f'[AI] Rate limited on {model}, waiting {wait_time}s (attempt {attempt+1}/{max_retries})')
                    time.sleep(wait_time)
                    continue
                else:
                    raise
            except Exception:
                raise
        print(f'[AI] All retries exhausted for {model}, trying next model...')

    raise Exception('全てのモデルでAPIコールに失敗しました。しばらく待ってから再試行してください。')


# ---------------------------------------------------------------------------
# Web scraping helpers
# ---------------------------------------------------------------------------
def scrape_url(url: str) -> dict:
    """Fetch a URL and extract text content + OGP metadata."""
    result = {
        'text': '',
        'og_title': '',
        'og_description': '',
        'og_image': '',
        'page_title': '',
    }
    try:
        headers = {'User-Agent': config.USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Page title
        if soup.title:
            result['page_title'] = soup.title.get_text(strip=True)

        # OGP tags
        for tag in soup.find_all('meta', attrs={'property': True}):
            prop = tag.get('property', '')
            content = tag.get('content', '')
            if prop == 'og:title':
                result['og_title'] = content
            elif prop == 'og:description':
                result['og_description'] = content
            elif prop == 'og:image':
                result['og_image'] = content

        # Meta description fallback
        if not result['og_description']:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag:
                result['og_description'] = desc_tag.get('content', '')

        # Extract main text (limited to keep prompt size reasonable)
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Limit to ~3000 chars
        result['text'] = text[:3000]

    except Exception:
        traceback.print_exc()

    # Download OG image for multimodal analysis (outside main try-except)
    result['og_image_data'] = None
    result['og_image_mime'] = 'image/jpeg'
    if result['og_image']:
        try:
            headers = {'User-Agent': config.USER_AGENT}
            img_resp = requests.get(result['og_image'], headers=headers, timeout=10)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get('Content-Type', 'image/jpeg')
            mime = content_type.split(';')[0].strip()
            if mime.startswith('image/'):
                result['og_image_data'] = img_resp.content
                result['og_image_mime'] = mime
                print(f'[AI] Downloaded OG image: {len(img_resp.content)} bytes ({mime})')
        except Exception:
            print('[AI] Failed to download OG image, continuing without it')

    return result


# ---------------------------------------------------------------------------
# Gemini analysis
# ---------------------------------------------------------------------------
ANALYZE_PROMPT = """あなたは建築の専門家です。以下のWebページの情報から建築作品の詳細を抽出し、JSON形式で返してください。

## Webページ情報
- ページタイトル: {page_title}
- OGPタイトル: {og_title}
- OGP説明: {og_description}
- 本文抜粋:
{text}

## 出力JSON形式（必ずこの形式で返してください）
```json
{{
  "title": "作品名（正式名称）",
  "architect": "設計者/建築家の名前",
  "year": 竣工年（数値、不明なら null）,
  "country": "所在国",
  "city": "所在都市",
  "usage": "用途（住宅/美術館/教会/オフィス/集合住宅/公共施設/商業施設/その他）",
  "structure": "構造種別（RC造/鉄骨造/木造/石造/混構造/その他）",
  "description": "この建築作品の特徴を200〜400字程度で詳しく説明（設計意図、空間構成の特徴、素材・光の使い方、歴史的・建築史的な意義、周辺環境との関係性などに触れてください）"
}}
```

注意:
- 情報が不明な場合は null を入れてください
- JSONのみを返してください。コードブロックのマークダウン記法は不要です
- 必ず日本語で回答してください
- 画像が添付されている場合は、外観・ファサード・素材感・プロポーションなどの視覚的特徴もdescriptionに反映してください
"""

REPORT_PROMPT = """あなたは建築教育の専門家です。以下は、ユーザーが学習した建築事例のリストです。

## 登録済み事例一覧
{works_json}

## ユーザーからの追加指示
{custom_prompt}

## タスク
上記の「ユーザーからの追加指示」がある場合はそれを最優先で反映してください。
指示がない場合は、以下のデフォルト分析を行ってください:

1. **概要統計**: 総数、分析済み数、年代分布、地域分布
2. **偏り分析**: どの年代/国/用途/構造に偏っているか、どこが手薄か
3. **おすすめ**: 次に学ぶべき建築のジャンルや時代を3つ具体的に提案（作品名も含めて）
4. **週間のまとめ**: これまでの学習の傾向と成長ポイント

## 出力ルール
- 必ず日本語で、読みやすいマークダウン形式で出力してください
- 具体的な作品名をなるべく多く挙げてください
- 表面的な分析ではなく、建築学的に深い考察を含めてください
- 1500文字以上を目安にしてください"""


def analyze_work(url: str, existing_title: str = '') -> dict:
    """Analyze a URL and return structured architectural data."""
    scraped = scrape_url(url) if url else {}

    # Build prompt
    prompt = ANALYZE_PROMPT.format(
        page_title=scraped.get('page_title', existing_title or '不明'),
        og_title=scraped.get('og_title', ''),
        og_description=scraped.get('og_description', ''),
        text=scraped.get('text', '（URLなし。タイトル「{}」のみ提供）'.format(existing_title)),
    )

    try:
        raw_response = _call_gemini(
            prompt,
            image_data=scraped.get('og_image_data'),
            image_mime=scraped.get('og_image_mime', 'image/jpeg'),
        )

        raw = raw_response
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)

        return {
            'title': data.get('title', existing_title) or existing_title,
            'architect': data.get('architect') or '',
            'year': data.get('year'),
            'country': data.get('country') or '',
            'city': data.get('city') or '',
            'usage': data.get('usage') or '',
            'structure': data.get('structure') or '',
            'ai_description': data.get('description') or '',
            'thumbnail_url': scraped.get('og_image', ''),
        }
    except Exception as e:
        traceback.print_exc()
        return {
            'error': str(e),
            'title': scraped.get('og_title') or scraped.get('page_title') or existing_title,
            'thumbnail_url': scraped.get('og_image', ''),
        }


def generate_report(works_data: list, custom_prompt: str = '') -> str:
    """Generate a report from all works data, with optional custom prompt."""
    works_json = json.dumps(works_data, ensure_ascii=False, indent=2)
    prompt = REPORT_PROMPT.format(
        works_json=works_json,
        custom_prompt=custom_prompt or '（特になし）',
    )

    try:
        return _call_gemini(prompt)
    except Exception as e:
        traceback.print_exc()
        return f'レポート生成エラー: {str(e)}'


def analyze_title_only(title: str) -> dict:
    """Analyze a work by title alone (no URL)."""
    prompt = f"""あなたは建築の専門家です。「{title}」という建築作品について知っている情報をJSON形式で返してください。

## 出力JSON形式
```json
{{
  "title": "作品名（正式名称）",
  "architect": "設計者",
  "year": 竣工年（数値、不明なら null）,
  "country": "所在国",
  "city": "所在都市",
  "usage": "用途",
  "structure": "構造種別",
  "description": "特徴を200〜400字程度で詳しく説明（設計意図、空間構成、素材、歴史的意義など）"
}}
```
JSONのみを返してください。必ず日本語で。"""

    try:
        raw = _call_gemini(prompt)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        return {
            'title': data.get('title', title) or title,
            'architect': data.get('architect') or '',
            'year': data.get('year'),
            'country': data.get('country') or '',
            'city': data.get('city') or '',
            'usage': data.get('usage') or '',
            'structure': data.get('structure') or '',
            'ai_description': data.get('description') or '',
            'thumbnail_url': '',
        }
    except Exception as e:
        traceback.print_exc()
        return {'error': str(e), 'title': title}


def deep_analyze(work_data: dict, user_prompt: str) -> str:
    """Deep-dive analysis of a single work with a user-specified prompt."""
    work_info = json.dumps(work_data, ensure_ascii=False, indent=2)

    prompt = f"""あなたは建築の専門家であり、建築教育者です。

## 対象作品の情報
{work_info}

## ユーザーからの質問・分析指示
{user_prompt}

## 回答ルール
- 必ず日本語で回答してください
- 建築学的に深い考察を含めてください
- 他の建築作品との比較や関連性にも言及してください
- 具体的なエピソードや技術的詳細を含めてください
- マークダウン形式で、見出しを使って構造的に回答してください
- 1000文字以上を目安に、充実した回答をしてください"""

    try:
        return _call_gemini(prompt)
    except Exception as e:
        traceback.print_exc()
        return f'分析エラー: {str(e)}'


def visual_analyze(image_data: bytes, image_mime: str = 'image/jpeg', existing_title: str = '') -> str:
    """Analyze an architectural image visually using Gemini multimodal."""
    context = f'（作品名: {existing_title}）' if existing_title else ''

    prompt = f"""あなたは建築の専門家であり、建築写真の批評家です。
以下の建築物の画像を詳しく分析してください。{context}

## 分析してほしい観点
1. **ファサード・外観**: 建物の正面性、開口部のリズム、立面構成
2. **素材・テクスチャ**: 使用されている素材（コンクリート、ガラス、木、石、鉄骨等）とその質感
3. **光と影**: 自然光の取り入れ方、影の演出、照明計画
4. **プロポーション・スケール**: 建物の比例関係、人間との対比、ボリューム感
5. **構造表現**: 構造体が外観にどう現れているか、構造と意匠の関係
6. **周辺環境・ランドスケープ**: 周囲との関係性、アプローチ、配置計画
7. **建築史的位置づけ**: どの建築様式・潮流に属するか、影響を受けた/与えた建築家

## 出力ルール
- 必ず日本語で、マークダウン形式で出力してください
- 各観点に見出しをつけて構造的に記述してください
- 専門用語を使いつつも、学習者にわかりやすく解説してください
- 類似する他の建築作品にも言及してください
- 500〜1000字程度を目安にしてください"""

    try:
        return _call_gemini(prompt, image_data=image_data, image_mime=image_mime)
    except Exception as e:
        traceback.print_exc()
        return f'視覚分析エラー: {str(e)}'
