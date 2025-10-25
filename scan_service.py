import asyncio
from bleak import BleakClient, BleakScanner

# Replace with your Pi's Bluetooth MAC address
PI_ADDRESS = "B8:27:EB:B1:FA:27"

# Replace with the UUID of your temperature characteristic
TEMP_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef0"

async def main():
    print(f"🔍 Scanning for device {PI_ADDRESS}...")
    device = await BleakScanner.find_device_by_address(PI_ADDRESS, timeout=10.0)

    if not device:
        print("❌ Device not found. Make sure the Pi is on and advertising.")
        return

    async with BleakClient(device) as client:
        print(f"✅ Connected to {device.address}")

        print("📜 Discovering services...")
        for service in client.services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                print(f"  ↳ Characteristic: {char.uuid}, properties: {char.properties}")

        # Read the temperature characteristic
        try:
            temp_data = await client.read_gatt_char(TEMP_CHAR_UUID)
            # Convert bytes to float (your Bluezero code uses float)
            temperature = float(int.from_bytes(temp_data, byteorder='little') / 10)
            print(f"🌡️ Temperature reading: {temperature}°C")
        except Exception as e:
            print(f"❌ Failed to read temperature: {e}")

asyncio.run(main())
