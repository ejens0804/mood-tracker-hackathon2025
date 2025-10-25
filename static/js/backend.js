let lastMood = null;
const POLL_INTERVAL = 600000; // 10 minutes
const PI_URL = "http://172.20.10.2:5000/data";
const redirectUri = "https://mood-tracker-hackathon2025.onrender.com/";


// --- Spotify App Info ---
const CLIENT_ID = "96bf49b1a1154d8bb78a53ce1ee6db45"; 
const REDIRECT_URI = window.location.origin + window.location.pathname; // current page
const SCOPES = "user-modify-playback-state user-read-playback-state";

// --- Get token from URL hash ---
function getTokenFromUrl() {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);
    return params.get("access_token");
}

// --- Redirect to Spotify auth if no token ---
function ensureSpotifyToken() {
    let token = getTokenFromUrl();
    if (!token) {
        const authUrl = `https://accounts.spotify.com/authorize?client_id=${CLIENT_ID}&response_type=token&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${encodeURIComponent(SCOPES)}`;
        window.location = authUrl;
    }
    return token;
}

const token = ensureSpotifyToken();

// --- Fetch Pi Data ---
async function getPiData() {
    const response = await fetch(PI_URL);
    if (!response.ok) throw new Error("Failed to fetch Pi data");
    return await response.json();
}

// --- Mood calculation ---
function calculateMood(temp, accel) {
    const score = temp * 0.5 + accel * 10;
    if (score < 15) return 'relaxed';
    if (score < 25) return 'neutral';
    return 'energetic';
}

// --- Get user playlist URIs ---
function getPlaylistMapFromUI() {
    return {
        relaxed: document.getElementById('relaxed').value,
        neutral: document.getElementById('neutral').value,
        energetic: document.getElementById('energetic').value
    };
}

// --- Play Spotify Playlist ---
async function playPlaylist(mood, token, playlistMap) {
    try {
        const playlistUri = playlistMap[mood];
        const devicesResp = await fetch("https://api.spotify.com/v1/me/player/devices", {
            headers: { Authorization: `Bearer ${token}` }
        });
        const devicesData = await devicesResp.json();
        const device = devicesData.devices[0];
        if (!device) {
            console.log("No active Spotify devices found.");
            return;
        }

        await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${device.id}`, {
            method: "PUT",
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ context_uri: playlistUri })
        });
        console.log(`Playing ${mood} playlist: ${playlistUri}`);
    } catch (err) {
        console.error("Error playing playlist:", err);
    }
}

// --- Main update ---
async function updateMood() {
    try {
        const data = await getPiData();
        const mood = calculateMood(data.temperature, data.acceleration);
        const playlistMap = getPlaylistMapFromUI();

        if (mood !== lastMood) {
            await playPlaylist(mood, token, playlistMap);
            lastMood = mood;
        } else {
            console.log("Mood unchanged:", mood);
        }
    } catch (err) {
        console.error("Error updating mood:", err);
    }
}

// --- Start polling ---
updateMood();
setInterval(updateMood, POLL_INTERVAL);
