// mood_spotify.js

let lastMood = null;
const POLL_INTERVAL = 600; // 10 minutes
const PI_URL = "http://172.20.10.2:5000/data"; // Pi endpoint

// Spotify app info
const CLIENT_ID = "96bf49b1a1154d8bb78a53ce1ee6db45";
const REDIRECT_URI = "https://yevette-sacrificeable-angeles.ngrok-free.dev/callback";
const SCOPES = "user-read-playback-state user-modify-playback-state";


// --- Get token ---
function getSpotifyToken() {
    // If we are on the callback page, extract token from URL hash
    if (window.location.pathname.endsWith('.dev')) {
        const hash = window.location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const token = params.get('access_token');
        if (token) {
            localStorage.setItem('spotify_token', token);
            window.location.href = '/'; // redirect to main page
        }
        return null;
    }
    // Otherwise, get from localStorage
    return localStorage.getItem('spotify_token');
}

// --- Get Pi data ---
async function getPiData() {
    const response = await fetch(PI_URL);
    if (!response.ok) throw new Error("Failed to fetch Pi data");
    return await response.json();
}

// --- Convert Pi data to mood ---
function calculateMood(temp, accel) {
    const score = temp * 0.5 + accel * 10;
    if (score < 15) return 'relaxed';
    if (score < 25) return 'neutral';
    return 'energetic';
}

// --- Get playlists from user inputs ---
function getPlaylistMapFromUI() {
    return {
        relaxed: document.getElementById('relaxed').value,
        neutral: document.getElementById('neutral').value,
        energetic: document.getElementById('energetic').value
    };
}

// --- Play playlist ---
async function playPlaylist(mood, token, playlistMap) {
    try {
        const playlistUri = playlistMap[mood];
        const devicesResp = await fetch("https://api.spotify.com/v1/me/player/devices", {
            headers: { Authorization: `Bearer ${token}` }
        });
        const devicesData = await devicesResp.json();
        const device = devicesData.devices[0]; // first active device
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

// --- Update mood ---
async function updateMood() {
    const token = getSpotifyToken();
    if (!token) {
        redirectToSpotifyLogin();
        return;
    }

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
updateMood(); // immediately
setInterval(updateMood, POLL_INTERVAL);
