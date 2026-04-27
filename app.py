import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
load_dotenv()
from core.db import (init_db, create_user, get_user_by_username,
                     add_workout, get_all_workouts, get_max_weight, get_exercise_history,
                     save_report, get_reports, delete_report)
from datetime import datetime, timedelta
from core.analytics import (parse_workouts, compute_acwr, compute_banister,
                            compute_injury_risk, compute_volume_timeline, compute_radar,
                            compute_recovery_forecast)
from core.ai import generate_training_report
from core.ml import compute_all_predictions, compute_1rm_history, poly_regression, compute_current_1rms

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fitscript-dev-secret-2026')
DB = 'fitscript.db'
MUSCLE_GROUPS = {'chest', 'back', 'legs', 'shoulders', 'arms', 'core'}

init_db()

# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    """API routes — returns 401 JSON when unauthenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated

def page_login_required(f):
    """Page routes — redirects to /login when unauthenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET'])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html', error=None)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    user = get_user_by_username(username)
    if not user or not check_password_hash(user[2], password):
        return render_template('login.html', error='Invalid username or password.', tab='login')
    session.clear()
    session['user_id'] = user[0]
    session['username'] = user[1]
    return redirect(url_for('index'))

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    if len(username) < 3:
        return render_template('login.html', error='Username must be at least 3 characters.', tab='signup')
    if len(password) < 6:
        return render_template('login.html', error='Password must be at least 6 characters.', tab='signup')
    if get_user_by_username(username):
        return render_template('login.html', error='Username already taken.', tab='signup')
    user_id = create_user(username, generate_password_hash(password))
    session.clear()
    session['user_id'] = user_id
    session['username'] = username
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ── Page ──────────────────────────────────────────────────────────────────────

@app.route('/')
@page_login_required
def index():
    return render_template('index.html', username=session['username'])

# ── Workout API ───────────────────────────────────────────────────────────────

@app.route('/log_workout', methods=['POST'])
@login_required
def log_workout():
    data = request.get_json()
    required = ['exercise', 'muscle_group', 'date', 'sets']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400
    try:
        datetime.strptime(data['date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    if not data['sets']:
        return jsonify({'error': 'Add at least one set'}), 400

    exercise     = data['exercise'].strip()
    muscle_group = data['muscle_group'].strip()
    date         = data['date'].strip()
    user_id      = session['user_id']

    if len(exercise) < 2:
        return jsonify({'error': 'Exercise name is too short'}), 400
    if muscle_group.lower() not in MUSCLE_GROUPS:
        return jsonify({'error': 'Invalid muscle group'}), 400

    prev_max = get_max_weight(exercise, user_id)
    is_pr = prev_max is None

    for i, s in enumerate(data['sets']):
        if not isinstance(s, dict) or 'reps' not in s or 'weight' not in s:
            return jsonify({'error': f'Invalid set at index {i}'}), 400
        try:
            reps = int(s['reps'])
            w    = float(s['weight'])
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid reps/weight in set {i + 1}'}), 400
        if reps <= 0 or w < 0:
            return jsonify({'error': f'Invalid reps/weight in set {i + 1}'}), 400
        if prev_max is not None and w > prev_max:
            is_pr = True
        add_workout(exercise, muscle_group, 1, reps, w, date, user_id)

    return jsonify({'message': 'Logged!', 'is_pr': is_pr}), 201

@app.route('/get_workouts', methods=['GET'])
@login_required
def get_workouts():
    workouts = get_all_workouts(session['user_id'])
    return jsonify({'workouts': [
        {'id': w[0], 'exercise': w[1], 'muscle_group': w[2], 'sets': w[3], 'reps': w[4], 'weight': w[5], 'date': w[6]}
        for w in workouts
    ]})

@app.route('/delete_workout/<int:workout_id>', methods=['DELETE'])
@login_required
def delete_workout(workout_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('DELETE FROM workouts WHERE id = ? AND user_id = ?', (workout_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'}), 200

@app.route('/suggestions', methods=['GET'])
@login_required
def get_suggestions():
    return jsonify(analyze(get_all_workouts(session['user_id'])))

@app.route('/stats', methods=['GET'])
@login_required
def get_stats():
    user_id = session['user_id']
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT SUM(sets * reps * weight) FROM workouts WHERE user_id = ?', (user_id,))
    total_volume = c.fetchone()[0]
    c.execute('SELECT DISTINCT date FROM workouts WHERE user_id = ? ORDER BY date DESC', (user_id,))
    dates = [row[0] for row in c.fetchall()]
    conn.close()

    streak = 0
    if dates:
        today    = datetime.today().date()
        date_set = {datetime.strptime(d, '%Y-%m-%d').date() for d in dates}
        check    = today if today in date_set else today - timedelta(days=1)
        while check in date_set:
            streak += 1
            check  -= timedelta(days=1)

    return jsonify({'streak': streak, 'total_sessions': len(dates), 'total_volume': int(total_volume or 0)})

@app.route('/progress', methods=['GET'])
@login_required
def get_progress():
    exercise = request.args.get('exercise', '').strip()
    if not exercise:
        return jsonify([])
    rows = get_exercise_history(exercise, session['user_id'])
    return jsonify([{'date': r[0], 'weight': r[1]} for r in rows])

# ── Analytics API ─────────────────────────────────────────────────────────────

@app.route('/analytics/acwr', methods=['GET'])
@login_required
def get_acwr():
    return jsonify(compute_acwr(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/analytics/injury_risk', methods=['GET'])
@login_required
def get_injury_risk():
    return jsonify(compute_injury_risk(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/analytics/banister', methods=['GET'])
@login_required
def get_banister():
    muscle = request.args.get('muscle', '').strip().lower()
    if not muscle:
        return jsonify({'error': 'muscle param required'}), 400
    return jsonify(compute_banister(parse_workouts(get_all_workouts(session['user_id'])), muscle))

@app.route('/analytics/predict', methods=['GET'])
@login_required
def get_predict():
    exercise = request.args.get('exercise', '').strip()
    workouts = parse_workouts(get_all_workouts(session['user_id']))
    if exercise:
        history = compute_1rm_history(workouts, exercise)
        reg = poly_regression(history)
        if not reg:
            return jsonify({'error': 'Need at least 2 sessions'}), 400
        return jsonify({'exercise': exercise, 'current_1rm': history[-1]['orm'] if history else 0, 'regression': reg})
    return jsonify(compute_all_predictions(workouts))

@app.route('/analytics/volume_timeline', methods=['GET'])
@login_required
def get_volume_timeline():
    return jsonify(compute_volume_timeline(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/analytics/radar', methods=['GET'])
@login_required
def get_radar():
    return jsonify(compute_radar(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/analytics/recovery_forecast', methods=['GET'])
@login_required
def get_recovery_forecast():
    return jsonify(compute_recovery_forecast(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/analytics/all_1rm', methods=['GET'])
@login_required
def get_all_1rm():
    return jsonify(compute_current_1rms(parse_workouts(get_all_workouts(session['user_id']))))

@app.route('/ai/training_report', methods=['POST'])
@login_required
def get_training_report():
    if not os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_API_KEY') == 'your_api_key_here':
        return jsonify({'error': 'ANTHROPIC_API_KEY not configured in .env'}), 503
    body      = request.get_json() or {}
    bw        = body.get('bodyweight')
    bodyweight = float(bw) if bw else None
    workouts  = parse_workouts(get_all_workouts(session['user_id']))
    try:
        report = generate_training_report(
            workouts   = workouts,
            recovery   = compute_recovery_forecast(workouts),
            acwr       = compute_acwr(workouts),
            injury_risk= compute_injury_risk(workouts),
            orm_data   = compute_current_1rms(workouts),
            radar      = compute_radar(workouts),
            bodyweight = bodyweight,
        )
        report_id = save_report(session['user_id'], report)
        return jsonify({'report': report, 'report_id': report_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reports', methods=['GET'])
@login_required
def list_reports():
    return jsonify(get_reports(session['user_id']))

@app.route('/reports/<int:report_id>', methods=['DELETE'])
@login_required
def remove_report(report_id):
    delete_report(report_id, session['user_id'])
    return jsonify({'message': 'Deleted'})

# ── Suggestions engine ────────────────────────────────────────────────────────

def analyze(rows):
    if not rows:
        return [{'type': 'info', 'message': 'Log your first workout to get suggestions'}]

    today    = datetime.today()
    workouts = [
        {'exercise': r[1], 'muscle_group': r[2].lower(), 'sets': r[3], 'reps': r[4], 'weight': r[5],
         'date': datetime.strptime(r[6], '%Y-%m-%d')}
        for r in rows
    ]
    suggestions = []

    trained = set(w['muscle_group'] for w in workouts)
    most_neglected, most_days = None, 0
    for group in trained:
        last = max(w['date'] for w in workouts if w['muscle_group'] == group)
        days = (today - last).days
        if days >= 5 and days > most_days:
            most_neglected, most_days = group, days
    if most_neglected:
        suggestions.append({'type': 'warning', 'message': f'{most_neglected.title()} hasn\'t been trained in {most_days} days — time to hit it.'})

    for group in trained:
        days = sorted({w['date'].date() for w in workouts if w['muscle_group'] == group}, reverse=True)
        if len(days) >= 3 and (today.date() - days[2]).days <= 3:
            suggestions.append({'type': 'warning', 'message': f'{group.title()} trained 3x in 3 days — give it a rest today.'})

    for exercise in set(w['exercise'].lower() for w in workouts):
        ex_rows = sorted([w for w in workouts if w['exercise'].lower() == exercise], key=lambda x: x['date'], reverse=True)
        sessions_by_date = {}
        for w in ex_rows:
            sessions_by_date.setdefault(w['date'], []).append(w)
        session_dates = sorted(sessions_by_date.keys(), reverse=True)
        if len(session_dates) >= 3:
            max_weights = [max(w['weight'] for w in sessions_by_date[d]) for d in session_dates[:3]]
            if max_weights[0] == max_weights[1] == max_weights[2]:
                suggestions.append({'type': 'warning', 'message': f'{exercise.title()} — same weight for 3 sessions. Try adding 5 lbs.'})

    if not suggestions:
        suggestions.append({'type': 'info', 'message': 'Training looks solid. Keep the consistency going.'})

    return suggestions

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=True, port=port)
