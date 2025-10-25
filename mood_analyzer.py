import json
import os
import time
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import spotipy
from spotipy.oauth2 import SpotifyOAuth

class MoodAnalyzer:
    def __init__(self, db_path="mood_music.db"):
        self.db_path = db_path
        self.sp = self.setup_spotify()
        
        # Mood to playlist mapping
        self.mood_playlists = {
            "calm": "37i9dQZF1DWZd79rJ6a7lp",
            "happy": "37i9dQZF1DXdPec7aLTmlC",
            "energetic": "37i9dQZF1DX76Wlfdnj7AP",
            "stressed": "37i9dQZF1DX3rxVfibe1L0",
            "anxious": "37i9dQZF1DWZqd5JICZI0u"
        }
    
    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def setup_spotify(self):
        CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
        CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
        REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        
        if not CLIENT_ID or not CLIENT_SECRET:
            print("⚠️  WARNING: Spotify credentials not found")
            return None
        
        scope = "user-read-playback-state user-modify-playback-state playlist-read-private"
        
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                redirect_uri=REDIRECT_URI,
                scope=scope,
                cache_path=".spotify_cache"
            ))
            sp.current_user()
            print("✓ Spotify connected")
            return sp
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def load_thresholds(self):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT mood, min_temp, max_temp FROM thresholds')
            rows = cursor.fetchall()
            return {row['mood']: {'min': row['min_temp'], 'max': row['max_temp']} 
                    for row in rows}
    
    def get_latest_reading(self):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT temperature, timestamp, device_id
                FROM readings ORDER BY id DESC LIMIT 1
            ''')
            row = cursor.fetchone()
            if row:
                return {
                    'temperature': row['temperature'],
                    'timestamp': row['timestamp'],
                    'device_id': row['device_id']
                }
        return None
    
    def determine_mood(self, temperature):
        thresholds = self.load_thresholds()
        for mood, temp_range in thresholds.items():
            if temp_range["min"] <= temperature <= temp_range["max"]:
                return mood
        return "calm"
    
    def play_mood_playlist(self, mood):
        if not self.sp:
            print("❌ Spotify not connected - skipping playback")
            return False
        
        try:
            playlist_id = self.mood_playlists.get(mood)
            if not playlist_id:
                print(f"⚠️  No playlist found for mood: {mood}")
                return False
            
            playlist_uri = f"spotify:playlist:{playlist_id}"
            devices = self.sp.devices()
            
            if not devices['devices']:
                print("⚠️  No active Spotify devices found")
                return False
            
            device_id = devices['devices'][0]['id']
            device_name = devices['devices'][0]['name']
            self.sp.start_playback(device_id=device_id, context_uri=playlist_uri)
            
            print(f"🎵 Playing {mood} playlist on {device_name}")
            return True
        except Exception as e:
            print(f"❌ Error playing playlist: {e}")
            return False
    
    def analyze_and_play(self):
        reading = self.get_latest_reading()
        if not reading:
            print("⚠️  No temperature reading available")
            return None
        
        temperature = reading['temperature']
        mood = self.determine_mood(temperature)
        
        print(f"\n{'='*50}")
        print(f"🌡️  Temperature: {temperature}°C")
        print(f"😊 Detected Mood: {mood.upper()}")
        print(f"⏰ Time: {reading['timestamp']}")
        print(f"{'='*50}\n")
        
        success = self.play_mood_playlist(mood)
        self.log_analysis(reading, mood, success)
        
        return {
            "temperature": temperature,
            "mood": mood,
            "timestamp": reading['timestamp'],
            "playlist_played": success
        }
    
    def log_analysis(self, reading, mood, success):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mood_log (timestamp, temperature, detected_mood, playlist_played)
                VALUES (?, ?, ?, ?)
            ''', (datetime.now().isoformat(), reading['temperature'], mood, 1 if success else 0))
    
    def run_continuous(self, interval=60):
        print("🚀 Starting continuous mood monitoring...")
        print(f"⏱️  Checking every {interval} seconds")
        print("🛑 Press Ctrl+C to stop\n")
        
        try:
            while True:
                try:
                    self.analyze_and_play()
                except Exception as e:
                    print(f"❌ Error: {e}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping...")

def main():
    db_path = os.environ.get('DATABASE_URL', 'mood_music.db')
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return
    
    analyzer = MoodAnalyzer(db_path=db_path)
    analyzer.run_continuous(interval=60)

if __name__ == "__main__":
    main()