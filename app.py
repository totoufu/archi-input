import os
import random
import threading
from datetime import date, datetime, timezone
from collections import Counter

from flask import Flask, render_template, request, redirect, url_for, jsonify
from models import db, Work
from ai_analyzer import analyze_work, analyze_title_only, generate_report, deep_analyze

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
# Routes – Actions
# ---------------------------------------------------------------------------
@app.route('/add', methods=['POST'])
def add_work():
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()

    if not title and not url:
        return redirect(url_for('inbox', error='作品名またはURLを入力してください'))

    work = Work(title=title, url=url)
    db.session.add(work)
    db.session.commit()

    # Auto-analyze in background thread
    work_id = work.id
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

    return redirect(url_for('inbox', success='1', analyzing=work_id))


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


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
