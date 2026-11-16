import time
import requests

PRIMARY_URL = "https://vadimklimenko.com" + "/map/statuses.json"
BACKUP_URL = "https://ubilling.net.ua" + "/aerialalerts/"

def get_alerts_data():
    """Return active regions from the primary or backup alert source."""
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


def monitor_alerts():
    """Print alert changes when running as a standalone monitor."""
    old_states = {}
    first_run = True

    print("Надійний моніторинг запущено...")
    print("Щоб зупинити програму, натисніть Ctrl + C\n")

    try:
        while True:
            try:
                current_states = get_alerts_data()

                for region, status in current_states.items():
                    if old_states.get(region) != status:
                        print(f"{status} — {region}")

                for region in old_states:
                    if region not in current_states:
                        print(f"🟢 ВІДБІЙ — {region}")

                if not current_states and (first_run or old_states):
                    print("Зараз тривог по країні немає.")

                old_states = current_states
                first_run = False

            except Exception as error:
                print("Обидва сервери тимчасово недоступні, чекаю 15 сек:", error)

            time.sleep(15)

    except KeyboardInterrupt:
        print("\nПрограму зупинено.")


if __name__ == "__main__":
    monitor_alerts()
