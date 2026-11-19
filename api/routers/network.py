"""Network endpoints: the static geography of the grid, for the map.

`/api/network/geo` returns one GeoJSON FeatureCollection with:
- a Point feature per substation (from `api.v_substations`), and
- a LineString feature per element (from `api.v_elements`; the route comes from the GIS
  circuits when matched, otherwise a straight line between the two substations).

Static attributes only (ratings, length, age). Results that change by month, such as
loading and losses, come from `/api/losses/map` and friends and are joined in the
browser on `element_id`. The collection carries a top-level `provenance` member.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from fastapi import APIRouter

from api import provenance, render
from api.tables import Col, TableSpec, register

router = APIRouter(prefix="/api/network", tags=["network"])

SUBSTATION_PROPS = ["ss_code", "name", "kv_levels", "district", "in_central"]
ELEMENT_PROPS = [
    "element_type", "element_id", "name", "ss_from", "ss_to", "kv", "length_km",
    "in_central", "rate_mva", "commissioning_year", "age_years", "status",
]

register(TableSpec(
    name="substations",
    title="Substations",
    view="api.v_substations",
    columns=[
        Col("ss_code", "Code"),
        Col("name", "Substation"),
        Col("kv_levels", "Voltage levels", "kV"),
        Col("district", "District"),
        Col("in_central", "In Central"),
        Col("lat", "Latitude", "°", 5),
        Col("lon", "Longitude", "°", 5),
    ],
    filters={"ss_code": "ss_code", "in_central": "in_central"},
    order_by="ss_code",
))

register(TableSpec(
    name="elements",
    title="Network elements",
    view="api.v_elements",
    columns=[
        Col("element_type", "Type"),
        Col("element_id", "Element"),
        Col("name", "Name"),
        Col("ss_from", "From"),
        Col("ss_to", "To"),
        Col("kv", "Voltage", "kV", 0),
        Col("length_km", "Length", "km", 1),
        Col("rate_mva", "Rating", "MVA", 0),
        Col("commissioning_year", "Commissioned"),
        Col("age_years", "Age", "years", 0),
        Col("in_central", "In Central"),
        Col("status", "Status"),
    ],
    filters={"element_type": "element_type", "kv": "kv", "ss": "ss_from", "status": "status"},
    order_by="element_type, element_id",
))

render.table_route(router, "/substations", "substations", "Substations (table)")
render.table_route(router, "/elements", "elements", "Network elements with static attributes (table)")


def parse_geometry(value: Any) -> dict[str, Any] | None:
    """The view's `geojson` column as a geometry dict: it may arrive as text or as JSON."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, dict) and "type" in value:
        return value
    return None


def point(lon: Any, lat: Any) -> dict[str, Any] | None:
    """A GeoJSON Point, or None when a coordinate is missing."""
    lon, lat = render.plain(lon), render.plain(lat)
    if not render.is_number(lon) or not render.is_number(lat):
        return None
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}


def substation_features(df: pd.DataFrame) -> list[dict[str, Any]]:
    """One Point feature per substation; id is the ss_code."""
    features = []
    for rec in df.to_dict(orient="records"):
        props = {"kind": "substation", **{k: render.plain(rec.get(k)) for k in SUBSTATION_PROPS}}
        features.append({
            "type": "Feature",
            "id": props["ss_code"],
            "geometry": point(rec.get("lon"), rec.get("lat")),
            "properties": props,
        })
    return features


def element_features(df: pd.DataFrame) -> list[dict[str, Any]]:
    """One feature per element; id is the element_id. Geometry may be null (no route known)."""
    decimals = {"length_km": 2, "rate_mva": 1, "kv": 1, "age_years": 0}
    features = []
    for rec in df.to_dict(orient="records"):
        props = {"kind": "element"}
        for key in ELEMENT_PROPS:
            props[key] = render.round_value(render.plain(rec.get(key)), decimals.get(key))
        features.append({
            "type": "Feature",
            "id": props["element_id"],
            "geometry": parse_geometry(rec.get("geojson")),
            "properties": props,
        })
    return features


@router.get("/geo", summary="Substations and elements as GeoJSON")
def network_geo() -> dict[str, Any]:
    """A FeatureCollection of substations (Point) and elements (LineString), with provenance.

    Element properties: element_type, element_id, name, ss_from, ss_to, kv [kV],
    length_km [km], in_central, rate_mva [MVA], commissioning_year, age_years [years], status.
    Substation properties: ss_code, name, kv_levels [kV], district, in_central.
    Every feature has `kind` = 'substation' or 'element'.
    """
    subs = render.query_view(
        "SELECT ss_code, name, kv_levels, district, in_central, lon, lat "
        "FROM api.v_substations ORDER BY ss_code",
        {}, "network geo", "api.v_substations",
    )
    elems = render.query_view(
        "SELECT element_type, element_id, name, ss_from, ss_to, kv, length_km, in_central, "
        "rate_mva, commissioning_year, age_years, status, geojson "
        "FROM api.v_elements ORDER BY element_type, element_id",
        {}, "network geo", "api.v_elements",
    )
    return {
        "type": "FeatureCollection",
        "provenance": provenance.current(),
        "features": substation_features(subs) + element_features(elems),
    }
