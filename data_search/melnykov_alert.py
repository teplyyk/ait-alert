import time
from datetime import datetime
import requests

PRIMARY_URL = "https://vadimklimenko.com" + "/map/statuses.json"
BACKUP_URL = "https://ubilling.net.ua" + "/aerialalerts/"

def _active_regions(states, is_primary):
    result = {}
    for region, info in states.items():
        if not isinstance(info, dict):
            continue

        if is_primary:
            districts = info.get("districts", {})
            active_districts = [
                name for name, district in districts.items()
                if isinstance(district, dict) and district.get("enabled")
            ]
            if info.get("enabled"):
                result[region] = "🔴 КРАСНАЯ (вся область)"
            elif active_districts:
                result[region] = f"🟡 ЖЕЛТАЯ ({', '.join(active_districts)})"
        elif info.get("alertnow"):
            result[region] = "🔴 ТРЕВОГА (резервний источник)"
    return result


def get_alerts_snapshot():
    """Return active alerts and source freshness metadata for the home page."""
    sources = (
        (PRIMARY_URL, "Основне джерело", True),
        (BACKUP_URL, "Резервне джерело", False),
    )
    errors = []

    for url, source_name, is_primary in sources:
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            payload = response.json()
            states = payload.get("states")
            if not isinstance(states, dict):
                raise ValueError("У відповіді джерела немає списку областей")

            source_time = (
                payload.get("cachedat")
                or payload.get("updated_at")
                or payload.get("updatedAt")
                or payload.get("at")
            )
            time_label = "Дані джерела оновлено"
            has_data_timestamp = bool(source_time)
            if not source_time:
                source_time = response.headers.get("Date")
                time_label = "Перевірено"
            if not source_time:
                source_time = datetime.now().astimezone().isoformat()

            status = source_name + " доступне"
            status_class = "ok" if is_primary else "warning"
            if has_data_timestamp:
                try:
                    parsed_time = datetime.fromisoformat(
                        str(source_time).replace("Z", "+00:00")
                    )
                    if parsed_time.tzinfo is None:
                        parsed_time = parsed_time.astimezone()
                    age_minutes = (
                        datetime.now().astimezone() - parsed_time.astimezone()
                    ).total_seconds() / 60
                    if age_minutes > 15:
                        status = "Дані застаріли"
                        status_class = "warning"
                except (TypeError, ValueError):
                    pass

            return {
                "available": True,
                "alerts": _active_regions(states, is_primary),
                "source": source_name,
                "status": status,
                "status_class": status_class,
                "updated_at": source_time,
                "time_label": time_label,
            }
        except Exception as error:
            errors.append(f"{source_name}: {error}")

    print("Обидва джерела тривог недоступні:", "; ".join(errors))
    return {
        "available": False,
        "alerts": {},
        "source": "Джерело недоступне",
        "status": "Джерело недоступне",
        "status_class": "offline",
        "updated_at": datetime.now().astimezone().isoformat(),
        "time_label": "Остання перевірка",
    }


def get_alerts_data():
    """Return active regions from the primary or backup alert source."""
    return get_alerts_snapshot()["alerts"]


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
