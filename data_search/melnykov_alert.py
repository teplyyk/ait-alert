import time
import requests

PRIMARY_URL = "https://vadimklimenko.com" + "/map/statuses.json"
BACKUP_URL = "https://ubilling.net.ua" + "/aerialalerts/"

old_states = {}
first_run = True


def get_alerts_data():
    try:
        res = requests.get(PRIMARY_URL, timeout=8)
        res.raise_for_status()
        states = res.json().get("states", {})
        result = {}

        for region, info in states.items():
            if isinstance(info, dict):
                districts = info.get("districts", {})
                active_d = [d for d, d_info in districts.items() if isinstance(d_info, dict) and d_info.get("enabled")]

                if info.get("enabled"):
                    result[region] = "🔴 КРАСНАЯ (вся область)"
                elif active_d:
                    result[region] = f"🟡 ЖЕЛТАЯ ({', '.join(active_d)})"
        return result
    except Exception:
        res = requests.get(BACKUP_URL, timeout=8)
        res.raise_for_status()
        states = res.json().get("states", {})
        result = {}

        for region, info in states.items():
            if isinstance(info, dict) and info.get("alertnow"):
                result[region] = "🔴 ТРЕВОГА (резервный источник)"
        return result


print("Надежный мониторинг запущен...")
print("Чтобы остановить программу, нажмите Ctrl + C\n")

try:
    while True:
        try:
            current_states = get_alerts_data()

            for region, status in current_states.items():
                if old_states.get(region) != status:
                    print(f"{status} — {region}")

            for region in old_states:
                if region not in current_states:
                    print(f"🟢 ОТБОЙ — {region}")

            if not current_states and (first_run or old_states):
                print("Сейчас тревог по стране нет.")

            old_states = current_states
            first_run = False

        except Exception as error:
            print("Оба сервера временно недоступны, жду 15 сек:", error)

        time.sleep(15)

except KeyboardInterrupt:
    print("\nПрограмма остановлена.")
