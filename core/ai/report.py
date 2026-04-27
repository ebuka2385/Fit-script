import os
from datetime import datetime
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = """You are an elite strength and conditioning coach with 20 years of experience working with powerlifters, athletes, and recreational lifters.

You are given a snapshot of an athlete's current training data. Write a personalised coaching report that is direct, specific, and actionable. Use the athlete's actual numbers — do not be vague.

Structure your response with exactly these five sections, each on its own line with the header in bold:

**TODAY'S TRAINING CALL**
One clear directive: what they should train today and why, or whether to rest. Name specific muscle groups.

**RECOVERY STATUS**
For each muscle group, state whether it is ready or recovering, and by how much. Flag anything that needs attention.

**STRENGTH PROGRESSION**
Comment on their lift numbers and which tier they are in (Untrained / Novice / Intermediate / Advanced / Elite). If you see a trend, name it. Give a concrete next target.

**INJURY RISK ALERTS**
Be direct about any muscle groups showing high ACWR or consecutive training concern. If everything looks fine, say so briefly.

**COACH'S SUMMARY**
Two or three sentences. Biggest win right now. Most important thing to fix. Tone: honest, encouraging, professional.

Rules:
- Under 450 words total
- Use actual numbers from the data
- Never say "based on your data" — just say it directly
- No bullet points, no em-dashes for lists — write in short punchy sentences
- Sound like a real coach texting an athlete, not a report generator"""

USER_TEMPLATE = """Athlete training snapshot — {date}

RECOVERY FORECAST (fatigue cleared / days until ready):
{recovery}

ACUTE:CHRONIC WORKLOAD RATIOS:
{acwr}

INJURY RISK SCORES (0-100):
{injury_risk}

ESTIMATED 1RM & STRENGTH LEVEL:
{strength}

VOLUME DISTRIBUTION (total lbs lifted):
{volume}

RECENT TRAINING (last 14 days):
{recent}"""


def _fmt_recovery(data: dict) -> str:
    if not data:
        return "No data yet."
    lines = []
    for muscle, d in data.items():
        status = "READY" if d['days_until_ready'] == 0 else f"ready {d['ready_label']}"
        lines.append(f"  {muscle.capitalize()}: {d['pct_recovered']}% cleared — {status} (trained {d['days_since']}d ago)")
    return "\n".join(lines)


def _fmt_acwr(data: dict) -> str:
    if not data:
        return "No data yet."
    lines = []
    for muscle, d in data.items():
        lines.append(f"  {muscle.capitalize()}: {d['acwr']} ({d['status']})")
    return "\n".join(lines)


def _fmt_injury(data: dict) -> str:
    if not data:
        return "No data yet."
    lines = []
    for muscle, d in data.items():
        lines.append(f"  {muscle.capitalize()}: {d['risk_score']}/100 — {d['status']}")
    return "\n".join(lines)


def _fmt_strength(orm_data: dict, bodyweight: float | None) -> str:
    if not orm_data:
        return "No lifts logged yet."
    STANDARDS = {
        'bench press':        [0.50, 0.75, 1.00, 1.50, 2.00],
        'incline bench press':[0.40, 0.60, 0.85, 1.25, 1.65],
        'squat':              [0.75, 1.25, 1.50, 2.00, 2.50],
        'deadlift':           [1.00, 1.50, 2.00, 2.50, 3.00],
        'romanian deadlift':  [0.75, 1.00, 1.50, 2.00, 2.50],
        'overhead press':     [0.35, 0.55, 0.75, 1.10, 1.40],
        'barbell row':        [0.50, 0.65, 0.90, 1.20, 1.50],
        'pull-up':            [0.00, 0.10, 0.30, 0.60, 1.00],
        'leg press':          [1.00, 1.75, 2.50, 3.25, 4.00],
    }
    LEVELS = ['Untrained', 'Novice', 'Intermediate', 'Advanced', 'Elite']
    lines = []
    for ex, orm in orm_data.items():
        key = next((k for k in STANDARDS if ex.lower() == k or k in ex.lower()), None)
        if key and bodyweight:
            ratio = orm / bodyweight
            level = 0
            for i, std in enumerate(STANDARDS[key]):
                if ratio >= std:
                    level = i
            next_std = STANDARDS[key][level + 1] if level < 4 else None
            next_lbs = f" → {round(next_std * bodyweight)} lbs to reach {LEVELS[level+1]}" if next_std else " (Elite)"
            lines.append(f"  {ex}: {orm} lbs est. 1RM — {LEVELS[level]}{next_lbs}")
        else:
            lines.append(f"  {ex}: {orm} lbs est. 1RM")
    return "\n".join(lines) if lines else "No compound lifts tracked yet."


def _fmt_volume(radar: dict) -> str:
    if not radar:
        return "No data yet."
    return "  " + ", ".join(f"{m.capitalize()}: {v:,} lbs" for m, v in radar.items() if v > 0)


def _fmt_recent(workouts: list) -> str:
    from datetime import datetime, timedelta
    cutoff = datetime.today() - timedelta(days=14)
    recent = [w for w in workouts if w['date'] >= cutoff]
    if not recent:
        return "No sessions in the last 14 days."
    by_date = {}
    for w in recent:
        d = w['date'].strftime('%b %d')
        by_date.setdefault(d, set()).add(w['muscle_group'])
    return "  " + " | ".join(
        f"{date}: {', '.join(sorted(muscles))}"
        for date, muscles in sorted(by_date.items())
    )


def generate_training_report(
    workouts: list,
    recovery: dict,
    acwr: dict,
    injury_risk: dict,
    orm_data: dict,
    radar: dict,
    bodyweight: float | None = None,
) -> str:
    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=600,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human",  USER_TEMPLATE),
    ])

    chain  = prompt | llm
    result = chain.invoke({
        "date":        datetime.today().strftime("%B %d, %Y"),
        "recovery":    _fmt_recovery(recovery),
        "acwr":        _fmt_acwr(acwr),
        "injury_risk": _fmt_injury(injury_risk),
        "strength":    _fmt_strength(orm_data, bodyweight),
        "volume":      _fmt_volume(radar),
        "recent":      _fmt_recent(workouts),
    })
    return result.content
