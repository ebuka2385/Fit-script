import math
from datetime import datetime, timedelta
from collections import defaultdict

def parse_workouts(rows):
    workouts = []
    for r in rows:
        try:
            workouts.append({
                'id': r[0], 'exercise': r[1], 'muscle_group': r[2].lower(),
                'sets': r[3], 'reps': r[4], 'weight': r[5],
                'date': datetime.strptime(r[6], '%Y-%m-%d'),
                'volume': r[3] * r[4] * r[5]
            })
        except Exception:
            continue
    return workouts

def rolling_volume(workouts, muscle, days, anchor):
    cutoff = anchor - timedelta(days=days)
    return sum(w['volume'] for w in workouts
               if w['muscle_group'] == muscle and cutoff <= w['date'] <= anchor)

def compute_acwr(workouts):
    if not workouts:
        return {}
    muscles = {w['muscle_group'] for w in workouts}
    today = max(w['date'] for w in workouts)
    result = {}
    for muscle in muscles:
        acute = rolling_volume(workouts, muscle, 7, today)
        chronic = rolling_volume(workouts, muscle, 28, today)
        acwr = round(acute / chronic, 3) if chronic > 0 else (1.0 if acute == 0 else 2.0)
        result[muscle] = {
            'acwr': acwr,
            'acute_load': round(acute),
            'chronic_load': round(chronic),
            'status': acwr_status(acwr)
        }
    return result

def acwr_status(acwr):
    if acwr < 0.8:
        return 'undertrained'
    if acwr <= 1.3:
        return 'optimal'
    if acwr <= 1.5:
        return 'caution'
    return 'danger'

def compute_banister(workouts, muscle):
    """
    Banister Fitness-Fatigue model.
    Fitness decays with τ=45 days, fatigue with τ=15 days.
    Returns list of {date, fitness, fatigue, performance} over training history
    plus a 30-day decay tail so the curves visibly fall off after the last session.
    """
    TAU_FITNESS = 45.0
    TAU_FATIGUE = 15.0
    K_FITNESS   = 1.0
    K_FATIGUE   = 2.0
    TAIL_DAYS   = 30      # project this many days past the last workout

    muscle_workouts = sorted(
        [w for w in workouts if w['muscle_group'] == muscle],
        key=lambda x: x['date']
    )
    if not muscle_workouts:
        return []

    start = muscle_workouts[0]['date']
    end   = muscle_workouts[-1]['date'] + timedelta(days=TAIL_DAYS)
    days  = (end - start).days + 1

    # Daily TRIMP (volume load as impulse)
    daily = defaultdict(float)
    for w in muscle_workouts:
        daily[(w['date'] - start).days] += w['volume']

    fitness  = 0.0
    fatigue  = 0.0
    results  = []
    for d in range(days):
        trimp = daily.get(d, 0.0)
        decay_f = (1 - 1 / TAU_FITNESS)
        decay_h = (1 - 1 / TAU_FATIGUE)
        fitness = fitness * decay_f + trimp
        fatigue = fatigue * decay_h + trimp
        perf    = fitness * K_FITNESS - fatigue * K_FATIGUE
        date_str = (start + timedelta(days=d)).strftime('%Y-%m-%d')
        results.append({
            'date': date_str,
            'fitness': round(fitness, 2),
            'fatigue': round(fatigue, 2),
            'performance': round(perf, 2)
        })
    return results

