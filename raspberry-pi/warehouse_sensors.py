import os, csv, json, time
from datetime import datetime
from collections import deque
from statistics import mean
import board, adafruit_dht
from gpiozero import LED, Buzzer
import paho.mqtt.client as mqtt
import socket

DHT_TYPE = adafruit_dht.DHT11
DHT_PIN = board.D4
LED_PIN = 14
GREEN_LED_PIN = 15
BUZZER_PIN = 18
buzzer = Buzzer(BUZZER_PIN)
READ_INTERVAL_SEC = 5
ALERT_INTERVAL_SEC = 10
BEEP_INTERVAL_SEC = 10
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
LOG_DIR = "logs"
CONFIG_DIR = "config"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.txt")
ROLLING_WINDOW_SEC = 300
WINDOW_LEN = max(1, ROLLING_WINDOW_SEC // READ_INTERVAL_SEC)

# Giá trị cấu hình mặc định
DEFAULT_CONFIG = {
    "TEMP_MAX": 32.0,
    "TEMP_MIN": 20.0,
    "HUMI_MIN": 40.0,
    "HUMI_MAX": 70.0,
    "pi_name": socket.gethostname()  # Giá trị mặc định cho pi_name là hostname
}

# Lấy DEVICE_ID từ pi_name trong file cấu hình
DEVICE_ID = None  # Sẽ được gán sau khi load_config

# Các topic MQTT riêng cho từng thiết bị
TOPIC_ALERT = None  # Sẽ được gán sau khi có DEVICE_ID
TOPIC_CONFIG = None  # Sẽ được gán sau khi có DEVICE_ID

# Biến cấu hình toàn cục
TEMP_MAX = DEFAULT_CONFIG["TEMP_MAX"]
TEMP_MIN = DEFAULT_CONFIG["TEMP_MIN"]
HUMI_MIN = DEFAULT_CONFIG["HUMI_MIN"]
HUMI_MAX = DEFAULT_CONFIG["HUMI_MAX"]

def load_config():
    """Tải cấu hình từ config.txt hoặc tạo mới với giá trị mặc định."""
    global TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX, DEVICE_ID, TOPIC_ALERT, TOPIC_CONFIG
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            for key, value in DEFAULT_CONFIG.items():
                f.write(f"{key}={value}\n")
    
    config = DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in config:
                        if key in ["TEMP_MAX", "TEMP_MIN", "HUMI_MIN", "HUMI_MAX"]:
                            value = float(value)
                        config[key] = value
    except Exception as e:
        print(f"Lỗi đọc file cấu hình: {e}. Sử dụng giá trị mặc định.")
    
    # Cập nhật biến toàn cục
    TEMP_MAX = config["TEMP_MAX"]
    TEMP_MIN = config["TEMP_MIN"]
    HUMI_MIN = config["HUMI_MIN"]
    HUMI_MAX = config["HUMI_MAX"]
    DEVICE_ID = config["pi_name"]
    
    # Cập nhật các topic MQTT
    TOPIC_ALERT = f"warehouse/alerts/{DEVICE_ID}"
    TOPIC_CONFIG = f"warehouse/config/{DEVICE_ID}"
    
    return TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX, DEVICE_ID

def update_config_file(config_data):
    """Cập nhật config.txt với giá trị mới từ thông điệp MQTT."""
    global TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX
    try:
        # Xác thực dữ liệu cấu hình nhận được
        new_config = DEFAULT_CONFIG.copy()
        for key in ["TEMP_MAX", "TEMP_MIN", "HUMI_MIN", "HUMI_MAX"]:
            if key in config_data:
                value = float(config_data[key])
                if value < 0:
                    print(f"Giá trị {key} không hợp lệ: {value}. Phải không âm.")
                    return False
                new_config[key] = value
        # Giữ nguyên pi_name từ file cấu hình hiện tại
        new_config["pi_name"] = DEVICE_ID
        
        # Kiểm tra các ràng buộc logic
        if new_config["TEMP_MAX"] <= new_config["TEMP_MIN"]:
            print("Lỗi: TEMP_MAX phải lớn hơn TEMP_MIN.")
            return False
        if new_config["HUMI_MAX"] <= new_config["HUMI_MIN"]:
            print("Lỗi: HUMI_MAX phải lớn hơn HUMI_MIN.")
            return False
        
        # Ghi vào file cấu hình
        with open(CONFIG_FILE, "w") as f:
            for key, value in new_config.items():
                f.write(f"{key}={value}\n")
        
        # Cập nhật biến toàn cục
        TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX, _ = load_config()
        print(f"Cấu hình đã được cập nhật cho thiết bị {DEVICE_ID}: "
              f"TEMP_MAX={TEMP_MAX}, TEMP_MIN={TEMP_MIN}, "
              f"HUMI_MIN={HUMI_MIN}, HUMI_MAX={HUMI_MAX}")
        if buzzer:
            for _ in range(2):
                buzzer.on()
                time.sleep(0.1)  # Thời gian ngắn hơn cho tần số cao
                buzzer.off()
                time.sleep(0.1)
        return True
    except Exception as e:
        print(f"Lỗi cập nhật file cấu hình: {e}")
        return False
        
def ensure_log_dir():
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

def log_path_for_today():
    return os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d") + ".csv")

def beep_buzzer(buzzer):
    for _ in range(3):
        buzzer.on()
        time.sleep(0.5)
        buzzer.off()
        time.sleep(0.5)
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
    global TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX, DEVICE_ID
    load_config()
    
    dht = DHT_TYPE(DHT_PIN)
    led = LED(LED_PIN)
    green_led = LED(GREEN_LED_PIN)
    #buzzer = Buzzer(BUZZER_PIN)
    temps = deque(maxlen=WINDOW_LEN)
    humis = deque(maxlen=WINDOW_LEN)
    client = mqtt.Client()
    client.reconnect_delay_set(1, 10)
    connected = {"ok": False}
    last_alert_sent = 0
    last_beep_time = 0

    def on_connect(c, u, flags, rc):
        connected["ok"] = (rc == 0)
        if connected["ok"]:
            print(f"Đã kết nối tới MQTT broker cho thiết bị {DEVICE_ID}")
            client.subscribe(TOPIC_CONFIG, qos=1)
        else:
            print("Không thể kết nối tới MQTT broker")

    def on_disconnect(c, u, rc):
        connected["ok"] = False
        print("Mất kết nối tới MQTT broker")
    
    def on_message(c, u, msg):
        if msg.topic == TOPIC_CONFIG:
            try:
                config_data = json.loads(msg.payload.decode())
                if update_config_file(config_data):
                    print(f"Nhận và áp dụng cấu hình mới: {config_data}")
                else:
                    print(f"Không thể áp dụng cấu hình: {config_data}")
            except Exception as e:
                print(f"Lỗi xử lý thông điệp cấu hình MQTT: {e}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.loop_start()

    def mqtt_connect():
        if not connected["ok"]:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 60)
            except Exception as e:
                print(f"Lỗi kết nối MQTT: {e}")

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

            now = time.time()
            alerts = []

            if temperature >= TEMP_MAX or temperature <= TEMP_MIN:
                led.on()
                if now - last_beep_time >= BEEP_INTERVAL_SEC:
                    beep_buzzer(buzzer)
                    last_beep_time = now
                alerts.append(f"{'Nhiệt độ cao' if temperature >= TEMP_MAX else 'Nhiệt độ thấp'}: {temperature} oC")
            elif TEMP_MIN < temperature < TEMP_MAX:
                led.off()
                buzzer.off()

            if humidity < HUMI_MIN or humidity > HUMI_MAX:
                alerts.append(f"Độ ẩm {'thấp' if humidity < HUMI_MIN else 'cao'}: {humidity}%")
                green_led.on()
                if now - last_beep_time >= BEEP_INTERVAL_SEC:
                    beep_buzzer(buzzer)
                    last_beep_time = now
            elif HUMI_MIN < humidity < HUMI_MAX:
                buzzer.off()
                green_led.off()
                
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
                except Exception as e:
                    print(f"Lỗi gửi cảnh báo: {e}")

            time.sleep(READ_INTERVAL_SEC)

    finally:
        try: csv_file.close()
        except: pass
        try: dht.exit()
        except: pass
        try: led.off()
        except: pass
        try: green_led.off()
        except: pass
        try: buzzer.off()
        except: pass
        try:
            client.loop_stop()
            client.disconnect()
        except: pass

if __name__ == "__main__":
    main()