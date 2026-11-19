"""Read GIS layers (GeoPackage, Shapefile, GeoJSON, KML) and reproject them to WGS 84.

Everything in the database is EPSG:4326 (contracts section 7). A layer without a CRS is
refused: guessing the CRS would put substations in the wrong place without anyone noticing.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pyogrio
import shapely

TARGET_CRS = "EPSG:4326"
VECTOR_SUFFIXES = {".gpkg", ".shp", ".geojson", ".json", ".kml", ".kmz", ".zip"}

# Geometry families a spec's geometry accepts without comment.
_FAMILY = {
    "Point": {"Point", "MultiPoint"},
    "LineString": {"LineString", "MultiLineString"},
    "Polygon": {"Polygon", "MultiPolygon"},
    "MultiPolygon": {"Polygon", "MultiPolygon"},
}


class VectorError(ValueError):
    """A layer cannot be read or has no coordinate reference system."""


def _gdal_path(path: Path) -> str:
    """Zipped shapefiles and KMZ are read through GDAL's /vsizip/ virtual file system."""
    if path.suffix.lower() in (".zip", ".kmz"):
        return f"/vsizip/{path}"
    return str(path)


def list_layers(path: Path) -> list[str]:
    """Layer names inside a file (a GeoPackage can hold several)."""
    return [str(name) for name, _ in pyogrio.list_layers(_gdal_path(Path(path)))]


def read_vector(path: Path, layer: str | None = None) -> gpd.GeoDataFrame:
    """Read one layer and return it in EPSG:4326. KML is always WGS 84 by definition."""
    path = Path(path)
    try:
        gdf = pyogrio.read_dataframe(_gdal_path(path), layer=layer)
    except Exception as exc:  # pyogrio raises several error types; report them the same way
        raise VectorError(f"cannot read {path.name}: {exc}") from exc
    if gdf.crs is None:
        if path.suffix.lower() in (".kml", ".kmz"):
            gdf = gdf.set_crs(TARGET_CRS)
        else:
            raise VectorError(f"{path.name} has no coordinate reference system: send the .prj or name the EPSG code")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


def geometry_matches(expected: str, actual: str | None) -> bool:
    """True when a feature's geometry type fits the spec's geometry."""
    if not expected or actual is None:
        return True
    return actual in _FAMILY.get(expected, {expected})


def to_ewkt(geom) -> str | None:
    """A shapely geometry as 2-D EWKT text with SRID 4326, which PostGIS reads in COPY.

    Z (height) values are dropped: KML from Google Earth and many shapefiles carry them,
    and the 2-D geometry columns refuse a 3-D geometry, which would fail the whole load.
    """
    if geom is None or geom.is_empty:
        return None
    if geom.has_z:
        geom = shapely.force_2d(geom)
    return f"SRID=4326;{geom.wkt}"
