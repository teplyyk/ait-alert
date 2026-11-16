from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime

from flask import Flask, render_template_string
import folium
import requests
import unicodedata

from accessibility import add_accessibility_layer, get_accessibility_source_status
from data_search.melnykov_alert import get_alerts_data, get_alerts_snapshot
from melnikov_light import get_kyiv_queue_status
from outages import add_outages_layer, get_place_details, get_power_source_status

app = Flask(__name__)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/"
    "darmat1/ukraine-geo-data/main/geodata/Ukraine.geojson"
)

DEFAULT_REGION_COLOR = "#808080"
ALERT_COLORS = {
    "yellow": "#ffd43b",
    "red": "#e53935",
}

REGION_ALIASES = {
    "vinnytsia": ("Vinnytsia", "Vinnytska", "Вінницька", "Винницкая"),
    "volyn": ("Volyn", "Volynska", "Волинська", "Волынская"),
    "dnipropetrovsk": (
        "Dnipropetrovsk", "Dnipropetrovska", "Dnipro",
        "Дніпропетровська", "Днепропетровская",
    ),
    "donetsk": ("Donetsk", "Donetska", "Донецька", "Донецкая"),
    "zhytomyr": ("Zhytomyr", "Zhytomyrska", "Житомирська", "Житомирская"),
    "zakarpattia": (
        "Zakarpattia", "Zakarpatska", "Закарпатська", "Закарпатская",
    ),
    "zaporizhzhia": (
        "Zaporizhzhia", "Zaporizhzhia Oblast", "Zaporizka",
        "Запорізька", "Запорожская",
    ),
    "ivano_frankivsk": (
        "Ivano-Frankivsk", "Ivano-Frankivska", "Івано-Франківська",
    ),
    "kyiv_oblast": (
        "Kyiv Oblast", "Kiev Oblast", "Kyivska", "Київська",
        "Киевская область",
    ),
    "kyiv_city": (
        "Kyiv", "Kiev", "Kyiv City", "Kiev City", "Київ", "Киев",
    ),
    "kirovohrad": (
        "Kirovohrad", "Kirovohradska", "Кіровоградська",
        "Кировоградская", "Kropyvnytskyi",
    ),
    "luhansk": ("Luhansk", "Luhanska", "Луганська", "Луганская"),
    "lviv": ("Lviv", "Lvivska", "Львівська", "Львовская"),
    "mykolaiv": ("Mykolaiv", "Mykolaivska", "Миколаївська", "Николаевская"),
    "odesa": ("Odesa", "Odessa", "Odeska", "Одеська", "Одесская"),
    "poltava": ("Poltava", "Poltavska", "Полтавська", "Полтавская"),
    "rivne": ("Rivne", "Rivnenska", "Рівненська", "Ровенская"),
    "sumy": ("Sumy", "Sumska", "Сумська", "Сумская"),
    "ternopil": ("Ternopil", "Ternopilska", "Тернопільська", "Тернопольская"),
    "kharkiv": ("Kharkiv", "Kharkivska", "Харківська", "Харьковская"),
    "kherson": ("Kherson", "Khersonska", "Херсонська", "Херсонская"),
    "khmelnytskyi": (
        "Khmelnytskyi", "Khmelnytska", "Хмельницька", "Хмельницкая",
    ),
    "cherkasy": ("Cherkasy", "Cherkaska", "Черкаська", "Черкасская"),
    "chernivtsi": ("Chernivtsi", "Chernivetska", "Чернівецька", "Черновицкая"),
    "chernihiv": ("Chernihiv", "Chernihivska", "Чернігівська", "Черниговская"),
    "crimea": (
        "Crimea", "Autonomous Republic of Crimea", "Автономна Республіка Крим",
        "Крым",
    ),
    "sevastopol": ("Sevastopol", "Севастополь"),
}

_CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ye", "ж": "zh", "з": "z", "и": "y", "і": "i",
    "ї": "yi", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ю": "yu", "я": "ya", "ь": "", "ъ": "",
    "ы": "y", "э": "e", "ё": "yo",
})


def normalize_region_name(name):
    value = unicodedata.normalize("NFKD", str(name)).casefold()
    value = value.translate(_CYRILLIC_TO_LATIN)
    value = "".join(character for character in value if character.isalnum())

    for suffix in ("oblast", "region", "area"):
        if value.endswith(suffix):
            base = value[:-len(suffix)]
            # Keep Kyiv Oblast distinct from Kyiv City.
            value = base + suffix if base in ("kyiv", "kiev", "kiyev") else base
            break

    return value


_CANONICAL_REGION_BY_ALIAS = {
    normalize_region_name(alias): canonical
    for canonical, aliases in REGION_ALIASES.items()
    for alias in (canonical, *aliases)
}


def canonical_region_name(name):
    normalized = normalize_region_name(name)
    return _CANONICAL_REGION_BY_ALIAS.get(normalized, normalized)


def alert_color(status):
    value = str(status).casefold()
    if "🟡" in value or "yellow" in value or "желт" in value:
        return ALERT_COLORS["yellow"]
    if "🔴" in value or "red" in value or "красн" in value:
        return ALERT_COLORS["red"]
    # Entries returned by get_alerts_data are active alerts; unknown active
    # statuses should remain visible as red.
    return ALERT_COLORS["red"]

HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>Мапа України</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            background: radial-gradient(ellipse at 50% 0%, #132333 0%, #080b10 55%);
            color: #f4f7fb;
            font-family: Arial, sans-serif;
        }
        main { max-width: 1120px; margin: 0 auto; padding: 10vh 28px 48px; }
        .hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 380px); align-items: center; gap: 28px; }
        .hero-art { display: flex; justify-content: center; align-items: center; min-width: 0; }
        .hero-art img { display: block; width: 100%; max-width: 380px; height: auto; filter: drop-shadow(0 18px 35px rgba(36, 151, 194, .16)); }
        .eyebrow { color: #7fb5d8; font-size: 13px; letter-spacing: .18em; text-transform: uppercase; }
        h1 { margin: 12px 0; font-size: clamp(36px, 6vw, 64px); }
        .intro { max-width: 620px; color: #aebdca; font-size: 18px; line-height: 1.6; }
        .cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin-top: 46px; }
        .card {
            display: flex; min-height: 290px; flex-direction: column; padding: 25px;
            border: 1px solid #263746; border-radius: 18px; background: #101923;
            color: inherit; text-decoration: none; transition: transform .18s, border-color .18s, background .18s;
        }
        .card:hover { transform: translateY(-4px); border-color: #5d9fc4; background: #14212d; }
        .icon { font-size: 30px; }
        h2 { margin: 23px 0 8px; font-size: 23px; }
        .card p { margin: 0; color: #aebdca; line-height: 1.5; }
        .source-info { margin-top: 18px; padding-top: 14px; border-top: 1px solid #263746; }
        .source-status { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.4; font-weight: 700; }
        .status-dot { flex: 0 0 9px; width: 9px; height: 9px; margin-top: 3px; border-radius: 50%; background: currentColor; box-shadow: 0 0 10px currentColor; }
        .ok { color: #70d69a; }
        .warning { color: #ffd166; }
        .offline { color: #ff7777; }
        .local { color: #8ec8ea; }
        .source-info .source-summary { margin-top: 7px; color: #d0d9e2; font-size: 13px; }
        .source-time { margin-top: 7px; color: #94a4b2; font-size: 11px; line-height: 1.4; }
        .open { margin-top: auto; padding-top: 20px; color: #8ec8ea; font-weight: 700; }
        @media (max-width: 760px) {
            main { padding: 48px 18px 30px; }
            .hero { grid-template-columns: 1fr; gap: 4px; }
            .hero-art { width: min(310px, 88%); justify-self: center; }
            .hero-art img { max-height: 185px; }
            .cards { grid-template-columns: 1fr; margin-top: 14px; }
            .card { min-height: 250px; }
        }
    </style>
</head>
<body>
    <main>
        <section class="hero">
            <div class="hero-copy">
                <div class="eyebrow">Інформаційні карти</div>
                <h1>Україна зараз</h1>
                <p class="intro">Оберіть карту, щоб переглянути дані про доступність, повітряні тривоги або електропостачання.</p>
            </div>
            <div class="hero-art" aria-hidden="true">
                <img src="{{ url_for('static', filename='ukraine-emblem.svg') }}" alt="">
            </div>
        </section>
        <nav class="cards" aria-label="Карти">
            <a class="card" href="/services">
                <span class="icon" aria-hidden="true">♿</span>
                <h2>Сервіс</h2>
                <p>Об'єкти безбар'єрності та доступності по Україні.</p>
                <div class="source-info">
                    <div class="source-status {{ services_status.status_class }}"><span class="status-dot"></span>{{ services_status.status }}</div>
                    <p class="source-summary">{{ services_status.summary }}</p>
                    <div class="source-time">{{ services_status.time_label }}: {{ services_status.updated_at }}</div>
                </div>
                <span class="open">Відкрити карту →</span>
            </a>
            <a class="card" href="/alerts">
                <span class="icon" aria-hidden="true">◉</span>
                <h2>Тривоги</h2>
                <p>Поточні тривоги по областях України.</p>
                <div class="source-info">
                    <div class="source-status {{ alerts_status.status_class }}"><span class="status-dot"></span>{{ alerts_status.status }}</div>
                    <p class="source-summary">{{ alerts_status.summary }}</p>
                    <div class="source-time">{{ alerts_status.time_label }}: {{ alerts_status.updated_at }}</div>
                </div>
                <span class="open">Відкрити карту →</span>
            </a>
            <a class="card" href="/power">
                <span class="icon" aria-hidden="true">⚡</span>
                <h2>Світло</h2>
                <p>Статус електропостачання та графік черг у Києві.</p>
                <div class="source-info">
                    <div class="source-status {{ power_status.status_class }}"><span class="status-dot"></span>{{ power_status.status }}</div>
                    <p class="source-summary">{{ power_status.summary }}</p>
                    <div class="source-time">{{ power_status.time_label }}: {{ power_status.updated_at }}</div>
                </div>
                <span class="open">Відкрити карту →</span>
            </a>
        </nav>
    </main>
</body>
</html>
"""

MAP_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>{{ title }} — Україна зараз</title>
    <style>
        * { box-sizing: border-box; }
        html, body { margin: 0; width: 100%; height: 100%; background: #080b10; color: #f4f7fb; font-family: Arial, sans-serif; }
        header { height: 68px; display: flex; align-items: center; gap: 18px; padding: 0 22px; border-bottom: 1px solid #263746; background: #0c131b; }
        .home { color: #8ec8ea; text-decoration: none; font-weight: 700; white-space: nowrap; }
        .heading { min-width: 0; }
        h1 { margin: 0; font-size: 21px; }
        .subtitle { margin: 3px 0 0; color: #aebdca; font-size: 13px; }
        .map-container { width: 100%; height: calc(100vh - 68px); overflow: hidden; }
        .map-container iframe { display: block; width: 100%; height: 100%; border: 0; }
        .summary {
            position: absolute; z-index: 1000; top: 82px; left: 16px; width: min(360px, calc(100vw - 32px));
            padding: 14px 16px; border: 1px solid #344858; border-radius: 12px; background: rgba(12, 19, 27, .94);
            box-shadow: 0 8px 26px rgba(0,0,0,.25); color: #eaf1f7; line-height: 1.5; font-size: 13px;
        }
        .summary strong { display: block; margin-bottom: 5px; font-size: 14px; }
        .summary .percent { color: #90d8a1; font-weight: 700; }
        @media (max-width: 560px) {
            header { height: 62px; gap: 12px; padding: 0 14px; }
            h1 { font-size: 18px; }
            .subtitle { font-size: 11px; }
            .map-container { height: calc(100vh - 62px); }
        }
    </style>
</head>
<body>
    <header>
        <a class="home" href="/">← Головна</a>
        <div class="heading">
            <h1>{{ title }}</h1>
            <p class="subtitle">{{ subtitle }}</p>
        </div>
    </header>
    {% if kyiv_status is not none %}
    <aside class="summary">
        <strong>Київські черги · дані на {{ kyiv_status.updated_at }}</strong>
        <span class="percent">Зі світлом {{ kyiv_status.percent_on }}% черг</span><br>
        Зі світлом: {{ kyiv_status.groups_on | length }} черг ·
        без світла: {{ kyiv_status.groups_off | length }} черг
    </aside>
    {% elif show_kyiv_status %}
    <aside class="summary">Дані про графік черг Києва тимчасово недоступні.</aside>
    {% endif %}
    <div class="map-container">{{ map_html | safe }}</div>
</body>
</html>
"""

POWER_PLACE_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>{{ place.name_uk or place.name_en or "Черги" }} — Світло</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; min-height: 100vh; background: #080b10; color: #f4f7fb; font-family: Arial, sans-serif; }
        header { padding: 20px 24px; background: #0c131b; border-bottom: 1px solid #263746; }
        a { color: #8ec8ea; text-decoration: none; font-weight: 700; }
        main { max-width: 980px; margin: 0 auto; padding: 28px 20px 48px; }
        h1 { margin: 22px 0 8px; }
        .summary { color: #aebdca; margin: 0 0 22px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
        .queue { padding: 14px; border: 1px solid #35424d; border-radius: 12px; background: #131c25; }
        .queue strong { display: block; font-size: 17px; margin-bottom: 6px; }
        .queue span { font-size: 13px; }
        .queue small { display: block; margin-top: 8px; color: #aebdca; }
        .off { border-color: #a94949; }
        .off span { color: #ff8888; }
        .on span { color: #84d79c; }
        .maybe span { color: #ffd16f; }
        .unknown span { color: #aebdca; }
        .empty, .error { padding: 18px; border: 1px solid #35424d; border-radius: 12px; color: #c2ccd5; }
        @media (max-width: 560px) { header { padding: 16px; } main { padding: 20px 14px; } }
    </style>
</head>
<body>
    <header><a href="/power">← Повернутися до карти світла</a></header>
    <main>
        {% if error %}
        <section class="error">{{ error }}</section>
        {% else %}
        <h1>{{ place.name_uk or place.name_en or "Населений пункт" }}</h1>
        <p class="summary">
            {% if place.stale %}Дані застаріли{% elif place.groups %}
                Зараз без світла {{ place.groups_off or 0 }} із {{ place.groups }} черг
            {% else %}Немає актуальних даних про черги{% endif %}
        </p>
        {% if groups %}
        <section class="grid" aria-label="Статус черг">
            {% for group in groups %}
            <article class="queue {{ group.css }}">
                <strong>Черга {{ group.name }}</strong>
                <span>{{ group.label }}</span>
                {% if group.detail %}<small>{{ group.detail }}</small>{% endif %}
            </article>
            {% endfor %}
        </section>
        {% else %}
        <section class="empty">Для цього населеного пункту джерело не повертає список окремих черг.</section>
        {% endif %}
        {% endif %}
    </main>
</body>
</html>
"""

# CSS, який потрапляє всередину самої карти (в iframe folium)
MAP_DARK_CSS = """
<style>
    html, body {
        background: #000000 !important;
        margin: 0;
        padding: 0;
    }
    .folium-map,
    .leaflet-container {
        background: #000000 !important;
    }
    .leaflet-tile-pane {
        filter: grayscale(1) invert(1) brightness(0.82) contrast(0.92);
    }
    .leaflet-control-attribution {
        background: rgba(0, 0, 0, 0.78) !important;
        color: #dddddd !important;
    }
    .leaflet-control-attribution a {
        color: #b9d8ef !important;
    }
</style>
"""


def create_ukraine_map(with_streets=False):
    ukraine_map = folium.Map(
        location=[48.5, 31.2],
        zoom_start=5,
        tiles="OpenStreetMap" if with_streets else None,
        width="100%",
        height="100%",
        min_zoom=4,
        max_zoom=19 if with_streets else 7,
        scrollWheelZoom=with_streets,
        control_scale=with_streets,
    )
    ukraine_map.get_root().header.add_child(folium.Element(MAP_DARK_CSS))
    return ukraine_map


def render_map_page(map_object, title, subtitle, kyiv_status=None, show_kyiv_status=False):
    return render_template_string(
        MAP_PAGE_TEMPLATE,
        map_html=map_object._repr_html_(),
        title=title,
        subtitle=subtitle,
        kyiv_status=kyiv_status,
        show_kyiv_status=show_kyiv_status,
    )


def format_home_time(value):
    if not value:
        return "—"

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return text

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d.%m.%Y, %H:%M")


@app.route("/")
def home():
    with ThreadPoolExecutor(max_workers=2) as executor:
        alerts_future = executor.submit(get_alerts_snapshot)
        power_future = executor.submit(get_power_source_status)
        alerts = alerts_future.result()
        power = power_future.result()

    services = get_accessibility_source_status()
    if alerts["available"]:
        alert_count = len(alerts["alerts"])
        alert_summary = (
            f"Активних областей: {alert_count}."
            if alert_count
            else "Активних тривог не показано."
        )
    else:
        alert_summary = "Не вдалося отримати поточний стан тривог."

    def prepare_card(source, summary):
        value = dict(source)
        value["summary"] = summary
        value.setdefault("status", value.get("source", "Дані недоступні"))
        value.setdefault("status_class", "offline")
        value["updated_at"] = format_home_time(value.get("updated_at"))
        return value

    services_status = prepare_card(services, services["summary"])
    alerts_status = prepare_card(alerts, alert_summary)
    power_status = prepare_card(power, power["summary"])

    return render_template_string(
        HOME_TEMPLATE,
        services_status=services_status,
        alerts_status=alerts_status,
        power_status=power_status,
    )


@app.route("/services")
def services_map():
    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()
    geojson_data = response.json()
    features = geojson_data.get("features", [])
    if not features:
        raise ValueError("GeoJSON не містить областей!")

    ukraine_map = create_ukraine_map(with_streets=True)
    region_layer = folium.GeoJson(
        geojson_data,
        name="Області України",
        style_function=lambda feature: {
            "fillColor": DEFAULT_REGION_COLOR,
            "color": "#111111",
            "weight": 2,
            "fillOpacity": 0.18,
        },
        highlight_function=lambda feature: {
            "fillColor": DEFAULT_REGION_COLOR,
            "color": "#ffffff",
            "weight": 3,
            "fillOpacity": 0.3,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=["Область:"],
        ),
    )
    region_layer.add_to(ukraine_map)
    add_accessibility_layer(ukraine_map)
    folium.LayerControl(collapsed=False).add_to(ukraine_map)
    ukraine_map.fit_bounds(region_layer.get_bounds(), padding=(40, 40), max_zoom=6)
    ukraine_map.options["maxZoom"] = 19

    return render_map_page(
        ukraine_map,
        "Сервіс · Безбар'єрність",
        "Об'єкти доступності з локального набору даних.",
    )


@app.route("/alerts")
def alerts_map():
    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()

    geojson_data = response.json()
    features = geojson_data.get("features", [])

    if not features:
        raise ValueError("GeoJSON не містить областей!")

    print("Успішно завантажено областей:", len(features))

    try:
        alert_data = get_alerts_data()
    except Exception as error:
        print("Не вдалося отримати дані тривог:", error)
        alert_data = {}

    alert_by_region = {
        canonical_region_name(region): alert_color(status)
        for region, status in alert_data.items()
    }

    ukraine_map = create_ukraine_map()

    def region_color(feature):
        name = feature.get("properties", {}).get("name", "")
        return alert_by_region.get(
            canonical_region_name(name),
            DEFAULT_REGION_COLOR,
        )

    def style_function(feature):
        return {
            "fillColor": region_color(feature),
            "color": "#111111",
            "weight": 2,
            "fillOpacity": 0.9,
        }

    def highlight_function(feature):
        return {
            "fillColor": region_color(feature),
            "color": "#ffffff",
            "weight": 3,
            "fillOpacity": 0.95,
        }

    geojson_layer = folium.GeoJson(
        geojson_data,
        name="Області України",
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=["Область:"],
        ),
    )
    geojson_layer.add_to(ukraine_map)

    bounds = geojson_layer.get_bounds()
    print("Межі карти:", bounds)

    ukraine_map.fit_bounds(bounds, padding=(40, 40), max_zoom=6)

    return render_map_page(
        ukraine_map,
        "Тривоги",
        "Поточний статус тривог по областях України.",
    )


@app.route("/power")
def power_map():
    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()
    geojson_data = response.json()

    if not geojson_data.get("features"):
        raise ValueError("GeoJSON не містить областей!")

    ukraine_map = create_ukraine_map(with_streets=True)
    add_outages_layer(ukraine_map, geojson_data)
    folium.LayerControl(collapsed=False).add_to(ukraine_map)

    try:
        kyiv_status = get_kyiv_queue_status()
    except Exception as error:
        print("Не вдалося отримати графік черг Києва:", error)
        kyiv_status = None

    return render_map_page(
        ukraine_map,
        "Світло",
        "Статус у містах і населених пунктах. Натисніть точку, щоб побачити черги.",
        kyiv_status=kyiv_status,
        show_kyiv_status=True,
    )


@app.route("/power/place/<slug>")
def power_place_detail(slug):
    try:
        data = get_place_details(slug)
    except requests.RequestException as error:
        print("Не вдалося отримати черги населеного пункту:", error)
        return render_template_string(
            POWER_PLACE_TEMPLATE,
            place={},
            groups=[],
            error="Не вдалося завантажити статус черг. Спробуйте ще раз пізніше.",
        ), 503

    place = data.get("place") or {}
    status_labels = {
        "on": ("Світло є", "on"),
        "off": ("Без світла", "off"),
        "maybe": ("Можливе відключення", "maybe"),
        "unknown": ("Немає даних", "unknown"),
    }
    groups = []

    for item in data.get("groups", []):
        if not isinstance(item, dict):
            continue

        state = str(item.get("state", "unknown"))
        label, css_class = status_labels.get(
            state,
            ("Немає даних", "unknown"),
        )
        restore_at = item.get("restore_at")
        next_at = item.get("next_at")
        next_state = item.get("next_state")

        if restore_at:
            time_text = str(restore_at).split("T")[-1][:5]
            detail = f"Відновлення за графіком о {time_text}"
        elif next_at:
            time_text = str(next_at).split("T")[-1][:5]
            next_label = "відключення" if next_state == "off" else "зміна статусу"
            detail = f"Наступне {next_label} о {time_text}"
        else:
            detail = ""

        groups.append({
            "name": item.get("group") or item.get("key", "—"),
            "label": label,
            "css": css_class,
            "detail": detail,
        })

    groups.sort(key=lambda group: str(group["name"]))

    return render_template_string(
        POWER_PLACE_TEMPLATE,
        place=place,
        groups=groups,
        error=None,
    )


if __name__ == "__main__":
    app.run(debug=True)
