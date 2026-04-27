import sqlite3
from datetime import datetime

DB = "fitscript.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exercise TEXT NOT NULL,
        muscle_group TEXT NOT NULL,
        sets INTEGER NOT NULL,
        reps INTEGER NOT NULL,
        weight REAL NOT NULL,
        date TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        generated_at TEXT NOT NULL,
        report_text TEXT NOT NULL
    )''')
    # Migration: add user_id to existing installations
    try:
        c.execute('ALTER TABLE workouts ADD COLUMN user_id INTEGER REFERENCES users(id)')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def save_report(user_id, report_text):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'INSERT INTO reports (user_id, generated_at, report_text) VALUES (?, ?, ?)',
        (user_id, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), report_text)
    )
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id

def get_reports(user_id, limit=20):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'SELECT id, generated_at, report_text FROM reports WHERE user_id = ? ORDER BY generated_at DESC LIMIT ?',
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'generated_at': r[1], 'report_text': r[2]} for r in rows]

def delete_report(report_id, user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('DELETE FROM reports WHERE id = ? AND user_id = ?', (report_id, user_id))
    conn.commit()
    conn.close()

def create_user(username, password_hash):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
              (username, password_hash, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return user_id

def get_user_by_username(username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, username, password_hash FROM users WHERE LOWER(username) = LOWER(?)', (username,))
    row = c.fetchone()
    conn.close()
    return row  # (id, username, password_hash) or None

def add_workout(exercise, muscle_group, sets, reps, weight, date, user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'INSERT INTO workouts (exercise, muscle_group, sets, reps, weight, date, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (exercise, muscle_group, sets, reps, weight, date, user_id)
    )
    conn.commit()
    conn.close()

def get_all_workouts(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'SELECT id, exercise, muscle_group, sets, reps, weight, date FROM workouts WHERE user_id = ? ORDER BY date DESC',
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_max_weight(exercise, user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'SELECT MAX(weight) FROM workouts WHERE LOWER(exercise) = LOWER(?) AND user_id = ?',
        (exercise, user_id)
    )
    result = c.fetchone()[0]
    conn.close()
    return result

def get_exercise_history(exercise, user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        'SELECT date, MAX(weight) FROM workouts WHERE LOWER(exercise) = LOWER(?) AND user_id = ? GROUP BY date ORDER BY date ASC',
        (exercise, user_id)
    )
    rows = c.fetchall()
    conn.close()
    return rows
