import pickle
from sqlalchemy import text


class GraphTileCache:
    def __init__(self, engine):
        self.engine = engine
        self.loaded_tiles = set()          # tile_id values already hydrated into memory
        self.loaded_tile_bounds = {}       # tile_id -> (min_lon, min_lat, max_lon, max_lat)
        self.query_count = 0               # How many times we actually hit Postgres
        self.graph = {}
        self._neighbor_id_sets = {}        # node_id -> set of neighbor ids already in self.graph[node_id].
                                            # Built lazily: only the first time a node is touched by a
                                            # SECOND tile, since most nodes only ever appear in one tile
                                            # and never need this at all.
        self.coords = {}

        # --- DATABASE SETTINGS ---
        # NOTE: map_tiles holds a small number (~180) of large custom regions, NOT a
        # uniform slippy-map grid of small tiles. So there's no meaningful "zoom level"
        # the tiles are stored at — DATA_ZOOM below is only used to scale the safety
        # buffer we search around a point, not to compute tile indices.
        self.DATA_ZOOM = 14

    def _point_covered_locally(self, lat: float, lon: float) -> bool:
        """
        Checks whether a point falls inside any tile already loaded into memory,
        without touching the DB. Tiles are built as plain axis-aligned rectangles
        (see tile_graph.py's use of shapely.box()), so a bounding-box comparison
        is exact here — not an approximation — and avoids the substantial overhead
        of shapely's general-purpose polygon predicates (Point construction, GEOS
        calls, numpy interop) on what's actually a trivial containment check. This
        matters a lot in practice: profiling showed this check alone running
        ~4.8 million times over the course of a single long route.
        """
        for min_lon, min_lat, max_lon, max_lat in self.loaded_tile_bounds.values():
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                return True
        return False

    def _hydrate_rows(self, rows) -> int:
        """
        Given rows of (tile_id, min_lon, min_lat, max_lon, max_lat, graph_data),
        loads any tile not already in memory: stores its bounding box for future
        local coverage checks, unpickles its graph data, and merges it into
        self.graph/self.coords. Returns how many tiles were newly hydrated.
        """
        new_tile_count = 0
        for tile_id, min_lon, min_lat, max_lon, max_lat, graph_blob in rows:
            if tile_id in self.loaded_tiles:
                continue
            self.loaded_tiles.add(tile_id)
            self.loaded_tile_bounds[tile_id] = (min_lon, min_lat, max_lon, max_lat)
            new_tile_count += 1

            tile_data = pickle.loads(graph_blob)
            self.coords.update(tile_data["coords"])

            for node_id, targets in tile_data["graph"].items():
                if node_id not in self.graph:
                    # Common case (most nodes only ever appear in one tile): just
                    # take the list as-is, no copy, no dedup set built up front.
                    self.graph[node_id] = targets
                else:
                    # This node was already added by an earlier tile — now, and only
                    # now, do we pay for building a dedup set, and only once.
                    existing = self._neighbor_id_sets.get(node_id)
                    if existing is None:
                        existing = {t[0] for t in self.graph[node_id]}
                        self._neighbor_id_sets[node_id] = existing
                    for target_node, travel_time, length_m, road_rank in targets:
                        if target_node not in existing:
                            self.graph[node_id].append((target_node, travel_time, length_m, road_rank))
                            existing.add(target_node)
        return new_tile_count

    def load_tile_for_coordinate(self, lat: float, lon: float, zoom: int) -> bool:
        """
        Loads whichever real map_tiles cover this point, hydrating each tile's
        packed graph data into memory.
        """
        # 1. Local check first: if a tile we've already loaded covers this point,
        # skip the DB entirely. No round-trip at all.
        if self._point_covered_locally(lat, lon):
            return True

        # 2. Not covered by anything we have yet. Search a small buffer around the
        # point rather than the exact point, both to be safe near tile borders and
        # so a more zoomed-out caller pulls in a bit more surrounding area at once.
        safe_zoom = max(10, zoom)
        zoom_diff = max(0, self.DATA_ZOOM - safe_zoom)
        buffer_m = min(20_000, 1_000 * (2 ** zoom_diff))

        query = text("""
            SELECT tile_id,
                   ST_XMin(tile_geom) AS min_lon, ST_YMin(tile_geom) AS min_lat,
                   ST_XMax(tile_geom) AS max_lon, ST_YMax(tile_geom) AS max_lat,
                   graph_data
            FROM map_tiles
            WHERE ST_DWithin(
                tile_geom::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :buffer_m
            );
        """)

        with self.engine.connect() as conn:
            results = conn.execute(query, {
                "lon": lon, "lat": lat, "buffer_m": buffer_m
            }).fetchall()
        self.query_count += 1

        new_tile_count = self._hydrate_rows(results)
        print(f"Zoom: {zoom} | {len(results)} tile(s) within {buffer_m}m, {new_tile_count} newly loaded")
        return True

    def preload_route_corridor(self, start_lat: float, start_lon: float,
                                goal_lat: float, goal_lon: float,
                                buffer_m: float = 25_000) -> bool:
        """
        Pre-fetches every tile within `buffer_m` meters of the straight line between
        start and goal, in a single query — so a long route doesn't have to stop
        and wait on a separate DB round-trip every time A*'s frontier wanders into
        a new tile. Real routes can still detour further than this straight-line
        buffer (e.g. around mountains or rivers); anything outside it is still
        picked up lazily by load_tile_for_coordinate as the search reaches it.
        """
        query = text("""
            SELECT tile_id,
                   ST_XMin(tile_geom) AS min_lon, ST_YMin(tile_geom) AS min_lat,
                   ST_XMax(tile_geom) AS max_lon, ST_YMax(tile_geom) AS max_lat,
                   graph_data
            FROM map_tiles
            WHERE ST_DWithin(
                tile_geom::geography,
                ST_SetSRID(
                    ST_MakeLine(
                        ST_MakePoint(:start_lon, :start_lat),
                        ST_MakePoint(:goal_lon, :goal_lat)
                    ),
                    4326
                )::geography,
                :buffer_m
            );
        """)

        with self.engine.connect() as conn:
            results = conn.execute(query, {
                "start_lon": start_lon, "start_lat": start_lat,
                "goal_lon": goal_lon, "goal_lat": goal_lat,
                "buffer_m": buffer_m
            }).fetchall()
        self.query_count += 1

        new_tile_count = self._hydrate_rows(results)
        print(f"Route corridor preload | {len(results)} tile(s) within {buffer_m:.0f}m of route line, "
              f"{new_tile_count} newly loaded")
        return True

    def fetch_node_coords(self, node_id):
        query = text("SELECT lat, lon FROM nodes WHERE node_id = :node_id")
        with self.engine.connect() as conn:
            result = conn.execute(query, {"node_id": node_id}).fetchone()
        return (result[0], result[1]) if result else None