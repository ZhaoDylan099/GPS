from pyrosm import OSM
from pathlib import Path
from sqlalchemy import create_engine
from geoalchemy2 import Geometry
import geopandas as gpd
import pandas as pd

directory = Path("./cache")

engine = create_engine("")

ROAD_RANK = {
    # Highways
    "motorway": 1,
    "motorway_link": 1,

    # Major roads
    "trunk": 2,
    "trunk_link": 2,

    # Arterials
    "primary": 3,
    "primary_link": 3,

    "secondary": 4,
    "secondary_link": 4,

    "tertiary": 5,
    "tertiary_link": 5,

    # Local roads
    "residential": 6,
    "living_street": 6,
    "residential_link": 6,

    # Service/local access
    "service": 7,
    "services": 7,
    "unclassified": 7,
    "rest_area": 7,

    # Low-priority roads
    "track": 8,
    "road": 8,
    "busway": 8,

    # Usually not routable
    "bus_stop": 99,
    "traffic_island": 99,
    "crossing": 99,
    "disused": 99
}

DEFAULT_SPEEDS = {
    # Interstate / freeway
    "motorway": 70,
    "motorway_link": 45,

    # Major highways
    "trunk": 60,
    "trunk_link": 40,

    # Major arterials
    "primary": 50,
    "primary_link": 35,

    # Secondary arterials
    "secondary": 45,
    "secondary_link": 30,

    # Local arterials
    "tertiary": 35,
    "tertiary_link": 25,

    # Residential roads
    "residential": 25,
    "residential_link": 25,
    "living_street": 15,

    # Service roads
    "service": 15,
    "services": 15,
    "rest_area": 15,

    # Misc local roads
    "unclassified": 25,
    "road": 25,

    # Low-quality / unpaved
    "track": 10,

    # Transit-related
    "busway": 20,

    # Non-routable (should probably be filtered out)
    "bus_stop": 0,
    "traffic_island": 0,
    "crossing": 0,
    "disused": 0
}

duplicates = set()

STATES = [
    "ohio",
    "pennsylvania"
]

NODES_COLUMNS = ["node_id", "lat", "lon", "geom", "state"]

EDGES_COLUMNS = ["osm_way_id", "source", "target", "road_name", "length_m", "speed_limit", 
                 "travel_time", "oneway", "road_rank", "road_type", "geom", "state"]

i = 0
for path in directory.glob("*.osm.pbf"):
    print(f"Processing {path.name}")
    osm = OSM(path)
    nodes, edges = osm.get_network(
        network_type="driving",
        nodes=True
    )
    nodes.rename(
        columns={
            "id": "node_id",
            "geometry": "geom"
            }, 
        inplace=True
    )

    
    edges["maxspeed"] = edges["maxspeed"].str.replace(" mph", "")
    edges["maxspeed"] = pd.to_numeric(edges["maxspeed"], errors="coerce")

    edges["maxspeed"] = (
        edges["maxspeed"]
        .fillna(edges["highway"].map(DEFAULT_SPEEDS))
    )

    edges["travel_time"] = (
        edges["length"] /
        (edges["maxspeed"] * 0.44704)
    )

    edges["road_rank"] = edges["highway"].map(ROAD_RANK)
    edges["road_rank"] = edges["road_rank"].fillna(99)

    edges["road_rank"] = edges["road_rank"].astype('Int64')


    nodes["state"] = STATES[i]
    edges["state"] = STATES[i]

    edges.rename(
        columns={
            "u": "source", 
            "v": "target",
            "id": "osm_way_id",
            "name": "road_name",
            "length": "length_m",
            "maxspeed": "speed_limit",
            "highway": "road_type",
            "geometry": "geom"
            }, inplace=True)

    nodes = nodes[~nodes["node_id"].isin(duplicates)]
    print(f"Sending to DB {path.name}")


    nodes = gpd.GeoDataFrame(nodes, geometry="geom", crs="EPSG:4326")
    edges = gpd.GeoDataFrame(edges, geometry="geom", crs="EPSG:4326")

    nodes[NODES_COLUMNS].to_postgis("nodes", engine, if_exists="append", index=False)
    edges[EDGES_COLUMNS].to_postgis("edges", engine, if_exists="append", index=False)

    duplicates.update(nodes["node_id"].tolist())
    print(f"Finished processing {path.name}")
    i += 1
