"""Settlement and queue-level electricity status maps."""

import html
from urllib.parse import quote

import folium
import requests


API_BASE = "https://svitlopulse.andrewboyko.name/api/v1"
PLACES_URL = f"{API_BASE}/places?limit=1000"

STATUS_COLORS = {
    "on": "#2ecc71",
    "mostly_on": "#a3d65c",
    "even": "#f6bf26",
    "mostly_off": "#f08c32",
    "off": "#ef4444",
    "partial": "#f39c12",
    "emergency": "#8e0000",
    "unknown": "#808080",
}

STATUS_LABELS = {
    "on": "Світло є в усіх чергах",
    "mostly_on": "У більшості черг світло є",
    "even": "Черги зі світлом і без — порівну",
    "mostly_off": "У більшості черг немає світла",
    "off": "Немає світла в жодній черзі",
    "partial": "Частково, частки черг не вказані",
    "emergency": "Аварійні обмеження",
    "unknown": "Немає актуальних даних",
}

STATUS_NAMES = {
    "on": "Світло у всіх чергах",
    "mostly_on": "Більшість черг зі світлом",
    "even": "Порівну зі світлом і без",
    "mostly_off": "Більшість черг без світла",
    "off": "Черги всі без світла",
    "partial": "Частково, без розподілу",
    "unknown": "Немає свіжих даних",
}


def get_outages():
    """Return available settlement points, not oblast-wide summaries."""
    try:
        response = requests.get(PLACES_URL, timeout=20)
        response.raise_for_status()
        data = response.json()
        places = data.get("places", [])
        if not isinstance(places, list):
            raise ValueError("API не повернув список населених пунктів")
        return places
    except (requests.RequestException, ValueError) as error:
        print(f"Помилка API населених пунктів: {error}")
        return []


def get_place_details(slug):
    """Return the queue details for one settlement."""
    safe_slug = quote(str(slug), safe="")
    response = requests.get(f"{API_BASE}/places/{safe_slug}", timeout=15)
    response.raise_for_status()
    return response.json()


def get_place_status(place):
    """Classify a settlement by how many outage queues are currently off."""
    if bool(place.get("stale", True)):
        return "unknown"

    try:
        total_groups = int(place.get("groups") or 0)
        groups_off = int(place.get("groups_off") or 0)
    except (TypeError, ValueError):
        total_groups = groups_off = 0

    if total_groups > 0:
        if groups_off <= 0:
            return "on"
        if groups_off >= total_groups:
            return "off"
        if groups_off * 2 < total_groups:
            return "mostly_on"
        if groups_off * 2 > total_groups:
            return "mostly_off"
        return "even"

    state = str(place.get("state", "unknown"))
    if state == "on":
        return "on"
    if state in {"off", "emergency"}:
        return "off"
    if state in {"partial", "maybe"}:
        return "partial"
    return "unknown"


