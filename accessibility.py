import json
import folium
from pathlib import Path


# Шлях до локального GeoJSON
DATA_FILE = (
    Path(__file__).parent
    / "data"
    / "establishments.geojson"
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

    # Знаходимо перший об'єкт з атрибутами
    properties = next(
        (
            feature.get("properties", {})
            for feature in features
            if feature.get("properties")
        ),
        {}
    )

    # Вибираємо поля, які можна показати
    fields = [
        key
        for key, value in properties.items()
        if value is not None
        and isinstance(value, (str, int, float, bool))
    ][:8]

    layer = folium.FeatureGroup(
        name="Безбар'єрність",
        show=False
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

    # Додаємо підказки лише за наявності атрибутів
    if fields:
        geojson_options["tooltip"] = folium.GeoJsonTooltip(
            fields=fields,
            aliases=fields,
            sticky=True
        )

        geojson_options["popup"] = folium.GeoJsonPopup(
            fields=fields,
            aliases=fields,
            localize=True
        )

    folium.GeoJson(**geojson_options).add_to(layer)

    layer.add_to(map_object)

    print(
        "Успішно додано об'єктів безбар'єрності:",
        len(features)
    )

    return map_object
