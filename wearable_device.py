import requests
import time
import json
from datetime import datetime

# Configuration
SERVER_URL = "http://localhost:5000"  # Change to your Render URL when deployed
DEVICE_ID = "wearable_001"
SEND_INTERVAL = 30  # seconds

class TemperatureWearable:
    def __init__(self, server_url, device_id):
        self.server_url = server_url
        self.device_id = device_id
        self.api_endpoint = f"{server_url}/api/temperature"
    
    def read_temperature(self):
        """
        Read temperature from sensor
        Replace this with your actual sensor reading code
        """
        
        # OPTION 1: DS18B20 Temperature Sensor (Raspberry Pi)
        try:
            import glob
            base_dir = '/sys/bus/w1/devices/'
            device_folder = glob.glob(base_dir + '28*')[0]
            device_file = device_folder + '/w1_slave'
            
            with open(device_file, 'r') as f:
                lines = f.readlines()
            
            if lines[0].strip()[-3:] == 'YES':
                equals_pos = lines[1].find('t=')
                if equals_pos != -1:
                    temp_string = lines[1][equals_pos+2:]
                    temp_c = float(temp_string) / 1000.0
                    return temp_c
        except Exception as e:
            print(f"DS18B20 error: {e}")
        
        # OPTION 2: DHT22 Sensor (Raspberry Pi)
        # Uncomment and install: pip install adafruit-circuitpython-dht
        # import board
        # import adafruit_dht
        # try:
        #     dht_device = adafruit_dht.DHT22(board.D4)
        #     temperature = dht_device.temperature
        #     return temperature
        # except RuntimeError as e:
        #     print(f"DHT22 error: {e}")
        
        # OPTION 3: BME280 Sensor (Raspberry Pi)
        # Uncomment and install: pip install adafruit-circuitpython-bme280
        # import board
        # import adafruit_bme280
        # try:
        #     i2c = board.I2C()
        #     bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)
        #     return bme280.temperature
        # except Exception as e:
        #     print(f"BME280 error: {e}")
        
        # OPTION 4: Simulated data for testing
        import random
        # Simulate body temperature between 36.0 and 38.0 °C
        return round(random.uniform(36.0, 38.0), 2)
    
    def send_temperature(self, temperature):
        """Send temperature reading to server"""
        data = {
            "temperature": temperature,
            "device_id": self.device_id,
            "timestamp": datetime.now().isoformat(),
            "unit": "celsius"
        }
        
        try:
            response = requests.post(
                self.api_endpoint,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Sent: {temperature}°C | Server: {result['message']}")
                return True
            else:
                print(f"✗ Error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"✗ Connection error: {e}")
            return False
    
    def run(self, interval=30):
        """Main loop - read and send temperature continuously"""
        print(f"🌡️  Temperature Wearable Device Started")
        print(f"📡 Server: {self.server_url}")
        print(f"🆔 Device ID: {self.device_id}")
        print(f"⏱️  Sending every {interval} seconds")
        print(f"🛑 Press Ctrl+C to stop\n")
        
        while True:
            try:
                # Read temperature
                temp = self.read_temperature()
                
                if temp is not None:
                    print(f"📊 Reading: {temp}°C", end=" | ")
                    self.send_temperature(temp)
                else:
                    print("⚠️  No temperature reading available")
                
                # Wait before next reading
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping wearable device...")
                break
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                time.sleep(interval)

def main():
    # Initialize wearable
    wearable = TemperatureWearable(
        server_url=SERVER_URL,
        device_id=DEVICE_ID
    )
    
    # Run continuously
    wearable.run(interval=SEND_INTERVAL)

if __name__ == "__main__":
    main()