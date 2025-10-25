import json
import os
import time
import pymysql
from datetime import datetime
from contextlib import contextmanager
from bleak import BleakClient, BleakScanner
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Replace this with your bracelet MAC address
BRACELET_ADDRESS = "b8:27:eb:b1:fa:27"
TEMP_SENSOR_UUID = "12345678-1234-5678-1234-56789abcdef1"  # Example sensor UUID


async def read_temperature():
    async with BleakClient(BRACELET_ADDRESS) as client:
        data = await client.read_gatt_char(TEMP_SENSOR_UUID)
        # Convert bytes to temperature (depends on your sensor format)
        temperature = int.from_bytes(data, byteorder='little') / 10
        return temperature


class MoodAnalyzer:
    def __init__(self):
        self.sp = self.setup_spotify()
        self.mood_playlists = {
            "calm": "37i9dQZF1DWZd79rJ6a7lp",
            "happy": "37i9dQZF1DXdPec7aLTmlC",
            "energetic": "37i9dQZF1DX76Wlfdnj7AP",
            "stressed": "37i9dQZF1DX3rxVfibe1L0",
            "anxious": "37i9dQZF1DWZqd5JICZI0u"
        }

    # ✅ FIXED: Proper MySQL connection setup
    @contextmanager
    def get_db(self):
        conn = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DB", "mood_music"),
            cursorclass=pymysql.cursors.DictCursor
        )
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
        REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "https://mood-tracker-hackathon2025.onrender.com/callback")

        if not CLIENT_ID or not CLIENT_SECRET:
            print("⚠️  Spotify credentials not found.")
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
            print("✅ Spotify connected")
            return sp
        except Exception as e:
            print(f"❌ Spotify error: {e}")
            return None

    def load_thresholds(self):
        with self.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT mood, min_temp, max_temp FROM thresholds")
                rows = cursor.fetchall()
                return {row['mood']: {'min': row['min_temp'], 'max': row['max_temp']} for row in rows}

    def get_latest_reading(self):
        with self.get_db() as conn:
            with conn.cursor() as cursor:
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
            print("❌ Spotify not connected.")
            return False

        try:
            playlist_id = self.mood_playlists.get(mood)
            if not playlist_id:
                print(f"⚠️  No playlist for mood '{mood}'")
                return False

            playlist_uri = f"spotify:playlist:{playlist_id}"
            devices = self.sp.devices()

            if not devices or not devices.get('devices'):
                print("⚠️  No active Spotify devices found.")
                return False

            device_id = devices['devices'][0]['id']
            device_name = devices['devices'][0]['name']

            self.sp.start_playback(device_id=device_id, context_uri=playlist_uri)
            print(f"🎵 Playing '{mood}' playlist on {device_name}")
            return True

        except Exception as e:
            print(f"❌ Playback error: {e}")
            return False

    async def analyze_and_play_live(self):
        try:
            temperature = await read_temperature()
        except Exception as e:
            print(f"❌ Error reading sensor: {e}")
            return

        mood = self.determine_mood(temperature)
        print(f"🧠 Detected mood: {mood} | 🌡️ Temperature: {temperature}")

        success = self.play_mood_playlist(mood)
        self.log_analysis({
            'temperature': temperature,
            'timestamp': datetime.now(),
            'device_id': 'bracelet'
        }, mood, success)

    async def run_continuous_live(self, interval=60):
        print("🚀 Starting live mood monitoring...")
        while True:
            await self.analyze_and_play_live()
            await asyncio.sleep(interval)

    def log_analysis(self, reading, mood, success):
        with self.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO mood_log (timestamp, temperature, detected_mood, playlist_played)
                    VALUES (%s, %s, %s, %s)
                ''', (
                    datetime.now().isoformat(),
                    reading['temperature'],
                    mood,
                    1 if success else 0
                ))


async def main():
    analyzer = MoodAnalyzer()
    await analyzer.run_continuous_live(interval=60)


if __name__ == "__main__":
    asyncio.run(main())