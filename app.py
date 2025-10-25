from flask import Flask, request, jsonify, render_template
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///mood_music.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ===== UPDATED ORM MODELS =====
class SensorReading(db.Model):
    """Stores all sensor data from wearable"""
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
    
    # Determined mood (either from threshold or user selection)
    user_mood = db.Column(db.String(50), nullable=False)
    mood_source = db.Column(db.String(20))  # 'threshold' or 'manual'
    
    # Spotify playlist played
    playlist_id = db.Column(db.String(100))
    playlist_played = db.Column(db.Boolean, default=False)

class Threshold(db.Model):
    __tablename__ = 'thresholds'
    mood = db.Column(db.String(50), primary_key=True)
    min_temp = db.Column(db.Float, nullable=False)
    max_temp = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime)

class TuningLog(db.Model):
    __tablename__ = 'tuning_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    reported_mood = db.Column(db.String(50), nullable=False)
    min_temp = db.Column(db.Float)
    max_temp = db.Column(db.Float)

DEFAULT_THRESHOLDS = {
    "calm": {"min": 36.1, "max": 36.5},
    "happy": {"min": 36.6, "max": 37.0},
    "energetic": {"min": 37.1, "max": 37.5},
    "stressed": {"min": 37.6, "max": 38.0},
    "anxious": {"min": 38.1, "max": 39.0}
}

MOOD_PLAYLISTS = {
    "calm": "37i9dQZF1DWZd79rJ6a7lp",
    "happy": "37i9dQZF1DXdPec7aLTmlC",
    "energetic": "37i9dQZF1DX76Wlfdnj7AP",
    "stressed": "37i9dQZF1DX3rxVfibe1L0",
    "anxious": "37i9dQZF1DWZqd5JICZI0u"
}

def seed_default_thresholds():
    existing = {t.mood for t in Threshold.query.all()}
    now = datetime.now()
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
    now = datetime.now()
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
    """Determine mood based on temperature thresholds"""
    thresholds = load_user_thresholds()
    for mood, temp_range in thresholds.items():
        if temp_range["min"] <= temperature <= temp_range["max"]:
            return mood
    return "calm"  # default

# ===== WEBSITE ROUTES =====
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/current-mood')
def current_mood():
    # Get latest sensor reading
    latest = SensorReading.query.order_by(SensorReading.id.desc()).first()
    return render_template('current-mood.html', reading=latest)

@app.route('/mood-history')
def mood_history():
    # Get all readings grouped by date
    readings = SensorReading.query.order_by(SensorReading.timestamp.desc()).limit(100).all()
    
    # Group by date
    history_by_date = {}
    for reading in readings:
        date_key = reading.timestamp.strftime('%Y-%m-%d')
        if date_key not in history_by_date:
            history_by_date[date_key] = []
        history_by_date[date_key].append(reading)
    
    return render_template('mood-history.html', history=history_by_date)

