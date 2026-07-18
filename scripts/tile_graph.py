import pickle
import pandas as pd
from sqlalchemy import create_engine, text
from shapely.geometry import box

engine = create_engine("")


def build_and_save_spatial_tiles():
    print("Loading raw network coordinates...")
    nodes = pd.read_sql("SELECT node_id, lat, lon FROM nodes", con=engine)
    edges = pd.read_sql("SELECT source, target, travel_time, oneway, length_m, road_rank FROM edges", con=engine)

    min_lat, max_lat = 38.4, 42.3
    min_lon, max_lon = -84.8, -74.7
    num_tiles_x, num_tiles_y = 24, 10

    lat_step = (max_lat - min_lat) / num_tiles_y
    lon_step = (max_lon - min_lon) / num_tiles_x

    print("Building coordinate and edge lookup tables...")
    all_coords = {row.node_id: (row.lat, row.lon) for row in nodes.itertuples()}

    edge_map = {}
    for row in edges.itertuples():
        edge_map.setdefault(row.source, []).append((row.target, row.travel_time, row.length_m, row.road_rank))
        if row.oneway != 'yes':
            edge_map.setdefault(row.target, []).append((row.source, row.travel_time, row.length_m, row.road_rank))

    print("Partitioning network graph into database tiles...")
    tiles_saved = 0

    for tx in range(num_tiles_x):
        for ty in range(num_tiles_y):
            tile_min_lon = min_lon + (tx * lon_step)
            tile_max_lon = tile_min_lon + lon_step
            tile_min_lat = min_lat + (ty * lat_step)
            tile_max_lat = tile_min_lat + lat_step

            # --- Step 1: Find all nodes whose coordinates fall inside this tile ---
            tile_coords = {}
            for node_id, (lat, lon) in all_coords.items():
                if (tile_min_lat <= lat <= tile_max_lat) and (tile_min_lon <= lon <= tile_max_lon):
                    tile_coords[node_id] = (lat, lon)

            if not tile_coords:
                continue

            tile_graph = {}

            # --- Step 2: First pass — process all native nodes inside the tile ---
            # For each native node, record its edges and pull in any cross-boundary
            # target coords so the router doesn't lose track of them.
            for source_node in list(tile_coords.keys()):
                if source_node not in edge_map:
                    continue
                for target_node, travel_time, length_m, road_rank in edge_map[source_node]:
                    # Pull cross-boundary target coords into this tile as a buffer node
                    if target_node not in tile_coords and target_node in all_coords:
                        tile_coords[target_node] = all_coords[target_node]
                    tile_graph.setdefault(source_node, []).append((target_node, travel_time, length_m, road_rank))

            # --- Step 3 removed ---
            # The previous version of this script also expanded a SECOND hop out
            # from the tile (every neighbor-of-a-neighbor), on the theory that A*
            # needed full edge data for buffer nodes to avoid dead-ending at tile
            # borders. That expansion is bounded by graph hops, not real distance —
            # so in areas with long, sparse edges (rural highways) it could pull in
            # nodes many km beyond the tile boundary, and neighboring tiles ended up
            # massively duplicating each other's border-area data.
            #
            # It's unnecessary: TileRouter already calls load_tile_for_coordinate on
            # a node's real coordinates before processing its edges, every time it's
            # visited. So a buffer node with coords-but-no-edges here simply triggers
            # the router to load whichever tile treats it as native (Step 2 above),
            # supplying its real edges on demand instead of duplicating them into
            # every neighboring tile ahead of time.

            # --- Step 4: Package and save to PostGIS ---
            tile_payload = {"graph": tile_graph, "coords": tile_coords}
            binary_blob = pickle.dumps(tile_payload)
            polygon_wkt = box(tile_min_lon, tile_min_lat, tile_max_lon, tile_max_lat).wkt

            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO map_tiles (tile_geom, graph_data)
                        VALUES (ST_SetSRID(ST_GeomFromText(:wkt), 4326), :blob)
                    """),
                    {"wkt": polygon_wkt, "blob": binary_blob}
                )

            tiles_saved += 1
            if tiles_saved % 20 == 0:
                print(f"  Saved {tiles_saved} tiles so far...")

    print(f"Done. {tiles_saved} tiles saved to PostGIS.")


if __name__ == "__main__":
    # Clear old tiles first before rebuilding
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE map_tiles"))
    print("Old tiles cleared.")

    build_and_save_spatial_tiles()