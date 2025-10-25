from flask import Flask, request, jsonify, render_template
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging

# --- App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# --- Database Setup (Connects to your AWS MySQL) ---
# On Render, set DATABASE_URL to: mysql+pymysql://user:pass@aws_host/db_name
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///mood_music.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
logging.basicConfig(level=logging.INFO)

# --- NEW DATABASE MODELS ---

class SensorReading(db.Model):
    """
    Stores all data from a single wearable reading, the mood it
    resulted in, and whether music has been played for it.
    This new model replaces your old 'Reading' and 'MoodLog' models.
    """
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    device_id = db.Column(db.String(100))
    
    # Gyroscope data
    gyro_x = db.Column(db.Float)
    gyro_y = db.Column(db.Float)
    gyro_z = db.Column(db.Float)
    
    # Temperature and humidity
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float)
    
    # Determined mood
    user_mood = db.Column(db.String(50), nullable=False)
    mood_source = db.Column(db.String(20))  # 'threshold' or 'manual'
    
    # Spotify trigger
    playlist_played = db.Column(db.Boolean, default=False)

class Threshold(db.Model):
    """Stores the user's custom mood thresholds (unchanged)"""
    __tablename__ = 'thresholds'
    mood = db.Column(db.String(50), primary_key=True)
    min_temp = db.Column(db.Float, nullable=False)
    max_temp = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime) # Changed to DateTime for better sorting

class TuningLog(db.Model):
    """Logs when a user manually tunes their mood (unchanged)"""
    __tablename__ = 'tuning_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False) # Changed to DateTime
    temperature = db.Column(db.Float, nullable=False)
    reported_mood = db.Column(db.String(50), nullable=False)
    min_temp = db.Column(db.Float)
    max_temp = db.Column(db.Float)

# --- Default Thresholds (Unchanged) ---
DEFAULT_THRESHOLDS = {
    "calm": {"min": 36.1, "max": 36.5},
    "happy": {"min": 36.6, "max": 37.0},
    "energetic": {"min": 37.1, "max": 37.5},
    "stressed": {"min": 37.6, "max": 38.0},
    "anxious": {"min": 38.1, "max": 39.0}
}

# --- Helper Functions ---

def seed_default_thresholds():
    """Seeds the database with default thresholds if they don't exist."""
    try:
        existing = {t.mood for t in Threshold.query.all()}
        now = datetime.utcnow()
        for mood, temps in DEFAULT_THRESHOLDS.items():
            if mood not in existing:
                t = Threshold(mood=mood, min_temp=temps['min'], max_temp=temps['max'], updated_at=now)
                db.session.add(t)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error seeding thresholds: {e}")
        db.session.rollback()

def load_user_thresholds():
    """Loads all mood thresholds from the database."""
    rows = Threshold.query.all()
    return {r.mood: {'min': r.min_temp, 'max': r.max_temp} for r in rows}

def save_user_thresholds(mood, min_temp, max_temp):
    """Saves a new or updated threshold to the database."""
    now = datetime.utcnow()
    t = Threshold.query.get(mood)
    if t:
        t.min_temp = min_temp
        t.max_temp = max_temp
        t.updated_at = now
    else:
        t = Threshold(mood=mood, min_temp=min_temp, max_temp=max_temp, updated_at=now)
        db.session.add(t)
    db.session.commit()

def determine_mood_from_temperature(temperature):
    """Determines mood based on temperature using DB thresholds."""
    thresholds = load_user_thresholds()
    for mood, temp_range in thresholds.items():
        if temp_range["min"] <= temperature <= temp_range["max"]:
            return mood
    return "calm"  # Default mood if no range matches

# --- Create Tables on Startup ---
with app.app_context():
    db.create_all()
    seed_default_thresholds()

# ===== WEBSITE ROUTES =====
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/current-mood')
def current_mood():
    # Get the most recent mood
    latest_reading = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()
    return render_template('current-mood.html', reading=latest_reading)

@app.route('/mood-history')
def mood_history():
    """
    GOAL 2: This route now reads from the new 'SensorReading' table
    and groups the data by date to display on mood-history.html.
    """
    try:
        # Get all readings, newest first
        readings = SensorReading.query.order_by(SensorReading.timestamp.desc()).limit(100).all()
        
        # Group by date for the template
        history_by_date = {}
        for reading in readings:
            date_key = reading.timestamp.strftime('%Y-%m-%d') # e.g., "2025-10-25"
            if date_key not in history_by_date:
                history_by_date[date_key] = []
            history_by_date[date_key].append(reading)
            
        return render_template('mood-history.html', history=history_by_date)
    except Exception as e:
        logging.error(f"Error loading mood history: {e}")
        return render_template('mood-history.html', history={})