@app.route('/tuning')
def tuning():
    # Get latest temperature for display
    latest = SensorReading.query.order_by(SensorReading.id.desc()).first()
    return render_template('tuning.html', latest_temp=latest.temperature if latest else None)

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
    Receive complete sensor data from wearable device
    Expected JSON format:
    {
        "device_id": "wearable_001",
        "gyro_x": 0.5,
        "gyro_y": -0.3,
        "gyro_z": 0.8,
        "temperature": 36.8,
        "humidity": 45.2,
        "user_mood": "happy"  (optional - if not provided, will be calculated)
    }
    """
    try:
        data = request.get_json()
        if not data or 'temperature' not in data:
            return jsonify({"success": False, "error": "Missing temperature"}), 400

        # Extract data
        temperature = float(data['temperature'])
        device_id = data.get('device_id', 'unknown')
        gyro_x = data.get('gyro_x')
        gyro_y = data.get('gyro_y')
        gyro_z = data.get('gyro_z')
        humidity = data.get('humidity')
        
        # Determine mood
        if 'user_mood' in data and data['user_mood']:
            user_mood = data['user_mood']
            mood_source = 'manual'
        else:
            user_mood = determine_mood_from_temperature(temperature)
            mood_source = 'threshold'
        
        # Get playlist for this mood
        playlist_id = MOOD_PLAYLISTS.get(user_mood)
        
        # Save to database
        reading = SensorReading(
            timestamp=datetime.now(),
            device_id=device_id,
            gyro_x=gyro_x,
            gyro_y=gyro_y,
            gyro_z=gyro_z,
            temperature=temperature,
            humidity=humidity,
            user_mood=user_mood,
            mood_source=mood_source,
            playlist_id=playlist_id,
            playlist_played=False  # Will be updated when Spotify plays
        )
        db.session.add(reading)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Sensor data recorded",
            "id": reading.id,
            "mood": user_mood,
            "mood_source": mood_source,
            "playlist_id": playlist_id,
            "timestamp": reading.timestamp.isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/latest', methods=['GET'])
def get_latest():
    """Get latest sensor reading"""
    try:
        r = SensorReading.query.order_by(SensorReading.id.desc()).first()
        if r:
            return jsonify({
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "temperature": r.temperature,
                "humidity": r.humidity,
                "gyro_x": r.gyro_x,
                "gyro_y": r.gyro_y,
                "gyro_z": r.gyro_z,
                "user_mood": r.user_mood,
                "mood_source": r.mood_source,
                "device_id": r.device_id,
                "playlist_id": r.playlist_id
            })
        else:
            return jsonify({"error": "No readings available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get historical sensor readings"""
    try:
        limit = request.args.get('limit', 50, type=int)
        readings = SensorReading.query.order_by(SensorReading.id.desc()).limit(limit).all()
        
        result = []
        for r in readings:
            result.append({
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "temperature": r.temperature,
                "humidity": r.humidity,
                "gyro_x": r.gyro_x,
                "gyro_y": r.gyro_y,
                "gyro_z": r.gyro_z,
                "user_mood": r.user_mood,
                "mood_source": r.mood_source,
                "device_id": r.device_id,
                "playlist_played": r.playlist_played
            })
        
        return jsonify({"readings": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== API ENDPOINTS FOR MOOD TUNING =====
@app.route('/api/manual-mood', methods=['POST'])
def manual_mood_selection():
    """
    User manually selects their mood (from tuning.html buttons)
    This will:
    1. Get latest sensor reading
    2. Update mood in database
    3. Return playlist to play
    """
    try:
        data = request.get_json()
        selected_mood = data.get('mood')
        
        if not selected_mood:
            return jsonify({"success": False, "error": "Missing mood"}), 400

        # Get latest sensor reading or use provided temperature
        if 'temperature' in data:
            temperature = float(data['temperature'])
            humidity = data.get('humidity')
            gyro_x = data.get('gyro_x')
            gyro_y = data.get('gyro_y')
            gyro_z = data.get('gyro_z')
            device_id = data.get('device_id', 'manual')
            
            # Create new reading with manual mood
            reading = SensorReading(
                timestamp=datetime.now(),
                device_id=device_id,
                gyro_x=gyro_x,
                gyro_y=gyro_y,
                gyro_z=gyro_z,
                temperature=temperature,
                humidity=humidity,
                user_mood=selected_mood,
                mood_source='manual',
                playlist_id=MOOD_PLAYLISTS.get(selected_mood),
                playlist_played=False
            )
            db.session.add(reading)
        else:
            # Update latest reading with new mood
            reading = SensorReading.query.order_by(SensorReading.id.desc()).first()
            if reading:
                reading.user_mood = selected_mood
                reading.mood_source = 'manual'
                reading.playlist_id = MOOD_PLAYLISTS.get(selected_mood)
        
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Mood updated",
            "mood": selected_mood,
            "playlist_id": MOOD_PLAYLISTS.get(selected_mood)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tune-mood', methods=['POST'])
def tune_mood():
    """Adjust mood thresholds based on user feedback"""
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

        log = TuningLog(
            timestamp=datetime.now(),
            temperature=current_temp,
            reported_mood=reported_mood,
            min_temp=new_min,
            max_temp=new_max
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Mood threshold updated",
            "mood": reported_mood,
            "new_range": {"min": new_min, "max": new_max}
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    return jsonify(load_user_thresholds())

@app.route('/api/mark-played', methods=['POST'])
def mark_playlist_played():
    """Mark that a playlist was successfully played"""
    try:
        data = request.get_json()
        reading_id = data.get('reading_id')
        
        if reading_id:
            reading = SensorReading.query.get(reading_id)
            if reading:
                reading.playlist_played = True
                db.session.commit()
                return jsonify({"success": True}), 200
        
        return jsonify({"success": False, "error": "Reading not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)



# from flask import Flask, request, jsonify, render_template
# import os
# from datetime import datetime
# from flask_sqlalchemy import SQLAlchemy
# from flask_migrate import Migrate

# app = Flask(__name__)
# app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# # Database configuration
# # Example MySQL URL format: mysql+pymysql://dbuser:dbpass@host:3306/dbname
# DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///mood_music.db')
# app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# db = SQLAlchemy(app)
# migrate = Migrate(app, db)

# # ORM models
# class Reading(db.Model):
#     __tablename__ = 'readings'
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     temperature = db.Column(db.Float, nullable=False)
#     timestamp = db.Column(db.String(50), nullable=False)
#     device_id = db.Column(db.String(100))
#     raw_data = db.Column(db.Text)

# class Threshold(db.Model):
#     __tablename__ = 'thresholds'
#     mood = db.Column(db.String(50), primary_key=True)
#     min_temp = db.Column(db.Float, nullable=False)
#     max_temp = db.Column(db.Float, nullable=False)
#     updated_at = db.Column(db.String(50))

# class TuningLog(db.Model):
#     __tablename__ = 'tuning_log'
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     timestamp = db.Column(db.String(50), nullable=False)
#     temperature = db.Column(db.Float, nullable=False)
#     reported_mood = db.Column(db.String(50), nullable=False)
#     min_temp = db.Column(db.Float)
#     max_temp = db.Column(db.Float)

# class MoodLog(db.Model):
#     __tablename__ = 'mood_log'
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     timestamp = db.Column(db.String(50), nullable=False)
#     temperature = db.Column(db.Float, nullable=False)
#     detected_mood = db.Column(db.String(50), nullable=False)
#     playlist_played = db.Column(db.Integer)

# DEFAULT_THRESHOLDS = {
#     "calm": {"min": 36.1, "max": 36.5},
#     "happy": {"min": 36.6, "max": 37.0},
#     "energetic": {"min": 37.1, "max": 37.5},
#     "stressed": {"min": 37.6, "max": 38.0},
#     "anxious": {"min": 38.1, "max": 39.0}
# }

# def seed_default_thresholds():
#     existing = {t.mood for t in Threshold.query.all()}
#     now = datetime.now().isoformat()
#     for mood, temps in DEFAULT_THRESHOLDS.items():
#         if mood not in existing:
#             t = Threshold(mood=mood, min_temp=temps['min'], max_temp=temps['max'], updated_at=now)
#             db.session.add(t)
#     db.session.commit()

# with app.app_context():
#     db.create_all()
#     seed_default_thresholds()

# def load_user_thresholds():
#     rows = Threshold.query.all()
#     thresholds = {}
#     for r in rows:
#         thresholds[r.mood] = {'min': r.min_temp, 'max': r.max_temp}
#     return thresholds

# def save_user_thresholds(mood, min_temp, max_temp):
#     now = datetime.now().isoformat()
#     t = Threshold.query.get(mood)
#     if t:
#         t.min_temp = min_temp
#         t.max_temp = max_temp
#         t.updated_at = now
#     else:
#         t = Threshold(mood=mood, min_temp=min_temp, max_temp=max_temp, updated_at=now)
#         db.session.add(t)
#     db.session.commit()

# # ===== WEBSITE ROUTES =====
# @app.route('/')
# def home():
#     return render_template('index.html')

# @app.route('/current-mood')
# def current_mood():
#     return render_template('current-mood.html')

# @app.route('/mood-history')
# def mood_history():
#     return render_template('mood-history.html')

# @app.route('/tuning')
# def tuning():
#     return render_template('tuning.html')

# @app.route('/about')
# def about():
#     return render_template('about.html')

# @app.route('/health')
# def health():
#     return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# # ===== API ENDPOINTS FOR WEARABLE =====
# @app.route('/api/temperature', methods=['POST'])
# def receive_temperature():
#     try:
#         data = request.get_json()
#         if not data or 'temperature' not in data:
#             return jsonify({"success": False, "error": "Missing temperature"}), 400

#         temperature = float(data['temperature'])
#         device_id = data.get('device_id', 'unknown')
#         timestamp = datetime.now().isoformat()

#         r = Reading(temperature=temperature, timestamp=timestamp, device_id=device_id, raw_data=str(data))
#         db.session.add(r)
#         db.session.commit()

#         return jsonify({
#             "success": True,
#             "message": "Temperature recorded",
#             "id": r.id,
#             "temperature": temperature,
#             "timestamp": timestamp
#         }), 200

#     except Exception as e:
#         return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/api/latest', methods=['GET'])
# def get_latest():
#     try:
#         r = Reading.query.order_by(Reading.id.desc()).first()
#         if r:
#             return jsonify({
#                 "temperature": r.temperature,
#                 "timestamp": r.timestamp,
#                 "device_id": r.device_id
#             })
#         else:
#             return jsonify({"error": "No readings available"}), 404
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# # ===== API ENDPOINTS FOR MOOD TUNING =====
# @app.route('/api/tune-mood', methods=['POST'])
# def tune_mood():
#     try:
#         data = request.get_json()
#         reported_mood = data.get('mood')
#         current_temp = data.get('temperature')

#         if not reported_mood or current_temp is None:
#             return jsonify({"success": False, "error": "Missing mood or temperature"}), 400

#         current_temp = float(current_temp)
#         thresholds = load_user_thresholds()

#         if reported_mood in thresholds:
#             mood_range = thresholds[reported_mood]
#             new_min = min(mood_range["min"], current_temp - 0.1)
#             new_max = max(mood_range["max"], current_temp + 0.1)
#         else:
#             new_min = current_temp - 0.2
#             new_max = current_temp + 0.2

#         save_user_thresholds(reported_mood, new_min, new_max)

#         log = TuningLog(timestamp=datetime.now().isoformat(), temperature=current_temp,
#                         reported_mood=reported_mood, min_temp=new_min, max_temp=new_max)
#         db.session.add(log)
#         db.session.commit()

#         return jsonify({
#             "success": True,
#             "message": "Mood threshold updated",
#             "mood": reported_mood,
#             "new_range": {"min": new_min, "max": new_max}
#         }), 200

#     except Exception as e:
#         return jsonify({"success": False, "error": str(e)}), 500

# @app.route('/api/thresholds', methods=['GET'])
# def get_thresholds():
#     return jsonify(load_user_thresholds())

# @app.route('/api/history', methods=['GET'])
# def get_history():
#     try:
#         limit = request.args.get('limit', 20, type=int)
#         rows = Reading.query.order_by(Reading.id.desc()).limit(limit).all()
#         readings = []
#         for r in rows:
#             readings.append({"temperature": r.temperature, "timestamp": r.timestamp, "device_id": r.device_id})
#         return jsonify({"readings": readings})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     port = int(os.environ.get('PORT', 5000))
#     debug = os.environ.get('FLASK_ENV') == 'development'
#     app.run(host='0.0.0.0', port=port, debug=debug)