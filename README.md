# Fit-script

Fit-script is a lightweight Flask + SQLite workout tracker that helps users:
- Log sets, reps, and weight by exercise and muscle group
- View progress and workout stats (streak, sessions, volume)
- Receive training suggestions (undertraining, overtraining, stalled lifts)

## Tech Stack

- Python 3
- Flask
- SQLite
- HTML/CSS/JS frontend (served from `templates/index.html`)

## Run Locally

```bash
./run.sh
```

Or manually:

```bash
pip3 install flask
python3 app.py
```

Then open: `http://localhost:5000`

## Current Feature Set

- Log workouts with sets, reps, and weight
- View workout history and progression trends
- Track consistency metrics like streak and volume
- Get training feedback based on workout patterns

## Fit-script Feedback (What Makes This an A Project)

To move this project from good to excellent, prioritize one of the following major upgrades:

### Option 1: Multi-user + Competition Layer

Add support for multiple users and social competition.

Suggested scope:
- User accounts (signup/login, hashed passwords, auth sessions)
- Per-user workout ownership and data isolation
- Leaderboards (weekly volume, consistency streaks, PR count)
- Challenges (e.g., "Most sessions this week")
- Friend or team mode for private competition groups

Why this helps:
- Turns Fit-script into a product people return to daily
- Adds retention and engagement through social motivation

### Option 2: Analytics + Prediction Layer (Health API Driven)

Add an analytics engine that combines Fit-script workouts with health app/API signals (sleep, HRV, resting heart rate, readiness, recovery).

Suggested scope:
- Data connector layer for Apple Health, Google Fit, or wearables APIs
- Feature pipeline that combines workout volume/intensity with recovery signals
- Injury-risk prediction (fatigue + load spikes + poor recovery trends)
- Workout/lift improvement recommendations (load adjustments, deload timing)
- Confidence scoring + explanations for each recommendation

Why this helps:
- Introduces intelligent coaching, not just tracking
- Demonstrates applied data science and product thinking

## Suggested Build Order

1. Add a user model + authentication
2. Refactor DB schema for multi-user support
3. Add API versioning (`/api/v1/...`) and validation
4. Implement either competition features or analytics predictions
5. Add tests for core routes and model logic
6. Deploy (Render/Fly.io) with environment-based config

## Security/Quality Upgrades

- Move `SECRET_KEY` and config values to environment variables
- Add input rate limiting and stronger request validation
- Add basic test coverage (`pytest`) for key endpoints
- Add `.gitignore` to exclude `__pycache__/`, `*.pyc`, `.DS_Store`, and `fitscript.db`

## Security Note (Do Not Expose Secrets)

Before pushing code, make sure you do **not** commit or publicly document:
- API keys, tokens, passwords, or private URLs
- Local database files or personal data exports
- `.env` files with real credentials
- Internal-only routes/endpoints that are not intended as public APIs

Use environment variables for sensitive values and keep only non-secret examples in the repo (for example, `.env.example`).

## License

Add a license file (MIT is common for student/open projects).