@app.route('/tuning')
def tuning():
    # Pass the current thresholds to the tuning page
    thresholds = load_user_thresholds()
    return render_template('tuning.html', thresholds=thresholds)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ===== API ENDPOINTS FOR WEARABLE =====

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """
    GOAL 1: This is your new main endpoint for the wearable.
    It receives ALL sensor data, determines the mood, and saves it
    to the new 'SensorReading' table.
    """
    try:
        data = request.get_json()
        if not data or 'temperature' not in data:
            return jsonify({"success": False, "error": "Missing temperature"}), 400

        # Determine mood based on temperature
        temperature = float(data['temperature'])
        determined_mood = determine_mood_from_temperature(temperature)
        
        # Create new database entry
        reading = SensorReading(
            device_id=data.get('device_id', 'unknown'),
            temperature=temperature,
            humidity=data.get('humidity'),
            gyro_x=data.get('gyro_x'),
            gyro_y=data.get('gyro_y'),
            gyro_z=data.get('gyro_z'),
            user_mood=determined_mood,
            mood_source='threshold',  # Mood was set by the system
            playlist_played=False     # Mark as UNPLAYED for Spotify
        )
        
        db.session.add(reading)
        db.session.commit()

        logging.info(f"Logged sensor data, mood: {determined_mood}")

        return jsonify({
            "success": True,
            "message": "Sensor data recorded",
            "id": reading.id,
            "determined_mood": determined_mood
        }), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in /api/sensor-data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/latest', methods=['GET'])
def get_latest():
    """Gets the most recent SensorReading."""
    try:
        r = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()
        if r:
            return jsonify({
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "device_id": r.device_id,
                "temperature": r.temperature,
                "humidity": r.humidity,
                "gyro_x": r.gyro_x,
                "gyro_y": r.gyro_y,
                "gyro_z": r.gyro_z,
                "user_mood": r.user_mood,
                "mood_source": r.mood_source
            })
        else:
            return jsonify({"error": "No readings available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== API ENDPOINTS FOR MOOD TUNING =====

@app.route('/api/tune-mood', methods=['POST'])
def tune_mood():
    """
    GOAL 1 & 3: This endpoint is called from tuning.html.
    It does TWO things:
    1. Saves a new SensorReading with the user's MANUAL mood.
    2. Updates the threshold logic for that mood.
    """
    try:
        data = request.get_json()
        reported_mood = data.get('mood')
        
        # All sensor data should be sent from the tuning page
        # (Your JS needs to fetch and send this)
        temperature = data.get('temperature')
        
        if not reported_mood or temperature is None:
            return jsonify({"success": False, "error": "Missing mood or temperature"}), 400

        temperature = float(temperature)

        # --- Part 1: Log this manual mood selection ---
        # This creates a new entry that the Spotify daemon will see
        manual_reading = SensorReading(
            device_id=data.get('device_id', 'web-ui'),
            temperature=temperature,
            humidity=data.get('humidity'),
            gyro_x=data.get('gyro_x'),
            gyro_y=data.get('gyro_y'),
            gyro_z=data.get('gyro_z'),
            user_mood=reported_mood,
            mood_source='manual',     # Mood was set by the user
            playlist_played=False     # Mark as UNPLAYED for Spotify
        )
        db.session.add(manual_reading)
        
        # --- Part 2: Update the thresholds (your original logic) ---
        thresholds = load_user_thresholds()
        if reported_mood in thresholds:
            mood_range = thresholds[reported_mood]
            new_min = min(mood_range["min"], temperature - 0.1)
            new_max = max(mood_range["max"], temperature + 0.1)
        else:
            new_min = temperature - 0.2
            new_max = temperature + 0.2

        save_user_thresholds(reported_mood, new_min, new_max)

        # Log the tuning action itself
        log = TuningLog(timestamp=datetime.utcnow(), temperature=temperature,
                        reported_mood=reported_mood, min_temp=new_min, max_temp=new_max)
        db.session.add(log)
        
        db.session.commit()
        
        logging.info(f"Logged manual mood tune: {reported_mood}")

        return jsonify({
            "success": True,
            "message": "Mood recorded and threshold updated",
            "mood": reported_mood,
            "new_range": {"min": new_min, "max": new_max}
        }), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in /api/tune-mood: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    return jsonify(load_user_thresholds())

@app.route('/api/history', methods=['GET'])
def get_history():
    """API endpoint to get raw history data."""
    try:
        limit = request.args.get('limit', 50, type=int)
        rows = SensorReading.query.order_by(SensorReading.timestamp.desc()).limit(limit).all()
        readings = [{
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "temperature": r.temperature,
            "user_mood": r.user_mood,
            "mood_source": r.mood_source
        } for r in rows]
        return jsonify({"readings": readings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Spotify OAuth Callback ---
# This is where Spotify sends the user after they log in
@app.route('/callback')
def callback():
    # This endpoint is minimal. Its only job is to receive the
    # code from Spotify. The Spotipy library handles the rest
    # when you run the mood_analyzer.py script.
    return "Spotify authentication successful! You can close this tab."

# --- Run the App ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)