import os
import random
import threading
import uuid
from datetime import date, datetime, timezone
from collections import Counter

from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from models import db, Work
from ai_analyzer import analyze_work, analyze_title_only, generate_report, deep_analyze, visual_analyze

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, 'data')
os.makedirs(data_dir, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(data_dir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'archi-input-dev-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Upload directory
upload_dir = os.path.join(basedir, 'static', 'uploads')
os.makedirs(upload_dir, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)

with app.app_context():
    # Create tables and add missing columns for existing DBs
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing_cols = [col['name'] for col in inspector.get_columns('works')] if 'works' in inspector.get_table_names() else []
    db.create_all()

    new_columns = {
        'architect': 'VARCHAR(300) DEFAULT ""',
        'year': 'INTEGER',
        'country': 'VARCHAR(100) DEFAULT ""',
        'city': 'VARCHAR(100) DEFAULT ""',
        'usage': 'VARCHAR(100) DEFAULT ""',
        'structure': 'VARCHAR(100) DEFAULT ""',
        'ai_description': 'TEXT DEFAULT ""',
        'thumbnail_url': 'VARCHAR(2000) DEFAULT ""',
        'is_analyzed': 'BOOLEAN DEFAULT 0',
        'image_path': 'VARCHAR(500) DEFAULT ""',
        'visual_analysis': 'TEXT DEFAULT ""',
    }
    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols and existing_cols:
            try:
                db.session.execute(text(f'ALTER TABLE works ADD COLUMN {col_name} {col_type}'))
            except Exception:
                pass
    db.session.commit()


# ---------------------------------------------------------------------------
# Helper – Today's 3 + 1 selection
# ---------------------------------------------------------------------------
def get_today_picks():
    """Return (main_3, bonus_1) for today. Same seed = same result per day."""
    today_seed = int(date.today().strftime('%Y%m%d'))
    rng = random.Random(today_seed)

    unreviewed = Work.query.filter_by(is_reviewed=False).order_by(Work.created_at.desc()).all()
    reviewed = Work.query.filter_by(is_reviewed=True).order_by(Work.created_at.desc()).all()

    if len(unreviewed) >= 3:
        main_picks = rng.sample(unreviewed, 3)
    else:
        main_picks = list(unreviewed)

    bonus = None
    remaining_unreviewed = [w for w in unreviewed if w not in main_picks]
    if reviewed:
        bonus = rng.choice(reviewed)
    elif remaining_unreviewed:
        bonus = rng.choice(remaining_unreviewed)

    return main_picks, bonus


# ---------------------------------------------------------------------------
# Routes – Pages
# ---------------------------------------------------------------------------
@app.route('/')
def inbox():
    recent = Work.query.order_by(Work.created_at.desc()).limit(5).all()
    return render_template('inbox.html', recent=recent)


@app.route('/today')
def today():
    total = Work.query.count()
    if total == 0:
        return render_template('today.html', main_picks=[], bonus=None, empty=True)
    main_picks, bonus = get_today_picks()
    return render_template('today.html', main_picks=main_picks, bonus=bonus, empty=False)


@app.route('/library')
def library():
    q = request.args.get('q', '').strip()
    if q:
        search = f'%{q}%'
        works = Work.query.filter(
            db.or_(
                Work.title.ilike(search),
                Work.notes.ilike(search),
                Work.architect.ilike(search),
                Work.country.ilike(search),
                Work.city.ilike(search),
                Work.usage.ilike(search),
                Work.structure.ilike(search),
            )
        ).order_by(Work.created_at.desc()).all()
    else:
        works = Work.query.order_by(Work.created_at.desc()).all()
    return render_template('library.html', works=works, query=q)


@app.route('/report')
def report():
    works = Work.query.all()
    total = len(works)
    analyzed = sum(1 for w in works if w.is_analyzed)

    # Stats for charts
    countries = Counter(w.country for w in works if w.country)
    usages = Counter(w.usage for w in works if w.usage)
    structures = Counter(w.structure for w in works if w.structure)
    decades = Counter((w.year // 10) * 10 for w in works if w.year)

    return render_template('report.html',
                           total=total, analyzed=analyzed,
                           countries=dict(countries.most_common(10)),
                           usages=dict(usages.most_common(10)),
                           structures=dict(structures.most_common(10)),
                           decades=dict(sorted(decades.items())))


# ---------------------------------------------------------------------------
# Helper – Background AI analysis
# ---------------------------------------------------------------------------
def start_bg_analysis(work_id):
    """Start background AI analysis for a work."""
    def bg_analyze():
        with app.app_context():
            w = Work.query.get(work_id)
            if not w:
                return
            try:
                if w.url:
                    result = analyze_work(w.url, w.title)
                elif w.title:
                    result = analyze_title_only(w.title)
                else:
                    return
                if 'error' not in result:
                    w.title = result.get('title') or w.title
                    w.architect = result.get('architect', '')
                    w.year = result.get('year')
                    w.country = result.get('country', '')
                    w.city = result.get('city', '')
                    w.usage = result.get('usage', '')
                    w.structure = result.get('structure', '')
                    w.ai_description = result.get('ai_description', '')
                    w.thumbnail_url = result.get('thumbnail_url', '')
                    w.is_analyzed = True
                    w.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                    print(f'[AI] Auto-analysis complete for work #{work_id}: {w.title}')
                else:
                    print(f'[AI] Auto-analysis failed for work #{work_id}: {result["error"]}')
            except Exception as e:
                print(f'[AI] Auto-analysis error for work #{work_id}: {e}')

    thread = threading.Thread(target=bg_analyze, daemon=True)
    thread.start()


def _is_url(text):
    """Check if text looks like a URL."""
    return text.startswith(('http://', 'https://', 'www.'))


# ---------------------------------------------------------------------------
# Routes – Actions
# ---------------------------------------------------------------------------
@app.route('/add', methods=['POST'])
def add_work():
    # Smart input: single field auto-detects URL vs title
    smart_input = request.form.get('input', '').strip()
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()

    # If smart input is provided, auto-detect
    if smart_input and not title and not url:
        if _is_url(smart_input):
            url = smart_input if smart_input.startswith('http') else 'https://' + smart_input
        else:
            title = smart_input

    if not title and not url:
        return redirect(url_for('inbox', error='作品名またはURLを入力してください'))

    work = Work(title=title, url=url)

    # Handle image upload
    image_file = request.files.get('image')
    if image_file and image_file.filename and allowed_file(image_file.filename):
        ext = image_file.filename.rsplit('.', 1)[1].lower()
        unique_name = f'{uuid.uuid4().hex[:12]}.{ext}'
        save_path = os.path.join(upload_dir, unique_name)
        image_file.save(save_path)
        work.image_path = f'uploads/{unique_name}'

    db.session.add(work)
    db.session.commit()

    start_bg_analysis(work.id)

    return redirect(url_for('inbox', success='1', analyzing=work.id))


@app.route('/bulk_add', methods=['POST'])
def bulk_add():
    """Add multiple works from a text block (one URL or title per line)."""
    text = request.form.get('bulk_input', '').strip()
    if not text:
        return redirect(url_for('inbox', error='テキストを入力してください'))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    added = 0
    for line in lines[:20]:  # Max 20 at once
        if _is_url(line):
            url = line if line.startswith('http') else 'https://' + line
            work = Work(url=url)
        else:
            work = Work(title=line)
        db.session.add(work)
        db.session.commit()
        start_bg_analysis(work.id)
        added += 1

    return redirect(url_for('inbox', success='1', bulk_count=added))


@app.route('/quick_add')
def quick_add():
    """Bookmarklet endpoint – register current page via GET request."""
    url = request.args.get('url', '').strip()
    title = request.args.get('title', '').strip()

    if not url:
        return '<html><body><script>window.close();</script><p>URLが指定されていません</p></body></html>'

    # Check for duplicates
    existing = Work.query.filter_by(url=url).first()
    if existing:
        return f'''<html><head><meta charset="utf-8"><style>body{{font-family:sans-serif;text-align:center;padding:40px;background:#1a1a2e;color:#fff}}</style></head>
        <body><h2>⚠️ 既に登録済みです</h2><p>{existing.title or url[:60]}</p>
        <script>setTimeout(()=>window.close(),2000)</script></body></html>'''

    work = Work(title=title, url=url)
    db.session.add(work)
    db.session.commit()
    start_bg_analysis(work.id)

    return f'''<html><head><meta charset="utf-8"><style>body{{font-family:sans-serif;text-align:center;padding:40px;background:#1a1a2e;color:#fff}}h2{{color:#a78bfa}}</style></head>
    <body><h2>✅ 登録しました！</h2><p>{title or url[:60]}</p><p style="color:#888">AI分析を開始しました…</p>
    <script>setTimeout(()=>window.close(),2000)</script></body></html>'''


@app.route('/update_notes', methods=['POST'])
def update_notes():
    data = request.get_json()
    work_id = data.get('id')
    notes = data.get('notes', '')

    work = Work.query.get_or_404(work_id)
    work.notes = notes
    work.is_reviewed = True
    work.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'status': 'ok'})


@app.route('/status/<int:work_id>')
def work_status(work_id):
    """Check if a work has been analyzed (for polling)."""
    work = Work.query.get_or_404(work_id)
    return jsonify({
        'is_analyzed': work.is_analyzed,
        'title': work.title,
        'architect': work.architect,
        'year': work.year,
        'country': work.country,
    })


@app.route('/delete/<int:work_id>', methods=['POST'])
def delete_work(work_id):
    work = Work.query.get_or_404(work_id)
    db.session.delete(work)
    db.session.commit()
    return redirect(request.referrer or url_for('library'))


@app.route('/analyze/<int:work_id>', methods=['POST'])
def analyze(work_id):
    """Run Gemini analysis on a single work."""
    work = Work.query.get_or_404(work_id)

    if work.url:
        result = analyze_work(work.url, work.title)
    elif work.title:
        result = analyze_title_only(work.title)
    else:
        return jsonify({'status': 'error', 'message': 'URLまたは作品名が必要です'})

    if 'error' in result:
        return jsonify({'status': 'error', 'message': result['error']})

    # Update work with AI results
    work.title = result.get('title') or work.title
    work.architect = result.get('architect', '')
    work.year = result.get('year')
    work.country = result.get('country', '')
    work.city = result.get('city', '')
    work.usage = result.get('usage', '')
    work.structure = result.get('structure', '')
    work.ai_description = result.get('ai_description', '')
    work.thumbnail_url = result.get('thumbnail_url', '')
    work.is_analyzed = True
    work.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': work.to_dict()})


@app.route('/generate_report', methods=['POST'])
def gen_report():
    """Generate a comprehensive report using Gemini."""
    works = Work.query.filter_by(is_analyzed=True).all()
    if not works:
        return jsonify({'status': 'error', 'message': '分析済みの作品がありません'})

    # Get custom prompt from request body
    data = request.get_json(silent=True) or {}
    custom_prompt = data.get('prompt', '')

    works_data = [w.to_dict() for w in works]
    report_text = generate_report(works_data, custom_prompt=custom_prompt)
    return jsonify({'status': 'ok', 'report': report_text})


@app.route('/deep_analyze/<int:work_id>', methods=['POST'])
def deep_analyze_work(work_id):
    """Deep analysis of a single work with a user-provided prompt."""
    work = Work.query.get_or_404(work_id)
    data = request.get_json(silent=True) or {}
    user_prompt = data.get('prompt', '')

    if not user_prompt:
        return jsonify({'status': 'error', 'message': '質問を入力してください'})

    work_data = work.to_dict()
    result_text = deep_analyze(work_data, user_prompt)
    return jsonify({'status': 'ok', 'result': result_text})


@app.route('/visual_analyze/<int:work_id>', methods=['POST'])
def visual_analyze_work(work_id):
    """Run visual analysis on an uploaded image."""
    work = Work.query.get_or_404(work_id)

    # Determine image source: uploaded file or OG image URL
    image_data = None
    image_mime = 'image/jpeg'

    if work.image_path:
        img_path = os.path.join(basedir, 'static', work.image_path)
        if os.path.exists(img_path):
            with open(img_path, 'rb') as f:
                image_data = f.read()
            ext = work.image_path.rsplit('.', 1)[1].lower()
            mime_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}
            image_mime = mime_map.get(ext, 'image/jpeg')
    elif work.thumbnail_url:
        try:
            import requests as req
            resp = req.get(work.thumbnail_url, timeout=10)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            if ct.startswith('image/'):
                image_data = resp.content
                image_mime = ct
        except Exception:
            pass

    if not image_data:
        return jsonify({'status': 'error', 'message': '画像が見つかりません'})

    result_text = visual_analyze(image_data, image_mime, existing_title=work.title)
    work.visual_analysis = result_text
    work.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'status': 'ok', 'result': result_text})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
