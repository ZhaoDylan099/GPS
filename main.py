
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine
 
from TileRouter import TileRouter
from search import search_location
from GraphTileCache import GraphTileCache
 
app = FastAPI()
engine = create_engine("")
 
# Shared cache instance so tiles loaded by one request stay warm for later requests.
cache = GraphTileCache(engine)
 
 
class TileCoordinateRequest(BaseModel):
    latitude: float
    longitude: float
    zoom: int  # Accept values generally ranging from 0 (world) to 18 (street view)
 
 
class AddressPoint(BaseModel):
    node_id: int
    latitude: float
    longitude: float
 
 
class RouteRequest(BaseModel):
    start: AddressPoint
    goal: AddressPoint
 
 
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
    router = TileRouter(cache, engine)
    result = router.find_shortest_path(
        start_address=request.start.model_dump(),
        goal_address=request.goal.model_dump()
    )
    if result is None:
        return {"error": "Route not found"}
    path, total_time, total_distance = result
    return {
        "path": path,
        "total_time": total_time,
        "total_distance": total_distance
    }

