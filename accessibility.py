import json
import folium
from pathlib import Path


# Шлях до локального GeoJSON
DATA_FILE = (
    Path(__file__).parent
    / "data"
    / "establishments.geojson"
)

DISPLAY_FIELDS = {
    "title": "Назва",
    "kind": "Тип об'єкта",
    "addressAdminUnitL1": "Область",
    "addressAdminUnitL2": "Район",
    "addressPostName": "Населений пункт",
    "addressThoroughfare": "Адреса",
    "rating": "Оцінка",
    "updateDate": "Оновлено",
    "url": "Джерело",
}

TOOLTIP_FIELDS = (
    "title",
    "kind",
    "addressPostName",
    "addressThoroughfare",
)


def get_accessibility_data():
    """Завантажує локальний GeoJSON безбар'єрності."""

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if data.get("type") != "FeatureCollection":
            raise ValueError("Файл не є GeoJSON FeatureCollection")

        if "features" not in data:
            raise ValueError("У GeoJSON відсутнє поле features")

        # The source file includes large nested category details. Keep only
        # fields used in map popups to avoid embedding that data in the page.
        for feature in data["features"]:
            properties = feature.get("properties") or {}
            feature["properties"] = {
                key: properties.get(key, "")
                for key in DISPLAY_FIELDS
            }

        print(
            "Отримано об'єктів безбар'єрності:",
            len(data["features"])
        )

        return data

    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Помилка завантаження безбар'єрності: {error}")
        return None


def add_accessibility_layer(map_object):
    """Додає об'єкти безбар'єрності на карту."""

    data = get_accessibility_data()

    if data is None:
        return map_object

    features = data.get("features", [])

    if not features:
        print("Об'єктів безбар'єрності не знайдено")
        return map_object

    layer = folium.FeatureGroup(
        name="Безбар'єрність",
        show=True
    )

    geojson_options = {
        "data": data,
        "name": "Об'єкти безбар'єрності",

        # Маркери для точкових об'єктів
        "marker": folium.CircleMarker(
            radius=5,
            color="#00c853",
            fill=True,
            fill_color="#00c853",
            fill_opacity=0.85,
            weight=1
        ),

        # Стиль для ліній та полігонів
        "style_function": lambda feature: {
            "color": "#00c853",
            "weight": 2,
            "fillColor": "#00c853",
            "fillOpacity": 0.35
        }
    }

    geojson_options["tooltip"] = folium.GeoJsonTooltip(
        fields=TOOLTIP_FIELDS,
        aliases=[DISPLAY_FIELDS[field] for field in TOOLTIP_FIELDS],
        sticky=True,
    )
    geojson_options["popup"] = folium.GeoJsonPopup(
        fields=list(DISPLAY_FIELDS),
        aliases=list(DISPLAY_FIELDS.values()),
        localize=True,
    )

    geojson_layer = folium.GeoJson(**geojson_options)
    geojson_layer.add_to(layer)

    layer.add_to(map_object)

    bounds = geojson_layer.get_bounds()
    if bounds and bounds[0] and bounds[1]:
        map_object.fit_bounds(bounds, padding=(24, 24), max_zoom=15)

    print(
        "Успішно додано об'єктів безбар'єрності:",
        len(features)
    )

    return map_object
