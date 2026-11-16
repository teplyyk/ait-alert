
from flask import Flask, render_template_string
import folium
import requests

app = Flask(__name__)

# Джерело даних: 136 районів та області
BASE = "https://raw.githubusercontent.com/Astaryon/UA_geojson/main/"
RAIONS_URL = BASE + "rayony.geojson"
OBLASTS_URL = BASE + "regiony.geojson"

# Запасне джерело для пошуку Києва
FALLBACK_URL = (
    "https://raw.githubusercontent.com/"
    "darmat1/ukraine-geo-data/main/geodata/Ukraine.geojson"
)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>Карта України</title>

    <style>
        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background: #000000 !important;
            color-scheme: dark;
            font-family: Arial, sans-serif;
        }

        .map-container {
            width: 100%;
            height: 100vh;
            background: #000000;
            overflow: hidden;
        }

        .map-container iframe {
            width: 100%;
            height: 100%;
            border: none;
            display: block;
            background: #000000;
            color-scheme: dark;
        }
    </style>
</head>

<body>
    <div class="map-container">
        {{ map_html | safe }}
    </div>
</body>
</html>
"""

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

    .leaflet-tooltip {
        background: #111;
        color: #fff;
        border: 1px solid #444;
        font-family: Arial, sans-serif;
        font-size: 13px;
    }
</style>
"""

# Можливі назви поля з назвою об'єкта
NAME_KEYS = [
    "name", "NAME", "Name", "name_uk", "name_ua",
    "NAME_UA", "name_uа", "ADM2_UA", "ADM2_EN",
    "ADM1_UA", "ADM1_EN", "shapeName", "rayon",
    "raion", "district", "region", "NAME_2", "NAME_1",
]

KYIV_NAMES = {
    "київ", "м. київ", "м.київ", "місто київ",
    "kyiv", "kiev", "kyiv city", "kiev city",
    "city of kyiv", "city of kiev",
}

_cache = {}


def load(url):
    """Завантажує GeoJSON і кешує його в пам'яті."""
    if url not in _cache:
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        _cache[url] = response.json()

    return _cache[url]


def pick_name(props, fallback):
    """Підбирає назву об'єкта з відомих полів."""
    for key in NAME_KEYS:
        value = props.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    for value in props.values():
        if isinstance(value, str) and value.strip():
            return value.strip()

    return fallback


def add_labels(data, prefix):
    for i, feature in enumerate(data.get("features", [])):
        props = feature.setdefault("properties", {})
        props["label"] = pick_name(
            props,
            f"{prefix} {i + 1}"
        )

    return data


def bbox_area(feature):
    xs, ys = [], []

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for c in coords:
                walk(c)

    walk(feature["geometry"]["coordinates"])

    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def find_kyiv_city(*datasets):
    """Шукає саме місто Київ, а не Київську область."""
    for data in datasets:
        matches = []

        for feature in data.get("features", []):
            values = [
                v.strip().lower()
                for v in feature.get("properties", {}).values()
                if isinstance(v, str)
            ]

            if any(v in KYIV_NAMES for v in values):
                matches.append(feature)

        if matches:
            return min(matches, key=bbox_area)

    return None


@app.route("/")
def index():

    # Завантаження районів та областей
    raions = add_labels(load(RAIONS_URL), "Район")
    oblasts = add_labels(load(OBLASTS_URL), "Область")

    if not raions.get("features"):
        raise ValueError(
            "rayony.geojson не містить районів!"
        )

    print("Районів:", len(raions["features"]))
    print("Областей:", len(oblasts.get("features", [])))
    print(
        "Поля району:",
        list(raions["features"][0]["properties"].keys())
    )

    # Пошук міста Києва
    kyiv = find_kyiv_city(raions, oblasts)

    if kyiv is None:
        try:
            fallback = add_labels(
                load(FALLBACK_URL),
                "Область"
            )
            kyiv = find_kyiv_city(fallback)

        except requests.RequestException as exc:
            print("Запасне джерело недоступне:", exc)

    if kyiv is None:
        print("УВАГА: м. Київ не знайдено!")

    # Створення карти з обмеженим масштабуванням
    ukraine_map = folium.Map(
        location=[48.5, 31.2],
        zoom_start=6,
        tiles=None,
        width="100%",
        height="100%",
        min_zoom=6,
        max_zoom=10,
        scrollWheelZoom=True,
        control_scale=False,
        zoomSnap=0.5,
    )

    ukraine_map.get_root().header.add_child(
        folium.Element(MAP_DARK_CSS)
    )

    # 1. Райони
    folium.GeoJson(
        raions,
        name="Райони",
        style_function=lambda f: {
            "fillColor": "#1b3a5c",
            "color": "#5d86b3",
            "weight": 0.8,
            "fillOpacity": 0.9,
        },
        highlight_function=lambda f: {
            "fillColor": "#ffff00",
            "color": "#ffffff",
            "weight": 2,
            "fillOpacity": 1,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["label"],
            aliases=["Район:"]
        ),
    ).add_to(ukraine_map)

    # 2. Місто Київ окремим шаром
    if kyiv is not None:
        kyiv = dict(kyiv)
        kyiv["properties"] = dict(
            kyiv.get("properties", {}),
            label="м. Київ"
        )

        folium.GeoJson(
            {
                "type": "FeatureCollection",
                "features": [kyiv]
            },
            name="м. Київ",
            style_function=lambda f: {
                "fillColor": "#2a6f97",
                "color": "#ffffff",
                "weight": 1.5,
                "fillOpacity": 1,
            },
            highlight_function=lambda f: {
                "fillColor": "#ffff00",
                "color": "#ffffff",
                "weight": 2.5,
                "fillOpacity": 1,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["label"],
                aliases=["Місто:"]
            ),
        ).add_to(ukraine_map)

    # 3. Контури областей
    oblast_layer = folium.GeoJson(
        oblasts,
        name="Області",
        style_function=lambda f: {
            "fill": False,
            "color": "#ffffff",
            "weight": 2,
        },
        interactive=False,
    )

    oblast_layer.add_to(ukraine_map)

    # Початкове розташування карти
    ukraine_map.fit_bounds(
        oblast_layer.get_bounds(),
        padding=(40, 40),
        max_zoom=6
    )

    # Обмеження масштабування
    ukraine_map.options["minZoom"] = 6
    ukraine_map.options["maxZoom"] = 10
    ukraine_map.options["scrollWheelZoom"] = True
    ukraine_map.options["zoomSnap"] = 0.5

    map_html = ukraine_map._repr_html_()

    return render_template_string(
        HTML_TEMPLATE,
        map_html=map_html
    )


if __name__ == "__main__":
    app.run(debug=True)