def add_outages_layer(map_object, geojson_data):
    """Draw subdued oblast outlines and clearly classified settlement markers."""
    region_layer = folium.GeoJson(
        geojson_data,
        name="Межі областей",
        style_function=lambda feature: {
            "fillColor": "#101820",
            "color": "#58636d",
            "weight": 1.5,
            "fillOpacity": 0.12,
        },
        highlight_function=lambda feature: {
            "fillColor": "#101820",
            "color": "#ffffff",
            "weight": 2,
            "fillOpacity": 0.18,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=["Область:"],
        ),
    )
    region_layer.add_to(map_object)

    places = get_outages()
    status_order = (
        "on", "mostly_on", "even", "mostly_off", "off", "partial", "unknown"
    )
    place_layers = {
        status: folium.FeatureGroup(
            name=f"{STATUS_NAMES[status]} · 0",
            show=True,
        )
        for status in status_order
    }
    counts = {status: 0 for status in status_order}

    for place in places:
        if not isinstance(place, dict):
            continue

        try:
            latitude = float(place["lat"])
            longitude = float(place["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        state = get_place_status(place)
        color = STATUS_COLORS[state]
        status_label = STATUS_LABELS[state]
        place_name = str(
            place.get("name_uk") or place.get("name_en") or place.get("slug") or "Населений пункт"
        )
        escaped_name = html.escape(place_name)
        try:
            groups = int(place.get("groups") or 0)
            groups_off = int(place.get("groups_off") or 0)
        except (TypeError, ValueError):
            groups = groups_off = 0
        off_share = place.get("off_share")

        try:
            off_share_value = (
                groups_off / groups
                if groups > 0
                else float(off_share or 0)
            )
        except (TypeError, ValueError):
            off_share_value = 0
        off_share_value = min(max(off_share_value, 0), 1)

        if groups:
            groups_on = max(groups - groups_off, 0)
            queue_text = (
                f"Зі світлом: {groups_on} із {groups} черг. "
                f"Без світла: {groups_off} із {groups} "
                f"({off_share_value * 100:.0f}%)."
            )
        else:
            queue_text = "Дані про черги відсутні"

        slug = place.get("slug")
        detail_link = ""
        if slug:
            href = f"/power/place/{quote(str(slug), safe='')}"
            detail_link = (
                f'<p><a href="{href}" target="_top">'
                "Показати окремі черги →</a></p>"
            )

        popup_html = (
            f"<strong>{escaped_name}</strong>"
            f"<div>{html.escape(status_label)}</div>"
            f"<div>{html.escape(queue_text)}</div>"
            f"{detail_link}"
        )
        tooltip_text = f"{place_name} · {status_label}"
        if groups:
            tooltip_text += (
                f" · без світла {groups_off}/{groups} черг "
                f"({off_share_value * 100:.0f}%)"
            )

        marker = folium.CircleMarker(
            location=[latitude, longitude],
            radius=6 + off_share_value * 4,
            color=color,
            weight=2.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=folium.Tooltip(html.escape(tooltip_text), sticky=True),
            popup=folium.Popup(popup_html, max_width=320),
        )
        marker.add_to(place_layers[state])
        counts[state] += 1

    for status in status_order:
        place_layers[status].layer_name = (
            f"{STATUS_NAMES[status]} · {counts[status]}"
        )
        place_layers[status].add_to(map_object)

    shown = sum(counts.values())

    if shown == 0:
        no_data_message = """
        <div style="position:fixed;top:86px;left:50%;transform:translateX(-50%);
                    z-index:9999;padding:12px 16px;border:1px solid #704b32;
                    border-radius:10px;background:rgba(30,22,16,.96);color:#ffe0b5;
                    font:14px Arial,sans-serif;max-width:90vw;text-align:center">
          Дані про відключення населених пунктів тимчасово недоступні.
        </div>
        """
        map_object.get_root().html.add_child(folium.Element(no_data_message))

    legend = f"""
    <div style="position:fixed;bottom:24px;left:16px;z-index:9999;
                padding:13px 16px;border:1px solid #344858;border-radius:10px;
                background:rgba(12,19,27,.96);color:#eaf1f7;
                font:13px Arial,sans-serif;line-height:1.85;min-width:225px">
      <strong>Статус світла · {shown} населених пунктів</strong>
      <div><span style="color:#2ecc71">●</span> У всіх чергах є: <b>{counts['on']}</b></div>
      <div><span style="color:#a3d65c">●</span> Більшість черг зі світлом: <b>{counts['mostly_on']}</b></div>
      <div><span style="color:#f6bf26">●</span> Порівну черг: <b>{counts['even']}</b></div>
      <div><span style="color:#f08c32">●</span> Більшість черг без світла: <b>{counts['mostly_off']}</b></div>
      <div><span style="color:#ef4444">●</span> Усі черги без світла: <b>{counts['off']}</b></div>
      <div><span style="color:#f39c12">●</span> Є відключення, частка невідома: <b>{counts['partial']}</b></div>
      <div><span style="color:#808080">●</span> Немає свіжих даних: <b>{counts['unknown']}</b></div>
      <div style="margin-top:5px;color:#aebdca">Кольори показують частку черг без світла</div>
      <div style="color:#aebdca">Натисніть точку, щоб побачити черги</div>
    </div>
    """
    map_object.get_root().html.add_child(folium.Element(legend))

    bounds = region_layer.get_bounds()
    if bounds and bounds[0] and bounds[1]:
        map_object.fit_bounds(bounds, padding=(40, 40), max_zoom=6)

    print(f"Статуси населених пунктів для карти: {counts}")
    return counts
