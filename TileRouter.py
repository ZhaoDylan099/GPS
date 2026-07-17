import heapq
import math
import time


class TileRouter:
    def __init__(self, cache, db_engine):
        self.cache = cache
        self.db_engine = db_engine

    def _haversine_meters(self, lat1, lon1, lat2, lon2):
        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))

    def _fast_distance_meters(self, lat1, lon1, lat2, lon2):
        """
        Equirectangular approximation of great-circle distance — a few times
        cheaper than full haversine (fewer trig calls: no sin/asin), with
        negligible error at routing scales (well under 1% for distances up to
        a few hundred km). Used in the A* hot path (_getHeuristic and the
        road-rank proximity check), which run on every node/edge relaxation —
        potentially hundreds of thousands of times per search — so the per-call
        savings compound significantly. The one-time overall trip-distance
        calculation still uses the more precise _haversine_meters.
        """
        R = 6_371_000
        lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
        lat_avg = (lat1_r + lat2_r) / 2.0
        dx = math.radians(lon2 - lon1) * math.cos(lat_avg)
        dy = lat2_r - lat1_r
        return R * math.sqrt(dx * dx + dy * dy)

    def _getHeuristic(self, node_lat, node_lon, goal_lat, goal_lon):
        dist = self._fast_distance_meters(node_lat, node_lon, goal_lat, goal_lon)
        return dist / (70 * 0.44704)

    def _get_road_rank_filter(self, current_lat, current_lon, start_lat, start_lon, goal_lat, goal_lon):
        # Allow small/local roads near either endpoint of the trip, and restrict
        # to progressively bigger roads the further we are from BOTH endpoints.
        dist_to_start = self._fast_distance_meters(current_lat, current_lon, start_lat, start_lon)
        dist_to_goal = self._fast_distance_meters(current_lat, current_lon, goal_lat, goal_lon)
        proximity = min(dist_to_start, dist_to_goal)
        if proximity < 2000:
            return 8   # everything
        elif proximity < 8000:
            return 5   # + tertiary
        elif proximity < 20000:
            return 4   # + secondary
        else:
            return 3   # highway

    def find_shortest_path(self, start_address, goal_address):
        start, start_lat, start_lon = start_address["node_id"], start_address["latitude"], start_address["longitude"]
        goal, goal_lat, goal_lon = goal_address["node_id"], goal_address["latitude"], goal_address["longitude"]

        # Preload the whole corridor between start and goal in one batched query,
        # instead of only the two endpoint tiles — avoids the search loop stopping
        # to hit the DB every time it crosses into a tile it hasn't seen yet.
        # NOTE: each tile here is expensive to hydrate (large payload, lots of
        # overlap with neighbors), so a wider buffer isn't free — it trades cheap
        # DB round-trips for expensive tile unpickling/merging. Since round-trips
        # are already cheap thanks to the local geometry cache, the buffer should
        # stay tight: just enough to avoid most lazy mid-search queries, not so
        # wide it pulls in tiles the route never actually uses.
        trip_distance_m = self._haversine_meters(start_lat, start_lon, goal_lat, goal_lon)
        corridor_buffer_m = max(15_000, min(60_000, trip_distance_m * 0.15))

        preload_start_time = time.time()
        self.cache.preload_route_corridor(start_lat, start_lon, goal_lat, goal_lon, buffer_m=corridor_buffer_m)
        preload_elapsed = time.time() - preload_start_time
        print(f"[diagnostics] Corridor preload time: {preload_elapsed:.2f}s")

        search_start_time = time.time()
        queries_before_search = self.cache.query_count

        queue = []
        track = {start: None}
        dist_score = {start: 0}
        g_score = {start: 0}
        counter = 0
        visited = set()
        heuristic_cache = {}  # node_id -> heuristic value, since a node can be relaxed
                               # (and its heuristic recomputed) more than once as A* finds
                               # progressively cheaper paths to it

        initial_h = self._getHeuristic(start_lat, start_lon, goal_lat, goal_lon)
        heapq.heappush(queue, (initial_h, counter, start))

        while queue:
            node = heapq.heappop(queue)[2]
            if node in visited:
                continue

            visited.add(node)

            if len(visited) % 10_000 == 0:
                print(f"Visited {len(visited)} nodes | Tiles loaded: {len(self.cache.loaded_tiles)} | Coords: {len(self.cache.coords)}")

            # Proactively load tile for current node as frontier expands
            if node in self.cache.coords:
                self.cache.load_tile_for_coordinate(*self.cache.coords[node], zoom=10)

                node_lat, node_lon = self.cache.coords[node]
                rank_limit = self._get_road_rank_filter(node_lat, node_lon, start_lat, start_lon, goal_lat, goal_lon)
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

                search_elapsed = time.time() - search_start_time
                queries_during_search = self.cache.query_count - queries_before_search
                print(f"[diagnostics] Nodes visited: {len(visited)} | "
                      f"DB queries during search: {queries_during_search} | "
                      f"Search loop time: {search_elapsed:.2f}s")

                return reconstruct, total_time, total_distance

            for target, travel_time, length_m, road_rank in self.cache.graph.get(node, []):
                if road_rank > rank_limit:
                    continue
                if target in visited:
                    continue

                if target not in self.cache.coords:
                    coords = self.cache.fetch_node_coords(target)
                    if coords is None:
                        continue
                    self.cache.load_tile_for_coordinate(coords[0], coords[1], zoom=10)

                if target not in self.cache.coords:
                    continue

                g = travel_time + g_score[node]
                if g < g_score.get(target, float('inf')):
                    if target not in heuristic_cache:
                        heuristic_cache[target] = self._getHeuristic(
                            self.cache.coords[target][0], self.cache.coords[target][1],
                            goal_lat, goal_lon
                        )
                    heuristic = heuristic_cache[target]
                    counter += 1
                    heapq.heappush(queue, (heuristic + g, counter, target))
                    track[target] = node
                    g_score[target] = g
                    dist_score[target] = dist_score[node] + length_m

        search_elapsed = time.time() - search_start_time
        queries_during_search = self.cache.query_count - queries_before_search
        print(f"Search exhausted. Visited {len(visited)} nodes, loaded {len(self.cache.loaded_tiles)} tiles")
        print(f"[diagnostics] Nodes visited: {len(visited)} | "
              f"DB queries during search: {queries_during_search} | "
              f"Search loop time: {search_elapsed:.2f}s")
        print(f"Goal in visited:  {goal in visited}")
        print(f"Goal in coords:   {goal in self.cache.coords}")
        print(f"Goal in graph:    {goal in self.cache.graph}")
        print(f"Goal in g_score:  {goal in g_score}")
        return None


if __name__ == "__main__":
    from sqlalchemy import create_engine
    from GraphTileCache import GraphTileCache
    from search import search_location

    engine = create_engine("")
    cache = GraphTileCache(engine)
    router = TileRouter(cache, engine)

    start_node, start_lat, start_lon = search_location("Columbus, OH", engine)
    goal_node, goal_lat, goal_lon = search_location("Pittsburgh, PA", engine)

    if start_node is None or goal_node is None:
        print("Could not geocode one of the addresses.")
    else:
        result = router.find_shortest_path(
            start_address={"node_id": start_node, "latitude": start_lat, "longitude": start_lon},
            goal_address={"node_id": goal_node, "latitude": goal_lat, "longitude": goal_lon}
        )

        if result is None:
            print("No path found.")
        else:
            optimal_path, total_time, total_distance = result
            print(f"Calculated Path Time: {total_time} sec across {len(optimal_path)} intersections.")
            print(f"Total Distance: {total_distance} meters.")