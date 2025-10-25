from flask import Flask, request, jsonify, render_template
import json
import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Database setup
DB_PATH = os.environ.get('DATABASE_URL', 'mood_music.db')

# Default temperature thresholds for moods
DEFAULT_THRESHOLDS = {
    "calm": {"min": 36.1, "max": 36.5},
    "happy": {"min": 36.6, "max": 37.0},
    "energetic": {"min": 37.1, "max": 37.5},
    "stressed": {"min": 37.6, "max": 38.0},
    "anxious": {"min": 38.1, "max": 39.0}
}

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initialize database tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Table for temperature readings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL NOT NULL,
                timestamp TEXT NOT NULL,
                device_id TEXT,
                raw_data TEXT
            )
        ''')
        
        # Table for mood thresholds (user customization)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS thresholds (
                mood TEXT PRIMARY KEY,
                min_temp REAL NOT NULL,
                max_temp REAL NOT NULL,
                updated_at TEXT
            )
        ''')
        
        # Table for tuning log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tuning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL NOT NULL,
                reported_mood TEXT NOT NULL,
                min_temp REAL,
                max_temp REAL
            )
        ''')
        
        # Table for mood analysis log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mood_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL NOT NULL,
                detected_mood TEXT NOT NULL,
                playlist_played INTEGER
            )
        ''')
        
        # Insert default thresholds if table is empty
        cursor.execute('SELECT COUNT(*) FROM thresholds')
        if cursor.fetchone()[0] == 0:
            for mood, temps in DEFAULT_THRESHOLDS.items():
                cursor.execute('''
                    INSERT INTO thresholds (mood, min_temp, max_temp, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (mood, temps['min'], temps['max'], datetime.now().isoformat()))

def load_user_thresholds():
    """Load user's customized temperature thresholds from database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT mood, min_temp, max_temp FROM thresholds')
        rows = cursor.fetchall()
        
        thresholds = {}
        for row in rows:
            thresholds[row['mood']] = {
                'min': row['min_temp'],
                'max': row['max_temp']
            }
        return thresholds

def save_user_thresholds(mood, min_temp, max_temp):
    """Save or update user's customized thresholds"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO thresholds (mood, min_temp, max_temp, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (mood, min_temp, max_temp, datetime.now().isoformat()))

# ===== WEBSITE ROUTES =====
@app.route('/')
def home():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/tuning')
def tuning():
    """Mood tuning page"""
    return render_template('tuning.html')

@app.route('/about')
def about():
    """About page - example of adding more pages"""
    return render_template('about.html')

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ===== API ENDPOINTS FOR WEARABLE =====
@app.route('/api/temperature', methods=['POST'])
def receive_temperature():
    """Receive temperature data from wearable device"""
    try:
        data = request.get_json()
        
        # Validate data
        if 'temperature' not in data:
            return jsonify({"success": False, "error": "Missing temperature"}), 400
        
        temperature = data['temperature']
        device_id = data.get('device_id', 'unknown')
        timestamp = datetime.now().isoformat()
        
        # Save to database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO readings (temperature, timestamp, device_id, raw_data)
                VALUES (?, ?, ?, ?)
            ''', (temperature, timestamp, device_id, json.dumps(data)))
            
            reading_id = cursor.lastrowid
        
        return jsonify({
            "success": True,
            "message": "Temperature recorded",
            "id": reading_id,
            "temperature": temperature,
            "timestamp": timestamp
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/latest', methods=['GET'])
def get_latest():
    """Get the latest temperature reading"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT temperature, timestamp, device_id
                FROM readings
                ORDER BY id DESC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            
            if row:
                return jsonify({
                    "temperature": row['temperature'],
                    "timestamp": row['timestamp'],
                    "device_id": row['device_id']
                })
            else:
                return jsonify({"error": "No readings available"}), 404
                
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== API ENDPOINTS FOR MOOD TUNING =====
@app.route('/api/tune-mood', methods=['POST'])
def tune_mood():
    """User reports their actual mood to update temperature thresholds"""
    try:
        data = request.get_json()
        
        # Get current temperature and reported mood
        reported_mood = data.get('mood')
        current_temp = data.get('temperature')
        
        if not reported_mood or not current_temp:
            return jsonify({"success": False, "error": "Missing mood or temperature"}), 400
        
        # Load current thresholds
        thresholds = load_user_thresholds()
        
        # Update the threshold for this mood
        if reported_mood in thresholds:
            mood_range = thresholds[reported_mood]
            
            # Expand range if temperature is outside current bounds
            new_min = min(mood_range["min"], current_temp - 0.1)
            new_max = max(mood_range["max"], current_temp + 0.1)
        else:
            # Create new mood category
            new_min = current_temp - 0.2
            new_max = current_temp + 0.2
        
        # Save updated thresholds
        save_user_thresholds(reported_mood, new_min, new_max)
        
        # Log the tuning event
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tuning_log (timestamp, temperature, reported_mood, min_temp, max_temp)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), current_temp, reported_mood, new_min, new_max))
        
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
    """Get current mood thresholds"""
    return jsonify(load_user_thresholds())

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get recent temperature readings"""
    try:
        limit = request.args.get('limit', 20, type=int)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT temperature, timestamp, device_id
                FROM readings
                ORDER BY id DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            readings = []
            for row in rows:
                readings.append({
                    "temperature": row['temperature'],
                    "timestamp": row['timestamp'],
                    "device_id": row['device_id']
                })
            
            return jsonify({"readings": readings})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Initialize database on startup
with app.app_context():
    init_db()

if __name__ == '__main__':
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get('PORT', 5000))
    
    # In production, debug should be False
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host='0.0.0.0', port=port, debug=debug)


#### **requirements.txt**

# Flask==3.0.0
# gunicorn==21.2.0
# spotipy==2.23.0
# requests==2.31.0
# python-dotenv==1.0.0