def compute_injury_risk(workouts):
    if not workouts:
        return {}
    muscles = {w['muscle_group'] for w in workouts}
    today = max(w['date'] for w in workouts)
    acwr_data = compute_acwr(workouts)
    result = {}

    for muscle in muscles:
        acwr = acwr_data[muscle]['acwr']

        # ACWR score (0-100)
        if acwr <= 1.3:
            acwr_score = max(0, (acwr - 0.8) / 0.5) * 30
        else:
            acwr_score = 30 + min(70, ((acwr - 1.3) / 0.7) * 70)

        # Volume spike score: compare last 7 days vs prior 7 days
        last7  = rolling_volume(workouts, muscle, 7, today)
        prior7 = rolling_volume(workouts, muscle, 7, today - timedelta(days=7))
        if prior7 > 0:
            spike_ratio = last7 / prior7
            spike_score = min(100, max(0, (spike_ratio - 1.3) / 0.7 * 100))
        else:
            spike_score = 0

        # Frequency score: consecutive days trained
        trained_days = sorted(
            {w['date'].date() for w in workouts if w['muscle_group'] == muscle},
            reverse=True
        )
        consecutive = 0
        if trained_days:
            check = trained_days[0]
            for d in trained_days:
                if (check - d).days <= 1:
                    consecutive += 1
                    check = d
                else:
                    break
        freq_score = min(100, consecutive * 20)

        risk = round(0.5 * acwr_score + 0.25 * spike_score + 0.25 * freq_score)
        result[muscle] = {
            'risk_score': int(min(100, max(0, risk))),
            'acwr': acwr,
            'status': acwr_status(acwr),
            'consecutive_days': consecutive
        }
    return result

def compute_volume_timeline(workouts, weeks=8):
    if not workouts:
        return {}
    muscles = {w['muscle_group'] for w in workouts}
    today = max(w['date'] for w in workouts)
    result = defaultdict(dict)
    for i in range(weeks):
        week_end   = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        label = week_start.strftime('%b %d')
        for muscle in muscles:
            vol = sum(w['volume'] for w in workouts
                      if w['muscle_group'] == muscle
                      and week_start <= w['date'] <= week_end)
            result[muscle][label] = round(vol)
    # Reverse so oldest week is first
    for muscle in result:
        result[muscle] = dict(reversed(list(result[muscle].items())))
    return dict(result)

def compute_radar(workouts):
    muscles = ['chest', 'back', 'legs', 'shoulders', 'arms', 'core']
    totals = defaultdict(float)
    for w in workouts:
        totals[w['muscle_group']] += w['volume']
    return {m: round(totals.get(m, 0)) for m in muscles}

def compute_recovery_forecast(workouts):
    """
    For each muscle group, project when fatigue decays to ≤30% of its
    post-session peak — the point we call "ready to train again."
    Uses the same Banister τ=15d fatigue decay constant.
    """
    READY_THRESHOLD = 0.30
    TAU_FATIGUE     = 15.0
    decay           = 1 - 1 / TAU_FATIGUE

    muscles = {w['muscle_group'] for w in workouts}
    today   = datetime.today()
    result  = {}

    for muscle in muscles:
        muscle_ws = [w for w in workouts if w['muscle_group'] == muscle]
        if not muscle_ws:
            continue

        last_date  = max(w['date'] for w in muscle_ws).date()
        days_since = (today.date() - last_date).days
        earliest   = min(w['date'] for w in muscle_ws).date()

        # Accumulate fatigue up to and including the last workout day
        daily_vol = defaultdict(float)
        for w in muscle_ws:
            daily_vol[(w['date'].date() - earliest).days] += w['volume']

        fatigue = 0.0
        for d in range((last_date - earliest).days + 1):
            fatigue = fatigue * decay + daily_vol.get(d, 0.0)
        peak_fatigue = fatigue

        if peak_fatigue <= 0:
            continue

        current_fatigue = peak_fatigue * (decay ** days_since)
        target_fatigue  = peak_fatigue * READY_THRESHOLD

        if current_fatigue <= target_fatigue:
            days_until_ready = 0
        else:
            days_until_ready = max(0, math.ceil(
                math.log(target_fatigue / current_fatigue) / math.log(decay)
            ))

        # % of excess fatigue (above threshold) that has cleared
        excess_peak   = max(peak_fatigue - target_fatigue, 1)
        excess_now    = max(current_fatigue - target_fatigue, 0)
        pct_recovered = min(100, round((1 - excess_now / excess_peak) * 100))

        ready_dt = (today + timedelta(days=days_until_ready)).date()

        result[muscle] = {
            'days_until_ready': days_until_ready,
            'ready_date':       str(ready_dt),
            'ready_label':      'Today' if days_until_ready == 0 else ready_dt.strftime('%b %d'),
            'pct_recovered':    pct_recovered,
            'last_trained':     last_date.strftime('%b %d'),
            'days_since':       days_since,
        }

    return result
