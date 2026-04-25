import sqlite3

DB = "fitscript.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
       CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercise TEXT NOT NULL,
            muscle_group TEXT NOT NULL,
            sets INTEGER NOT NULL,
            reps INTEGER NOT NULL,
            weight REAL NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_workout(exercise, muscle_group, sets, reps, weight, date):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO workouts (exercise, muscle_group, sets, reps, weight, date) VALUES (?, ?, ?, ?, ?, ?)',
              (exercise, muscle_group, sets, reps, weight, date))
    conn.commit()
    conn.close()

def get_all_workouts():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM workouts ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_max_weight(exercise):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT MAX(weight) FROM workouts WHERE LOWER(exercise) = LOWER(?)', (exercise,))
    result = c.fetchone()[0]
    conn.close()
    return result

def get_exercise_history(exercise):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT date, MAX(weight) FROM workouts WHERE LOWER(exercise) = LOWER(?) GROUP BY date ORDER BY date ASC', (exercise,))
    rows = c.fetchall()
    conn.close()
    return rows
