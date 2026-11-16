"""Fetch Kyiv outage-queue status and optionally print it as a monitor."""

import time
from datetime import datetime

import requests


URL = "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/kyiv.json"


def get_kyiv_queue_status(now=None):
    """Return current Kyiv queue status, or None when the feed has no data."""
    now = now or datetime.now()
    response = requests.get(URL, timeout=15)
    response.raise_for_status()
    data = response.json()

    fact_data = data.get("fact", {}).get("data", {})
    date_keys = [key for key in fact_data if str(key).isdigit()]
    if not date_keys:
        return None

    groups = fact_data[max(date_keys, key=int)]
    hour_key = str(now.hour + 1)
    groups_on = []
    groups_off = []

    for group_name, hours in groups.items():
        if not isinstance(hours, dict):
            continue

        clean_name = group_name.replace("GPV", "")
        status = hours.get(hour_key, "yes")
        is_off = (
            status == "no"
            or (status == "first" and now.minute < 30)
            or (status == "second" and now.minute >= 30)
        )

        (groups_off if is_off else groups_on).append(clean_name)

    total = len(groups_on) + len(groups_off)
    if not total:
        return None

    return {
        "updated_at": now.strftime("%H:%M"),
        "percent_on": round(len(groups_on) / total * 100, 1),
        "groups_on": groups_on,
        "groups_off": groups_off,
    }


def monitor_kyiv_light():
    """Print Kyiv queue changes once per minute."""
    previous = None
    print("Моніторинг графіків світла (Київ) запущено...")
    print("Щоб зупинити програму, натисніть Ctrl + C\n")

    try:
        while True:
            try:
                status = get_kyiv_queue_status()
                summary = (
                    (status["groups_on"], status["groups_off"])
                    if status
                    else None
                )

                if status and summary != previous:
                    print(
                        f'[{status["updated_at"]}] У Києві зі світлом '
                        f'{status["percent_on"]}% черг'
                    )
                    print(
                        f'🟢 Зі світлом ({len(status["groups_on"])}): '
                        f'{", ".join(status["groups_on"])}'
                    )
                    print(
                        f'🔴 Без світла ({len(status["groups_off"])}): '
                        f'{", ".join(status["groups_off"])}\n'
                    )
                    previous = summary
                elif status is None and previous is not None:
                    print("Даних про черги поки немає.")
                    previous = None

            except Exception as error:
                print("Помилка перевірки графіка:", error)

            time.sleep(60)

    except KeyboardInterrupt:
        print("\nМоніторинг зупинено.")


if __name__ == "__main__":
    monitor_kyiv_light()
