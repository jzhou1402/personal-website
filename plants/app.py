import os
import sqlite3
import resend
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'plants.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS plants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                species TEXT,
                water_every_days INTEGER NOT NULL DEFAULT 7,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS waterings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL REFERENCES plants(id),
                watered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                health_status TEXT CHECK(health_status IN ('thriving','good','okay','struggling','bad')) DEFAULT 'good',
                notes TEXT
            );
        ''')


def send_alert_email(overdue_plants):
    api_key = os.getenv('RESEND_API_KEY')
    to = os.getenv('ALERT_EMAIL')
    if not all([api_key, to]):
        app.logger.warning('Resend not configured — skipping watering alert')
        return

    resend.api_key = api_key
    count = len(overdue_plants)

    lines = ['Time to water your plants!\n']
    for p in overdue_plants:
        d = p['days_overdue']
        suffix = '' if d == '?' else (f' day{"s" if d != 1 else ""} overdue')
        lines.append(f"  • {p['name']}: {d}{suffix}")
    lines.append('\nVisit plants.johnzhou.xyz to log your waterings.')

    resend.Emails.send({
        'from': 'Plants <plants@johnzhou.xyz>',
        'to': [to],
        'subject': f'🪴 {count} plant{"s" if count > 1 else ""} need{"" if count > 1 else "s"} watering',
        'text': '\n'.join(lines),
    })
    app.logger.info(f'Watering alert sent for {count} plant(s)')


def check_watering():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT p.id, p.name, p.water_every_days,
                   MAX(w.watered_at) as last_watered
            FROM plants p
            LEFT JOIN waterings w ON w.plant_id = p.id
            GROUP BY p.id
        ''').fetchall()

    today = datetime.now().date()
    overdue = []
    for r in rows:
        if r['last_watered']:
            last = datetime.fromisoformat(r['last_watered']).date()
            due = last + timedelta(days=r['water_every_days'])
            days_over = (today - due).days
            if days_over >= 0:
                overdue.append({'name': r['name'], 'days_overdue': days_over + 1})
        else:
            overdue.append({'name': r['name'], 'days_overdue': '?'})

    if overdue:
        try:
            send_alert_email(overdue)
        except Exception as e:
            app.logger.error(f'Failed to send email alert: {e}')


@app.route('/')
def index():
    with get_db() as conn:
        plants = conn.execute('''
            SELECT p.id, p.name, p.species, p.water_every_days, p.notes,
                   MAX(w.watered_at) as last_watered,
                   (SELECT health_status FROM waterings WHERE plant_id = p.id ORDER BY watered_at DESC LIMIT 1) as last_health,
                   (SELECT notes FROM waterings WHERE plant_id = p.id ORDER BY watered_at DESC LIMIT 1) as last_log_note
            FROM plants p
            LEFT JOIN waterings w ON w.plant_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        ''').fetchall()

        log = conn.execute('''
            SELECT w.id, w.watered_at, w.health_status, w.notes, p.name as plant_name
            FROM waterings w
            JOIN plants p ON p.id = w.plant_id
            ORDER BY w.watered_at DESC
            LIMIT 20
        ''').fetchall()

    now = datetime.now()
    plant_data = []
    for p in plants:
        d = dict(p)
        if p['last_watered']:
            last = datetime.fromisoformat(p['last_watered'])
            days_since = int((now - last).total_seconds() / 86400)
            d['days_since'] = days_since
            d['days_until'] = p['water_every_days'] - days_since
            d['overdue'] = days_since >= p['water_every_days']
            d['pct'] = min(100, int(days_since / p['water_every_days'] * 100))
            d['days_overdue'] = max(0, days_since - p['water_every_days'])
        else:
            d['days_since'] = None
            d['days_until'] = 0
            d['overdue'] = True
            d['pct'] = 100
            d['days_overdue'] = 0
        plant_data.append(d)

    plant_data.sort(key=lambda x: (-x['pct'], x['name']))
    return render_template('index.html', plants=plant_data, log=log)


@app.route('/plants', methods=['POST'])
def add_plant():
    name = request.form.get('name', '').strip()
    if name:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO plants (name, species, water_every_days, notes) VALUES (?, ?, ?, ?)',
                (
                    name,
                    request.form.get('species', '').strip() or None,
                    max(1, int(request.form.get('water_every_days') or 7)),
                    request.form.get('notes', '').strip() or None,
                )
            )
    return redirect(url_for('index'))


@app.route('/water', methods=['POST'])
def log_watering():
    plant_id = request.form.get('plant_id', type=int)
    if plant_id:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO waterings (plant_id, health_status, notes) VALUES (?, ?, ?)',
                (
                    plant_id,
                    request.form.get('health_status', 'good'),
                    request.form.get('notes', '').strip() or None,
                )
            )
    return redirect(url_for('index'))


@app.route('/plants/<int:plant_id>', methods=['DELETE'])
def delete_plant(plant_id):
    with get_db() as conn:
        conn.execute('DELETE FROM waterings WHERE plant_id = ?', (plant_id,))
        conn.execute('DELETE FROM plants WHERE id = ?', (plant_id,))
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(check_watering, 'cron', hour=8, minute=0)
    scheduler.start()

    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
