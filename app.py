import sqlite3
from flask import Flask, render_template, request, jsonify
from database import init_db, add_workout, get_all_workouts, get_max_weight, get_exercise_history
from datetime import datetime, timedelta

app = Flask(__name__)
DB = 'fitscript.db'
MUSCLE_GROUPS = {'chest', 'back', 'legs', 'shoulders', 'arms', 'core'}

# Ensure tables exist even when running via `flask run` / gunicorn
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/log_workout', methods=['POST'])
def log_workout():
    data = request.get_json()
    # Expects: {exercise, muscle_group, date, sets: [{reps, weight}, ...]}
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

    exercise = data['exercise'].strip()
    muscle_group = data['muscle_group'].strip()
    date = data['date'].strip()

    if not exercise or len(exercise) < 2:
        return jsonify({'error': 'Exercise name is too short'}), 400
    if not muscle_group or muscle_group.lower() not in MUSCLE_GROUPS:
        return jsonify({'error': 'Invalid muscle group'}), 400

    prev_max = get_max_weight(exercise)
    is_pr = prev_max is None  # first time logging this exercise counts as a PR

    for i, s in enumerate(data['sets']):
        if not isinstance(s, dict):
            return jsonify({'error': f'Invalid set at index {i}'}), 400
        if 'reps' not in s or 'weight' not in s:
            return jsonify({'error': f'Missing reps/weight in set {i + 1}'}), 400
        try:
            reps = int(s['reps'])
            w = float(s['weight'])
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid reps/weight in set {i + 1}'}), 400
        if reps <= 0 or w < 0:
            return jsonify({'error': f'Invalid reps/weight in set {i + 1}'}), 400

        if prev_max is not None and w > prev_max:
            is_pr = True
        add_workout(exercise, muscle_group, 1, reps, w, date)

    return jsonify({'message': 'Logged!', 'is_pr': is_pr}), 201

@app.route('/get_workouts', methods=['GET'])
def get_workouts():
    workouts = get_all_workouts()
    return jsonify({'workouts': [
        {'id': w[0], 'exercise': w[1], 'muscle_group': w[2], 'sets': w[3], 'reps': w[4], 'weight': w[5], 'date': w[6]}
        for w in workouts
    ]})

@app.route('/delete_workout/<int:workout_id>', methods=['DELETE'])
def delete_workout(workout_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('DELETE FROM workouts WHERE id = ?', (workout_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'}), 200

@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    return jsonify(analyze(get_all_workouts()))

@app.route('/stats', methods=['GET'])
def get_stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT SUM(sets * reps * weight) FROM workouts')
    total_volume = c.fetchone()[0]
    c.execute('SELECT DISTINCT date FROM workouts ORDER BY date DESC')
    dates = [row[0] for row in c.fetchall()]
    conn.close()

    streak = 0
    if dates:
        today = datetime.today().date()
        date_set = {datetime.strptime(d, '%Y-%m-%d').date() for d in dates}
        check = today if today in date_set else today - timedelta(days=1)
        while check in date_set:
            streak += 1
            check -= timedelta(days=1)

    return jsonify({
        'streak': streak,
        'total_sessions': len(dates),
        'total_volume': int(total_volume or 0)
    })

@app.route('/progress', methods=['GET'])
def get_progress():
    exercise = request.args.get('exercise', '').strip()
    if not exercise:
        return jsonify([])
    rows = get_exercise_history(exercise)
    return jsonify([{'date': r[0], 'weight': r[1]} for r in rows])

def analyze(rows):
    if not rows:
        return [{'type': 'info', 'message': 'Log your first workout to get suggestions'}]

    today = datetime.today()
    workouts = [
        {'exercise': r[1], 'muscle_group': r[2].lower(), 'sets': r[3], 'reps': r[4], 'weight': r[5],
         'date': datetime.strptime(r[6], '%Y-%m-%d')}
        for r in rows
    ]
    suggestions = []

    # 1. NEGLECTED MUSCLE GROUPS
    # Only flag muscles the user has actually trained — show the single most neglected one
    trained = set(w['muscle_group'] for w in workouts)
    most_neglected, most_days = None, 0
    for group in trained:
        last = max(w['date'] for w in workouts if w['muscle_group'] == group)
        days = (today - last).days
        if days >= 5 and days > most_days:
            most_neglected, most_days = group, days
    if most_neglected:
        suggestions.append({'type': 'warning', 'message': f'{most_neglected.title()} hasn\'t been trained in {most_days} days — time to hit it.'})

    # 2. OVERTRAINING
    # Count distinct training days per muscle group (rows are sets)
    for group in trained:
        days = sorted({w['date'].date() for w in workouts if w['muscle_group'] == group}, reverse=True)
        if len(days) >= 3:
            if (today.date() - days[2]).days <= 3:
                suggestions.append({'type': 'warning', 'message': f'{group.title()} trained 3x in 3 days — give it a rest today.'})

    # 3. PROGRESSION STALL — group sets by date, compare max weight per session
    for exercise in set(w['exercise'].lower() for w in workouts):
        rows = sorted([w for w in workouts if w['exercise'].lower() == exercise], key=lambda x: x['date'], reverse=True)
        # Group into sessions by date
        sessions_by_date = {}
        for w in rows:
            d = w['date']
            if d not in sessions_by_date:
                sessions_by_date[d] = []
            sessions_by_date[d].append(w)
        session_dates = sorted(sessions_by_date.keys(), reverse=True)
        if len(session_dates) >= 3:
            max_weights = [max(w['weight'] for w in sessions_by_date[d]) for d in session_dates[:3]]
            if max_weights[0] == max_weights[1] == max_weights[2]:
                suggestions.append({'type': 'warning', 'message': f'{exercise.title()} — same weight for 3 sessions. Try adding 5 lbs.'})

    if not suggestions:
        suggestions.append({'type': 'info', 'message': 'Training looks solid. Keep the consistency going.'})

    return suggestions

if __name__ == '__main__':
    app.run(debug=True)
