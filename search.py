import pandas as pd
from sqlalchemy import text
from geopy.geocoders import Nominatim


def _fetch_nearest_node_id(lat, lon, sql_engine):
    query = text("""
        SELECT node_id, lat, lon
        FROM nodes
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
        LIMIT 1;
    """)
    result = pd.read_sql(query, con=sql_engine, params={"lon": lon, "lat": lat})
    if not result.empty:
        return result.iloc[0]['node_id'].item(), result.iloc[0]['lat'].item(), result.iloc[0]['lon'].item()
    return None, None, None


def search_location(address, engine):
    geolocator = Nominatim(user_agent="tiled_router")
    location = geolocator.geocode(address)
    if location:
        return _fetch_nearest_node_id(location.latitude, location.longitude, engine)
    return None, None, None
