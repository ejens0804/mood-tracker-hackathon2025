import requests
import time

def calculate_mood(temp, accel):
    score = temp*0.5 + accel*10
    if score < 15:
        return 'relaxed'
    elif score < 25:
        return 'neutral'
    else:
        return 'energetic'

while True:
    data = requests.get("http://172.0.0.1:4040").json()
    
    # calculate mood from sensor data
    mood = calculate_mood(data['temperature'], data['acceleration'])
    
    print("Mood:", mood)
    
    time.sleep(5)
