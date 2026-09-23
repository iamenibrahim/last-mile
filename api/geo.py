from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    longitude: float
    latitude: float


def point_in_polygon(point: Point, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon; coordinates are [lon, lat]."""

    inside = False
    x, y = point.longitude, point.latitude
    if len(polygon) < 3:
        return False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            edge_x = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < edge_x:
                inside = not inside
        j = i
    return inside


def _haversine_km(a: Point, b: Point) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def distance_to_polygon_km(point: Point, polygon: list[list[float]]) -> float:
    """Approximate minimum edge distance using a local equirectangular projection."""

    if len(polygon) < 2:
        return float("inf")
    lat_scale = 111.32
    lon_scale = 111.32 * math.cos(math.radians(point.latitude))
    minimum = float("inf")
    for index in range(len(polygon) - 1):
        ax = (polygon[index][0] - point.longitude) * lon_scale
        ay = (polygon[index][1] - point.latitude) * lat_scale
        bx = (polygon[index + 1][0] - point.longitude) * lon_scale
        by = (polygon[index + 1][1] - point.latitude) * lat_scale
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        t = 0.0 if denominator == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
        minimum = min(minimum, math.hypot(ax + t * dx, ay + t * dy))
    return minimum


def classify_position(point: Point, geometry: dict | None) -> dict:
    if not geometry or geometry.get("type") != "Polygon":
        return {"status": "unknown", "distance_km": None, "explanation": "The source alert has no polygon."}
    polygon = geometry.get("coordinates", [[]])[0]
    if point_in_polygon(point, polygon):
        return {"status": "inside", "distance_km": 0.0, "explanation": "This location is inside the source warning polygon."}
    distance = distance_to_polygon_km(point, polygon)
    if distance <= 10:
        return {
            "status": "nearby",
            "distance_km": round(distance, 1),
            "explanation": f"This location is about {distance:.1f} km from the warning boundary.",
        }
    return {
        "status": "outside",
        "distance_km": round(distance, 1),
        "explanation": f"This location is about {distance:.1f} km outside the warning boundary.",
    }


_DEMO_LOCATIONS = {
    "24370": Point(-81.7607, 36.8815),
    "saltville": Point(-81.7607, 36.8815),
    "23510": Point(-76.2859, 36.8508),
    "norfolk": Point(-76.2859, 36.8508),
    "virginia beach": Point(-75.9780, 36.8529),
    "richmond": Point(-77.4360, 37.5407),
    "roanoke": Point(-79.9414, 37.2710),
}


def geocode(address: str) -> dict:
    normalized = address.lower()
    for token, point in _DEMO_LOCATIONS.items():
        if token in normalized:
            return {
                "point": point,
                "matched_address": address,
                "provider": "cached-demo",
                "precision": "locality",
            }

    query = urllib.parse.urlencode(
        {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    )
    url = f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "LastMileNavigator/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
        matches = payload["result"]["addressMatches"]
        if not matches:
            raise ValueError("No address match")
        match = matches[0]
        point = Point(float(match["coordinates"]["x"]), float(match["coordinates"]["y"]))
        return {
            "point": point,
            "matched_address": match.get("matchedAddress", address),
            "provider": "US Census Geocoder",
            "precision": "address",
        }
    except Exception:
        return {
            "point": Point(-76.2859, 36.8508),
            "matched_address": "Norfolk, Virginia (demo fallback)",
            "provider": "cached-demo",
            "precision": "locality",
        }
