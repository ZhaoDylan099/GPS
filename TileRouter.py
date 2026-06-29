import pickle
import pandas as pd
from sqlalchemy import create_engine, text
from shapely.geometry import box
import heapq
from geopy.geocoders import Nominatim
import math

engine = create_engine("postgresql://postgres:@localhost:5432/GPS")

class TiledRouter:
    def __init__(self, db_engine):
        self.engine = db_engine
        self.loaded_tiles = set()  # ← fixed
        self.graph = {}
        self.coords = {}

    def _load_tile_for_coordinate(self, lat, lon):
        min_lat, min_lon = 38.4, -84.8
        lat_step = (42.3 - 38.4) / 10
        lon_step = (-74.7 - -84.8) / 24

        # Snap to the exact tile grid origin
        tile_row = int((lat - min_lat) / lat_step)
        tile_col = int((lon - min_lon) / lon_step)
        tile_key = (tile_row, tile_col)

        if tile_key in self.loaded_tiles:
            return
        self.loaded_tiles.add(tile_key)

        query = text("""
            SELECT graph_data FROM map_tiles 
            WHERE ST_Intersects(tile_geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) 
            LIMIT 1;
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query, {"lon": lon, "lat": lat}).fetchone()

        if result is None:
            print(f"WARNING: No tile found for ({lat}, {lon})")
            return

        tile_data = pickle.loads(result[0])
        self.coords.update(tile_data["coords"])
        for node_id, targets in tile_data["graph"].items():
            if node_id not in self.graph:
                self.graph[node_id] = targets
            else:
                existing = {neighbor for neighbor, _, _, _ in self.graph[node_id]}
                for target_node, travel_time, length_m, road_rank in targets:
                    if target_node not in existing:
                        self.graph[node_id].append((target_node, travel_time, length_m, road_rank))

        print(f"Loaded tile ({tile_row}, {tile_col}) | Total tiles: {len(self.loaded_tiles)} | Coords: {len(self.coords)}")

    def _haversine_meters(self, lat1, lon1, lat2, lon2):
        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
        return R * 2 * math.asin(math.sqrt(a))

    def _getHeuristic(self, node_lat, node_lon, goal_lat, goal_lon):
        dist = self._haversine_meters(node_lat, node_lon, goal_lat, goal_lon)
        return dist / (70 * 0.44704)

    def _fetch_node_coords(self, node_id):
        query = text("SELECT lat, lon FROM nodes WHERE node_id = :node_id")
        with self.engine.connect() as conn:
            result = conn.execute(query, {"node_id": node_id}).fetchone()
        return (result[0], result[1]) if result else None

    def fetch_nearest_node_id(self, lat, lon, sql_engine):
        query = """
        SELECT node_id, lat, lon 
        FROM nodes 
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326) 
        LIMIT 1;
        """
        result = pd.read_sql(query, con=sql_engine, params=(lon, lat))
        if not result.empty:
            return result.iloc[0]['node_id'].item(), result.iloc[0]['lat'].item(), result.iloc[0]['lon'].item()
        return None

    def _get_road_rank_filter(self, current_lat, current_lon, goal_lat, goal_lon):
        dist_km_start = self._haversine_meters(current_lat, current_lon, goal_lat, goal_lon)
        dist_km_goal = self._haversine_meters(goal_lat, goal_lon, current_lat, current_lon)
        proximity = min(dist_km_start, dist_km_goal)
        if proximity < 2000:
            return 8   # everything
        elif proximity < 8000:
            return 5   # + tertiary
        elif proximity < 20000:
            return 4   # + secondary
        else:
            return 3   # highway

    def find_shortest_path(self, start_address, goal_address):
        geolocator = Nominatim(user_agent="tiled_router")
        start_location = geolocator.geocode(start_address)
        goal_location = geolocator.geocode(goal_address)

        start, start_lat, start_lon = self.fetch_nearest_node_id(start_location.latitude, start_location.longitude, self.engine)
        goal, goal_lat, goal_lon = self.fetch_nearest_node_id(goal_location.latitude, goal_location.longitude, self.engine)

        self._load_tile_for_coordinate(start_lat, start_lon)
        self._load_tile_for_coordinate(goal_lat, goal_lon)


        print(f"Start {start} in coords: {start in self.coords}, in graph: {start in self.graph}")
        print(f"Goal  {goal} in coords: {goal in self.coords},  in graph: {goal in self.graph}")
        print(f"Start neighbors: {self.graph.get(start, [])[:3]}")
        print(f"Goal  neighbors: {self.graph.get(goal, [])[:3]}")

        queue = []
        track = {start: None}
        dist_score = {start: 0}
        g_score = {start: 0}
        counter = 0
        visited = set()



        initial_h = self._getHeuristic(start_lat, start_lon, goal_lat, goal_lon)
        heapq.heappush(queue, (initial_h, counter, start))

        while queue:
            node = heapq.heappop(queue)[2]
            if node in visited:
                continue

            if len(visited) % 10_000 == 0:
                print(f"Visited {len(visited)} nodes | Tiles loaded: {len(self.loaded_tiles)} | Coords: {len(self.coords)}")

            visited.add(node)

            # Proactively load tile for current node as frontier expands
            if node in self.coords:
                self._load_tile_for_coordinate(*self.coords[node])

                node_lat, node_lon = self.coords[node]
                rank_limit = self._get_road_rank_filter(node_lat, node_lon, goal_lat, goal_lon)
            else:
                rank_limit = 8  # If we don't have coordinates, allow all road ranks

            if node == goal:
                total_time = g_score[goal]
                total_distance = dist_score[goal]
                reconstruct = []
                current = goal
                while track[current] is not None:
                    reconstruct.append(current)
                    current = track[current]
                reconstruct.append(start)
                reconstruct.reverse()
                return reconstruct, total_time, total_distance

            for target, travel_time, length_m, road_rank in self.graph.get(node, []):

                
                if road_rank > rank_limit:
                    continue
                if target in visited:
                    continue

                if target not in self.coords:
                    coords = self._fetch_node_coords(target)
                    if coords is None:
                        continue
                    self._load_tile_for_coordinate(coords[0], coords[1])

                    

                if target not in self.coords:
                    continue
                
                

                g = travel_time + g_score[node]
                if g < g_score.get(target, float('inf')):
                    heuristic = self._getHeuristic(
                        self.coords[target][0], self.coords[target][1],
                        goal_lat, goal_lon
                    )
                    counter += 1
                    heapq.heappush(queue, (heuristic + g, counter, target))
                    track[target] = node
                    g_score[target] = g
                    dist_score[target] = dist_score[node] + length_m

        print(f"Search exhausted. Visited {len(visited)} nodes, loaded {len(self.loaded_tiles)} tiles")
        print(f"Goal in visited:  {goal in visited}")
        print(f"Goal in coords:   {goal in self.coords}")
        print(f"Goal in graph:    {goal in self.graph}")
        print(f"Goal in g_score:  {goal in g_score}")
        print(f"Goal node ID: {goal} @ ({goal_lat}, {goal_lon})")

        # Check what neighbors the goal has
        goal_neighbors = self.graph.get(goal, [])
        print(f"Goal has {len(goal_neighbors)} neighbors in graph")

        # Check if goal was ever added to the queue
        print(f"Goal g_score: {g_score.get(goal, 'NEVER REACHED')}")

        # Sample what the last few visited nodes look like geographically
        sample = list(visited)[-5:]
        for n in sample:
            if n in self.coords:
                print(f"  late visited node {n} @ {self.coords[n]}")
        return None  # ← fixed


if __name__ == "__main__":
    router = TiledRouter(engine)

    result = router.find_shortest_path(
        start_address="Columbus, OH",
        goal_address="Pittsburgh, PA"
    )

    if result is None:
        print("No path found.")
    else:
        optimal_path, total_time, total_distance = result
        print(f"Calculated Path Time: {total_time} mins across {len(optimal_path)} intersections.")
        print(f"Total Distance: {total_distance} meters.")