import os

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine

from TileRouter import TileRouter
from search import search_location
from GraphTileCache import GraphTileCache

app = FastAPI()

# In Docker, "localhost" would point at the app container itself, not the DB
# container — so this reads from DATABASE_URL (set in docker-compose.yml to
# point at the "db" service) and only falls back to localhost for running
# main.py directly on your machine outside of Docker.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
engine = create_engine(DATABASE_URL)

# Shared cache instance so tiles loaded by one request stay warm for later requests.
cache = GraphTileCache(engine)


class TileCoordinateRequest(BaseModel):
    latitude: float
    longitude: float
    zoom: int  # Accept values generally ranging from 0 (world) to 18 (street view)


class RouteRequest(BaseModel):
    start_address: str
    goal_address: str


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/tiles")
def preload_tile(request: TileCoordinateRequest):
    cache.load_tile_for_coordinate(request.latitude, request.longitude, zoom=request.zoom)
    return {
        "tiles_loaded": len(cache.loaded_tiles),
        "nodes_cached": len(cache.coords),
    }


@app.get("/search")
def search(address: str):
    node_id, lat, lon = search_location(address, engine)
    if lat is None or lon is None:
        return {"error": "Location not found"}
    return {"node_id": node_id, "latitude": lat, "longitude": lon}


@app.post("/route")
def route(request: RouteRequest):
    start_node, start_lat, start_lon = search_location(request.start_address, engine)
    if start_lat is None or start_lon is None:
        return {"error": f"Start location not found: {request.start_address}"}

    goal_node, goal_lat, goal_lon = search_location(request.goal_address, engine)
    if goal_lat is None or goal_lon is None:
        return {"error": f"Goal location not found: {request.goal_address}"}

    start = {"node_id": start_node, "latitude": start_lat, "longitude": start_lon}
    goal = {"node_id": goal_node, "latitude": goal_lat, "longitude": goal_lon}

    router = TileRouter(cache, engine)
    result = router.find_shortest_path(start_address=start, goal_address=goal)
    if result is None:
        return {"error": "Route not found"}
    path, total_time, total_distance = result
    return {
        "path": path,
        "total_time": total_time,
        "total_distance": total_distance
    }