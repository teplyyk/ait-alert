
import requests
import folium
import copy


API_URL = "https://svitlopulse.andrewboyko.name/api/v1/oblasts"


# Зіставлення slug API з назвами у GeoJSON
OBLAST_NAMES = {
    "vinnytsia-oblast": ["Вінницька область", "Vinnytsia Oblast"],
    "volyn-oblast": ["Волинська область", "Volyn Oblast"],
    "luhansk-oblast": ["Луганська область", "Luhansk Oblast"],
    "dnipropetrovsk-oblast": [
        "Дніпропетровська область",
        "Dnipropetrovsk Oblast",
        "Dnipropetrovsk"
    ],
    "donetsk-oblast": ["Донецька область", "Donetsk Oblast"],
    "zhytomyr-oblast": ["Житомирська область", "Zhytomyr Oblast"],
    "zakarpattia-oblast": [
        "Закарпатська область",
        "Zakarpattia Oblast"
    ],
    "zaporizhzhia-oblast": [
        "Запорізька область",
        "Zaporizhzhia Oblast"
    ],
    "ivano-frankivsk-oblast": [
        "Івано-Франківська область",
        "Ivano-Frankivsk Oblast"
    ],
    "kyiv-oblast": ["Київська область", "Kyiv Oblast"],
    "kirovohrad-oblast": [
        "Кіровоградська область",
        "Kirovohrad Oblast"
    ],
    "lviv-oblast": ["Львівська область", "Lviv Oblast"],
    "mykolaiv-oblast": ["Миколаївська область", "Mykolaiv Oblast"],
    "odesa-oblast": ["Одеська область", "Odesa Oblast"],
    "poltava-oblast": ["Полтавська область", "Poltava Oblast"],
    "rivne-oblast": ["Рівненська область", "Rivne Oblast"],
    "sumy-oblast": ["Сумська область", "Sumy Oblast"],
    "ternopil-oblast": ["Тернопільська область", "Ternopil Oblast"],
    "kharkiv-oblast": ["Харківська область", "Kharkiv Oblast"],
    "kherson-oblast": ["Херсонська область", "Kherson Oblast"],
    "khmelnytskyi-oblast": [
        "Хмельницька область",
        "Khmelnytskyi Oblast"
    ],
    "cherkasy-oblast": ["Черкаська область", "Cherkasy Oblast"],
    "chernihiv-oblast": ["Чернігівська область", "Chernihiv Oblast"],
    "chernivtsi-oblast": ["Чернівецька область", "Chernivtsi Oblast"],
    "kyiv-city": ["Київ", "Kyiv", "Kyiv City"],
    "crimea": ["Автономна Республіка Крим", "Crimea"],
    "sevastopol": ["Севастополь", "Sevastopol"]
}


def normalize_name(name):
    """Уніфікує назви для зіставлення."""

    return (
        str(name)
        .strip()
        .lower()
        .replace("'", "")
        .replace("’", "")
        .replace("-", " ")
        .replace("_", " ")
    )


def get_outages():
    """Отримує поточний статус електропостачання."""

    try:
        response = requests.get(
            API_URL,
            timeout=20
        )
        response.raise_for_status()

        data = response.json()

        if "oblasts" not in data:
            raise ValueError("API не повернув список областей")

        return data["oblasts"]

    except (requests.RequestException, ValueError) as error:
        print(f"Помилка API відключень: {error}")
        return []


def get_status_color(state, stale):
    """Визначає колір області за статусом."""

    if stale or state == "unknown":
        return "#808080"

    colors = {
        "on": "#2ecc71",
        "off": "#e74c3c",
        "partial": "#f39c12",
        "emergency": "#8e0000"
    }

    return colors.get(state, "#808080")


def add_outages_layer(map_object, geojson_data):
    """Зафарбовує області відповідно до відключень."""

    oblasts = get_outages()

    if not oblasts:
        print("Немає даних про відключення")
        return map_object

    # Створюємо копію, щоб не змінювати оригінальний GeoJSON
    geojson_copy = copy.deepcopy(geojson_data)

    # Створюємо словник назв GeoJSON
    name_to_slug = {}

    for slug, names in OBLAST_NAMES.items():
        for name in names:
            name_to_slug[normalize_name(name)] = slug

    # Зберігаємо статуси за slug
    status_by_slug = {
        oblast["slug"]: oblast
        for oblast in oblasts
    }

    matched = set()

    # Додаємо інформацію про відключення до кожної області
    for feature in geojson_copy["features"]:

        properties = feature.get("properties", {})

        geo_name = properties.get("name", "")

        slug = name_to_slug.get(
            normalize_name(geo_name)
        )

        outage = status_by_slug.get(slug)

        if outage is None:
            properties["power_status"] = "Немає даних"
            properties["off_share"] = "Невідомо"
            properties["freshness"] = "Не знайдено відповідності"
            properties["_color"] = "#808080"
            continue

        state = outage.get("state", "unknown")
        stale = outage.get("stale", True)
        off_share = outage.get("off_share")

        # Назви статусів українською
        status_names = {
            "on": "Світло є",
            "off": "Відключення",
            "partial": "Часткові відключення",
            "emergency": "Аварійні обмеження",
            "unknown": "Невідомо"
        }

        properties["power_status"] = status_names.get(
            state, "Невідомо"
        )

        if isinstance(off_share, (int, float)):
            properties["off_share"] = (
                f"{off_share * 100:.1f}%"
            )
        else:
            properties["off_share"] = "Невідомо"

        properties["freshness"] = (
            "Застарілі дані" if stale
            else "Не позначені як застарілі"
        )

        properties["_color"] = get_status_color(
            state, stale
        )

        matched.add(slug)

    # Визначаємо стиль кожного полігона
    def style_function(feature):

        color = feature["properties"].get(
            "_color", "#808080"
        )

        return {
            "fillColor": color,
            "color": "#111111",
            "weight": 2,
            "fillOpacity": 0.85
        }

    # Підсвічування при наведенні
    def highlight_function(feature):

        return {
            "color": "#ffffff",
            "weight": 3,
            "fillOpacity": 1
        }

    # Окремий шар відключень
    layer = folium.FeatureGroup(
        name="Відключення світла",
        show=False
    )

    folium.GeoJson(
        geojson_copy,
        name="Статус електропостачання",
        style_function=style_function,
        highlight_function=highlight_function,

        tooltip=folium.GeoJsonTooltip(
            fields=["name", "power_status"],
            aliases=["Область:", "Статус:"]
        ),

        popup=folium.GeoJsonPopup(
            fields=[
                "name",
                "power_status",
                "off_share",
                "freshness"
            ],
            aliases=[
                "Область:",
                "Статус:",
                "Частка черг без світла:",
                "Актуальність:"
            ]
        )
    ).add_to(layer)

    layer.add_to(map_object)

    print(
        f"Областей зіставлено: {len(matched)} "
        f"із {len(oblasts)} записів API"
    )

    return map_object
