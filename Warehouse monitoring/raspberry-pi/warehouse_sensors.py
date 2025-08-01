import os, csv, json, time
from datetime import datetime
from collections import deque
from statistics import mean

import board, adafruit_dht
from gpiozero import LED
import paho.mqtt.client as mqtt

DHT_TYPE = adafruit_dht.DHT11
DHT_PIN = board.D4
LED_PIN = 17
READ_INTERVAL_SEC = 5
TEMP_MAX = 30.0
TEMP_HYST = 0.5
HUMI_MIN = 40.0
HUMI_MAX = 70.0
ALERT_INTERVAL_SEC = 10
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_DATA = "warehouse/sensors/dht11"
TOPIC_ALERT = "warehouse/alerts"
LOG_DIR = "logs"
ROLLING_WINDOW_SEC = 300
WINDOW_LEN = max(1, ROLLING_WINDOW_SEC // READ_INTERVAL_SEC)

def ensure_log_dir():
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

def log_path_for_today():
    return os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d") + ".csv")

def ensure_csv_header(path):
    exists = os.path.exists(path)
    f = open(path, "a", newline="")
    w = csv.writer(f)
    if not exists:
        w.writerow([
            "timestamp", "temperature_c", "humidity_pct",
            f"temp_avg_{ROLLING_WINDOW_SEC}s", f"humi_avg_{ROLLING_WINDOW_SEC}s",
            f"temp_min_{ROLLING_WINDOW_SEC}s", f"temp_max_{ROLLING_WINDOW_SEC}s",
            f"humi_min_{ROLLING_WINDOW_SEC}s", f"humi_max_{ROLLING_WINDOW_SEC}s"
        ])
    return f, w
    
def compute_stats(ts, hs):
    return mean(ts), mean(hs), min(ts), max(ts), min(hs), max(hs)

def main():
    dht = DHT_TYPE(DHT_PIN)
    led = LED(LED_PIN)
    temps = deque(maxlen=WINDOW_LEN)
    humis = deque(maxlen=WINDOW_LEN)
    client = mqtt.Client()
    client.reconnect_delay_set(1, 10)
    client.loop_start()

    connected = {"ok": False}
    last_alert_sent = 0

    def on_connect(c, u, flags, rc):
        connected["ok"] = (rc == 0)
    def on_disconnect(c, u, rc):
        connected["ok"] = False

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    def mqtt_connect():
        if not connected["ok"]:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 60)
            except Exception:
                pass

    ensure_log_dir()
    mqtt_connect()
    csv_file = None
    writer = None
    current_log = None

    try:
        while True:
            try:
                temperature = dht.temperature
                humidity = dht.humidity
            except RuntimeError:
                time.sleep(READ_INTERVAL_SEC)
                continue
            except Exception:
                try: dht.exit()
                except: pass
                time.sleep(1)
                dht = DHT_TYPE(DHT_PIN)
                continue

            if (temperature is None) or (humidity is None):
                time.sleep(READ_INTERVAL_SEC)
                continue

            temperature = float(temperature)
            humidity = float(humidity)
            temps.append(temperature)
            humis.append(humidity)
            ta, ha, tmin, tmax, hmin, hmax = compute_stats(temps, humis)

            payload = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "temperature_c": round(temperature, 2),
                "humidity_pct": round(humidity, 2),
                "avg": {"temp_c": round(ta, 2), "humi_pct": round(ha, 2)},
                "minmax": {
                    "temp_min": round(tmin, 2), "temp_max": round(tmax, 2),
                    "humi_min": round(hmin, 2), "humi_max": round(hmax, 2)
                },
                "window_sec": ROLLING_WINDOW_SEC
            }

            print(f"{payload['ts']}  Temperature= {temperature} oC  Humidity= {humidity}%")

            path = log_path_for_today()
            if current_log != path:
                if csv_file:
                    csv_file.close()
                csv_file, writer = ensure_csv_header(path)
                current_log = path
                
            writer.writerow([
                payload["ts"], payload["temperature_c"], payload["humidity_pct"],
                payload["avg"]["temp_c"], payload["avg"]["humi_pct"],
                payload["minmax"]["temp_min"], payload["minmax"]["temp_max"],
                payload["minmax"]["humi_min"], payload["minmax"]["humi_max"]
            ])
            csv_file.flush()

            try:
                if connected["ok"]:
                    client.publish(TOPIC_DATA, json.dumps(payload), qos=0, retain=True)
                else:
                    mqtt_connect()
            except Exception:
                pass

            now = time.time()
            alerts = []

            if temperature >= TEMP_MAX:
                led.on()
                alerts.append(f"High temperature: {temperature} oC")
            elif temperature < (TEMP_MAX - TEMP_HYST):
                led.off()

            if humidity < HUMI_MIN or humidity > HUMI_MAX:
                alerts.append(f"Humidity {'Low' if humidity < HUMI_MIN else 'High'}: {humidity}%")

            if alerts and (now - last_alert_sent >= ALERT_INTERVAL_SEC):
                alert_msg = {
                    "timestamp": payload["ts"],
                    "level": "warning",
                    "message": " | ".join(alerts)
                }
                try:
                    if connected["ok"]:
                        client.publish(TOPIC_ALERT, json.dumps(alert_msg), qos=1, retain=True)
                        last_alert_sent = now
                    else:
                        mqtt_connect()
                except Exception:
                    pass

            time.sleep(READ_INTERVAL_SEC)

    finally:
        try: csv_file.close()
        except: pass
        try: dht.exit()
        except: pass
        try: led.off()
        except: pass
        try:
            client.loop_stop()
            client.disconnect()
        except: pass

if __name__ == "__main__":
    main()
