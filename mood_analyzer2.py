import json
import os
import time
import pymysql
from datetime import datetime
from contextlib import contextmanager
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging

logging.basicConfig(level=logging.INFO)

class SpotifyPlayerDaemon:
    def __init__(self):
        # Setup Spotify connection (same as your original file)
        self.sp = self.setup_spotify()
        self.mood_playlists = {
            "calm": "37i9dQZF1DWZd79rJ6a7lp",
            "happy": "37i9dQZF1DXdPec7aLTmlC",
            "energetic": "37i9dQZF1DX76Wlfdnj7AP",
            "stressed": "37i9dQZF1DX3rxVfibe1L0",
            "anxious": "37i9dQZF1DWZqd5JICZI0u"
            # Add any other moods you use
        }

    @contextmanager
    def get_db(self):
        """
        Connects directly to the AWS MySQL database using pymysql.
        Ensures environment variables are set.
        """
        try:
            conn = pymysql.connect(
                host=os.environ.get("MYSQL_HOST"),
                user=os.environ.get("MYSQL_USER"),
                password=os.environ.get("MYSQL_PASSWORD"),
                database=os.environ.get("MYSQL_DB"),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False # We will manage transactions
            )
            yield conn
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()

    def setup_spotify(self):
        """Authenticates with the Spotify API."""
        CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
        CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
        
        # This MUST match the one in your Flask app and Spotify Dashboard
        REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "https://your-app-name.onrender.com/callback")

        if not CLIENT_ID or not CLIENT_SECRET:
            logging.warning("⚠️  Spotify credentials (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET) not found.")
            return None

        scope = "user-read-playback-state user-modify-playback-state playlist-read-private"

        try:
            # Using .spotify_cache ensures you don't have to log in every time
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                redirect_uri=REDIRECT_URI,
                scope=scope,
                cache_path=".spotify_cache" 
            ))
            
            # This call will trigger the auth flow if needed (or refresh the token)
            sp.current_user() 
            logging.info("✅ Spotify connected")
            return sp
        except Exception as e:
            logging.error(f"❌ Spotify authentication error: {e}")
            logging.error("    If running for the first time, you may need to run this locally")
            logging.error("    to authenticate in a browser, then upload the .spotify_cache file.")
            return None

    def play_mood_playlist(self, mood):
        """Plays the Spotify playlist for the given mood."""
        if not self.sp:
            logging.error("❌ Spotify not connected. Skipping playback.")
            return False

        try:
            playlist_id = self.mood_playlists.get(mood)
            if not playlist_id:
                logging.warning(f"⚠️  No playlist configured for mood '{mood}'")
                return False

            playlist_uri = f"spotify:playlist:{playlist_id}"
            
            # Find an active device
            devices = self.sp.devices()
            if not devices or not devices.get('devices'):
                logging.warning("⚠️  No active Spotify devices found. Open Spotify on a device.")
                return False

            # Play on the first available device
            device_id = devices['devices'][0]['id']
            device_name = devices['devices'][0]['name']

            self.sp.start_playback(device_id=device_id, context_uri=playlist_uri)
            logging.info(f"🎵 Playing '{mood}' playlist on {device_name}")
            return True

        except Exception as e:
            # Handle common "No active device" error
            if "No active device found" in str(e):
                 logging.warning("⚠️  Spotify error: No active device found.")
            else:
                logging.error(f"❌ Spotify playback error: {e}")
            return False

    def check_for_new_mood_and_play(self):
        """
        1. Checks the DB for the latest unplayed mood.
        2. Plays the music.
        3. Marks it as played.
        """
        reading_to_play = None
        conn = None
        
        try:
            with self.get_db() as conn:
                with conn.cursor() as cursor:
                    # Find the newest entry that has NOT been played
                    cursor.execute("""
                        SELECT id, user_mood 
                        FROM sensor_readings 
                        WHERE playlist_played = False 
                        ORDER BY timestamp ASC
                        LIMIT 1
                    """)
                    reading_to_play = cursor.fetchone()

            # 2. If we found one, play it
            if reading_to_play:
                mood = reading_to_play['user_mood']
                reading_id = reading_to_play['id']
                
                logging.info(f"Found new mood: '{mood}' (ID: {reading_id}). Attempting to play...")
                success = self.play_mood_playlist(mood)
                
                # 3. Mark it as played (even if playback failed, to avoid loops)
                if success:
                    logging.info(f"Successfully started playlist for '{mood}'.")
                else:
                    logging.warning(f"Failed to play playlist for '{mood}'. Marking as played to prevent loop.")

                with self.get_db() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE sensor_readings 
                            SET playlist_played = True 
                            WHERE id = %s
                        """, (reading_id,))
                    conn.commit() # Commit the update
                logging.info(f"Marked reading {reading_id} as played.")
            else:
                # No new moods, just wait
                logging.debug("No new moods to play. Waiting...")
                pass
        
        except pymysql.Error as e:
            logging.error(f"Database error during check/play loop: {e}")
            if conn:
                conn.rollback()
        except Exception as e:
            logging.error(f"An error occurred in the main loop: {e}")

    def run_daemon(self, interval=10):
        """Runs continuously, checking for new moods every `interval` seconds."""
        logging.info("🚀 Starting Spotify Player Daemon...")
        if not self.sp:
            logging.error("❌ Spotify not connected. Daemon cannot start.")
            return
            
        while True:
            self.check_for_new_mood_and_play()
            # Wait for the next check
            time.sleep(interval)

if __name__ == "__main__":
    player = SpotifyPlayerDaemon()
    player.run_daemon(interval=10) # Check for new songs every 10 seconds