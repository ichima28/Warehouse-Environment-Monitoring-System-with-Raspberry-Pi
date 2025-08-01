# Warehouse-Environment-Monitoring-System-with-Raspberry-Pi
# Warehouse Temperature and Humidity Monitoring System (Raspberry Pi + Node-RED + MQTT)

## Overview

This project is a real-time temperature and humidity monitoring system for warehouses. It uses a Raspberry Pi with a DHT22 sensor and buzzer to detect environmental changes and sends alerts via MQTT. A Node-RED dashboard is used to display sensor data and warning notifications.

## Features

- Read temperature and humidity from a DHT22 sensor
- Send data via MQTT to a broker
- Display real-time data on Node-RED Dashboard
- Trigger alerts for:
  - High temperature (red background)
  - High humidity (blue background)
  - Low temperature (light blue background)
- Alert throttling to avoid repetitive triggers

## Technologies

- Raspberry Pi (tested on Raspberry Pi 5)
- Python 3
- Node-RED
- MQTT (e.g., Mosquitto)
- DHT22 Sensor


## Folder Structure
warehouse-monitoring/
├── dashboard node-red/
│ └── flows.json # Exported Node-RED flow
├── raspberry-pi/
│ ├── warehouse_sensor.py # Python script for DHT22 + MQTT
│ ├── requirements.txt # Python dependencies
│ ├── utils/
│ │ └── mqtt_client.py # MQTT publish wrapper
│ └── alert/
├── dashboard_screenshots/
│ └── demo-ui.png # Screenshot of Node-RED UI
├── .gitignore
└── README.md


## How It Works

1. **Sensor Data Collection**:  
   Raspberry Pi reads temperature and humidity from the DHT22 every 10 seconds.

2. **MQTT Publishing**:  
   Sensor data is formatted as JSON and sent to the `warehouse/data` topic. Alerts are sent to `warehouse/alerts`.

3. **Node-RED Flow**:  
   - Subscribes to `warehouse/data` and displays temperature/humidity using gauges.
   - Listens to `warehouse/alerts` and triggers popup warnings or buzzer.
   - Displays popups with color codes based on alert type.
   - Includes a button to manually turn off the buzzer.

## Setup Instructions
### Firstly
```bash
pip3 install -r requirements.txt
```
- If you are using virtual enviroment remember to activate it
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
### Raspberry Pi Side

1. **Install dependencies**:

   ```bash
   sudo apt update
   sudo apt install python3-pip
   pip3 install paho-mqtt adafruit-circuitpython-dht
   sudo apt install libgpiod2
2. **Connect to hardware**
  - DHT22: Connect to GPIO(e.g., GPIO4)
  - Led: Connect to GPIO(e.g., GPIO17)
  - Buzzer (Optional): Connect via transistor or relay to a GPIO (e.g., GPIO22)
3. **Run the script**
    ```bash
    python3 warehouse_sensor.py

### Node-RED Side
1. Install Node-RED:
```bash
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
```
2. Start Node-RED and open it in your browser:
    http://<your-pi-ip>:1880
3. Import flows.json to Node-RED Editor
4. Deploy the flow
   
### MQTT Topics
| Topic               | Description                                       |
| ------------------- | ------------------------------------------------- |
| `warehouse/data`    | Publishes temperature & humidity readings         |
| `warehouse/alerts`  | Publishes warning messages                        |
| `warehouse/control` | Subscribes to buzzer control (e.g., `BUZZER_OFF`) |

### UI Dashboard
- Gauge for Temperature (°C)
- Gauge for Humidity (%)
- Alert Popup with color-coded background
- Button to stop buzzer manually

📷 Screenshots

📝 Future Improvements
- Combined warning with buzzer 
- Manual buzzer control via Dashboard button
- Data logging to CSV or cloud database
- Email/SMS notifications
- Multi-zone warehouse monitoring
