from flask import Flask, request, jsonify, render_template
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
# Example MySQL URL format: mysql+pymysql://dbuser:dbpass@host:3306/dbname
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///mood_music.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ORM models
class Reading(db.Model):
    __tablename__ = 'readings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    temperature = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.String, nullable=False)
    device_id = db.Column(db.String)
    raw_data = db.Column(db.Text)

class Threshold(db.Model):
    __tablename__ = 'thresholds'
    mood = db.Column(db.String, primary_key=True)
    min_temp = db.Column(db.Float, nullable=False)
    max_temp = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.String)

class TuningLog(db.Model):
    __tablename__ = 'tuning_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    reported_mood = db.Column(db.String, nullable=False)
    min_temp = db.Column(db.Float)
    max_temp = db.Column(db.Float)

class MoodLog(db.Model):
    __tablename__ = 'mood_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    detected_mood = db.Column(db.String, nullable=False)
    playlist_played = db.Column(db.Integer)

DEFAULT_THRESHOLDS = {
    "calm": {"min": 36.1, "max": 36.5},
    "happy": {"min": 36.6, "max": 37.0},
    "energetic": {"min": 37.1, "max": 37.5},
    "stressed": {"min": 37.6, "max": 38.0},
    "anxious": {"min": 38.1, "max": 39.0}
}

def seed_default_thresholds():
    existing = {t.mood for t in Threshold.query.all()}
    now = datetime.now().isoformat()
    for mood, temps in DEFAULT_THRESHOLDS.items():
        if mood not in existing:
            t = Threshold(mood=mood, min_temp=temps['min'], max_temp=temps['max'], updated_at=now)
            db.session.add(t)
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_default_thresholds()

def load_user_thresholds():
    rows = Threshold.query.all()
    thresholds = {}
    for r in rows:
        thresholds[r.mood] = {'min': r.min_temp, 'max': r.max_temp}
    return thresholds

def save_user_thresholds(mood, min_temp, max_temp):
    now = datetime.now().isoformat()
    t = Threshold.query.get(mood)
    if t:
        t.min_temp = min_temp
        t.max_temp = max_temp
        t.updated_at = now
    else:
        t = Threshold(mood=mood, min_temp=min_temp, max_temp=max_temp, updated_at=now)
        db.session.add(t)
    db.session.commit()

# ===== WEBSITE ROUTES =====
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/tuning')
def tuning():
    return render_template('tuning.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ===== API ENDPOINTS FOR WEARABLE =====
@app.route('/api/temperature', methods=['POST'])
def receive_temperature():
    try:
        data = request.get_json()
        if not data or 'temperature' not in data:
            return jsonify({"success": False, "error": "Missing temperature"}), 400

        temperature = float(data['temperature'])
        device_id = data.get('device_id', 'unknown')
        timestamp = datetime.now().isoformat()

        r = Reading(temperature=temperature, timestamp=timestamp, device_id=device_id, raw_data=str(data))
        db.session.add(r)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Temperature recorded",
            "id": r.id,
            "temperature": temperature,
            "timestamp": timestamp
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/latest', methods=['GET'])
def get_latest():
    try:
        r = Reading.query.order_by(Reading.id.desc()).first()
        if r:
            return jsonify({
                "temperature": r.temperature,
                "timestamp": r.timestamp,
                "device_id": r.device_id
            })
        else:
            return jsonify({"error": "No readings available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== API ENDPOINTS FOR MOOD TUNING =====
@app.route('/api/tune-mood', methods=['POST'])
def tune_mood():
    try:
        data = request.get_json()
        reported_mood = data.get('mood')
        current_temp = data.get('temperature')

        if not reported_mood or current_temp is None:
            return jsonify({"success": False, "error": "Missing mood or temperature"}), 400

        current_temp = float(current_temp)
        thresholds = load_user_thresholds()

        if reported_mood in thresholds:
            mood_range = thresholds[reported_mood]
            new_min = min(mood_range["min"], current_temp - 0.1)
            new_max = max(mood_range["max"], current_temp + 0.1)
        else:
            new_min = current_temp - 0.2
            new_max = current_temp + 0.2

        save_user_thresholds(reported_mood, new_min, new_max)

        log = TuningLog(timestamp=datetime.now().isoformat(), temperature=current_temp,
                        reported_mood=reported_mood, min_temp=new_min, max_temp=new_max)
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Mood threshold updated",
            "mood": reported_mood,
            "new_range": {"min": new_min, "max": new_max}
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    return jsonify(load_user_thresholds())

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        limit = request.args.get('limit', 20, type=int)
        rows = Reading.query.order_by(Reading.id.desc()).limit(limit).all()
        readings = []
        for r in rows:
            readings.append({"temperature": r.temperature, "timestamp": r.timestamp, "device_id": r.device_id})
        return jsonify({"readings": readings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)