import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta

WILKS_A = [-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08]

def epley_1rm(weight, reps):
    if reps == 1:
        return float(weight)
    return float(weight) * (1 + reps / 30.0)

def wilks_coefficient(bodyweight_kg):
    """Wilks coefficient for bodyweight normalisation (male formula)."""
    bw = bodyweight_kg
    denom = sum(WILKS_A[i] * (bw ** i) for i in range(6))
    return 500.0 / denom if denom != 0 else 0.0

def compute_1rm_history(workouts, exercise):
    """Best estimated 1RM per session for a given exercise."""
    sessions = defaultdict(list)
    for w in workouts:
        if w['exercise'].lower() == exercise.lower():
            sessions[w['date']].append(epley_1rm(w['weight'], w['reps']))
    return sorted(
        [{'date': d.strftime('%Y-%m-%d'), 'orm': round(max(vals), 1)}
         for d, vals in sessions.items()],
        key=lambda x: x['date']
    )

def poly_regression(history, future_days=(14, 28, 56)):
    """
    Fit degree-2 polynomial to 1RM history.
    Returns actual points + predicted future points + confidence band.
    """
    if len(history) < 2:
        return None

    dates = [datetime.strptime(p['date'], '%Y-%m-%d') for p in history]
    origin = dates[0]
    x = np.array([(d - origin).days for d in dates], dtype=float)
    y = np.array([p['orm'] for p in history], dtype=float)

    degree = min(2, len(x) - 1)
    coeffs = np.polyfit(x, y, degree)
    poly   = np.poly1d(coeffs)

    # Residuals → std for confidence band
    y_hat = poly(x)
    residuals = y - y_hat
    std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    # Actual curve points (one per session)
    actual = [{'date': p['date'], 'orm': p['orm'], 'fitted': round(float(poly(xi)), 1)}
              for p, xi in zip(history, x)]

    # Future predictions
    last_x = float(x[-1])
    last_date = dates[-1]
    predictions = []
    for days in future_days:
        fx = last_x + days
        pred = float(poly(fx))
        predictions.append({
            'date': (last_date + timedelta(days=days)).strftime('%Y-%m-%d'),
            'label': f'+{days}d',
            'predicted_1rm': round(pred, 1),
            'lower': round(pred - 1.96 * std, 1),
            'upper': round(pred + 1.96 * std, 1)
        })

    return {
        'actual': actual,
        'predictions': predictions,
        'std': round(std, 2),
        'degree': degree
    }

def compute_current_1rms(workouts):
    """Latest estimated 1RM for every exercise with at least one logged session."""
    result = {}
    for ex in {w['exercise'] for w in workouts}:
        history = compute_1rm_history(workouts, ex)
        if history:
            result[ex] = history[-1]['orm']
    return result

def compute_all_predictions(workouts):
    exercises = {w['exercise'] for w in workouts}
    result = {}
    for ex in exercises:
        history = compute_1rm_history(workouts, ex)
        if len(history) >= 2:
            reg = poly_regression(history)
            if reg:
                result[ex] = {
                    'current_1rm': history[-1]['orm'],
                    'regression': reg
                }
    return result
