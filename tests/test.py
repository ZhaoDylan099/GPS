"""
Integration test script for the tiled GPS router.

Unlike a mocked unit test, this hits your REAL Postgres/PostGIS database and
geocoding service, exercising the actual code paths in:
    - GraphTileCache.load_tile_for_coordinate / fetch_node_coords
    - search.search_location
    - TileRouter.find_shortest_path

Configure the connection string via the DATABASE_URL environment variable,
or edit DEFAULT_DB_URL below. Configure the two test addresses via
TEST_START_ADDRESS / TEST_GOAL_ADDRESS, or edit the defaults below.

Run with:
    python test_integration.py
"""

import os
import sys
import time

from sqlalchemy import create_engine, text

from GraphTileCache import GraphTileCache
from search import search_location
from TileRouter import TileRouter

DEFAULT_DB_URL = ""
DB_URL = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)

# Pick two addresses that are close enough together to route between quickly
# during testing. Override via env vars if you want to test a longer route.
START_ADDRESS = os.environ.get("TEST_START_ADDRESS", "Columbus, OH")
GOAL_ADDRESS = os.environ.get("TEST_GOAL_ADDRESS", "Pittsburgh, OH")

# Roughly downtown Columbus, OH — used for the raw tile-loading test.
TEST_LAT = 39.9612
TEST_LON = -82.9988


def _section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_db_connection(engine):
    _section("1. Database connection")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"Connected OK to: {DB_URL}")

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT extname FROM pg_extension WHERE extname = 'postgis'"
        )).fetchone()
    assert result is not None, (
        "PostGIS extension not found. GraphTileCache's tile-loading query relies on "
        "ST_Intersects/ST_MakeEnvelope, which require PostGIS. Run: CREATE EXTENSION postgis;"
    )
    print("PostGIS extension confirmed.")


def test_table_counts(engine):
    _section("2. Database table counts")
    with engine.connect() as conn:
        total_nodes = conn.execute(text("SELECT COUNT(*) FROM nodes")).scalar()
        total_edges = conn.execute(text("SELECT COUNT(*) FROM edges")).scalar()
        total_tiles = conn.execute(text("SELECT COUNT(*) FROM map_tiles")).scalar()

    print(f"Total nodes:     {total_nodes}")
    print(f"Total edges:     {total_edges}")
    print(f"Total map_tiles: {total_tiles}")

    assert total_nodes is not None and total_nodes > 0, (
        "nodes table is empty — has the node-import step been run?"
    )
    assert total_tiles is not None and total_tiles > 0, (
        "map_tiles table is empty — has the tile-generation step been run?"
    )

    return {"nodes": total_nodes, "edges": total_edges, "tiles": total_tiles}


def test_tile_loading(engine, table_counts):
    _section("3. GraphTileCache.load_tile_for_coordinate")

    cache = GraphTileCache(engine)

    start = time.time()
    ok = cache.load_tile_for_coordinate(TEST_LAT, TEST_LON, zoom=10)
    elapsed = time.time() - start

    assert ok is True, "load_tile_for_coordinate should return True"
    assert len(cache.loaded_tiles) > 0, "Expected at least one tile to be loaded"
    print(f"Loaded {len(cache.loaded_tiles)} tile(s) for this viewport in {elapsed:.2f}s "
          f"({len(cache.loaded_tiles)}/{table_counts['tiles']} of all tiles)")
    print(f"Nodes cached in memory: {len(cache.coords)} (out of {table_counts['nodes']} total in DB)")
    print(f"Graph nodes with edges: {len(cache.graph)}")

    # Calling again for the same spot should now hit the local grid-cell cache and
    # skip the DB round-trip entirely, so loaded_tiles shouldn't grow.
    tiles_before = len(cache.loaded_tiles)
    cache.load_tile_for_coordinate(TEST_LAT, TEST_LON, zoom=10)
    tiles_after = len(cache.loaded_tiles)
    assert tiles_after == tiles_before, "Re-loading the same area should not add new tiles"
    print("Cache hit confirmed: re-requesting the same area loaded no new tiles.")

    if cache.coords:
        sample_node = next(iter(cache.coords))
        coords_direct = cache.fetch_node_coords(sample_node)
        assert coords_direct is not None, "fetch_node_coords should find a node we just loaded"
        print(f"fetch_node_coords sanity check OK for node {sample_node}: {coords_direct}")

    return cache


def test_search(engine):
    _section("4. search.search_location")

    node_id, lat, lon = search_location(START_ADDRESS, engine)
    print(f"'{START_ADDRESS}' -> node_id={node_id}, lat={lat}, lon={lon}")
    assert node_id is not None, f"Expected to resolve a node for '{START_ADDRESS}'"
    assert lat is not None and lon is not None

    node_id2, lat2, lon2 = search_location(GOAL_ADDRESS, engine)
    print(f"'{GOAL_ADDRESS}' -> node_id={node_id2}, lat={lat2}, lon={lon2}")
    assert node_id2 is not None, f"Expected to resolve a node for '{GOAL_ADDRESS}'"

    # Also confirm a nonsense address degrades gracefully instead of crashing.
    bad_node, bad_lat, bad_lon = search_location("asdkjfhaskdjfh nonexistent place 12345", engine)
    assert bad_node is None and bad_lat is None and bad_lon is None, (
        "An unresolvable address should return (None, None, None), not raise"
    )
    print("Unresolvable-address fallback OK: returned (None, None, None) as expected.")

    return {
        "start": {"node_id": node_id, "latitude": lat, "longitude": lon},
        "goal": {"node_id": node_id2, "latitude": lat2, "longitude": lon2},
    }


def test_routing(engine, cache, addresses):
    _section("5. TileRouter.find_shortest_path")

    router = TileRouter(cache, engine)

    nodes_before = len(cache.coords)
    tiles_before = len(cache.loaded_tiles)

    start = time.time()
    result = router.find_shortest_path(
        start_address=addresses["start"],
        goal_address=addresses["goal"],
    )
    elapsed = time.time() - start

    nodes_after = len(cache.coords)
    tiles_after = len(cache.loaded_tiles)
    print(f"Nodes cached: {nodes_before} -> {nodes_after} "
          f"(+{nodes_after - nodes_before} loaded during search)")
    print(f"Tiles cached: {tiles_before} -> {tiles_after} "
          f"(+{tiles_after - tiles_before} loaded during search)")

    if result is None:
        print(f"No route found between '{START_ADDRESS}' and '{GOAL_ADDRESS}' ({elapsed:.2f}s).")
        print("This may be expected if the two addresses aren't connected in your graph data.")
        return

    path, total_time, total_distance = result
    assert len(path) >= 2, "A valid route should include at least a start and end node"
    assert total_time >= 0
    assert total_distance >= 0

    print(f"Route found in {elapsed:.2f}s")
    print(f"Nodes in path: {len(path)}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Total distance: {total_distance:.0f} m")
    print(f"First few nodes: {path[:5]}")
    print(f"Last few nodes:  {path[-5:]}")


def main():
    print(f"Using DATABASE_URL: {DB_URL}")
    engine = create_engine(DB_URL)

    try:
        test_db_connection(engine)
        table_counts = test_table_counts(engine)
        cache = test_tile_loading(engine, table_counts)
        addresses = test_search(engine)
        test_routing(engine, cache, addresses)
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        print("Check that Postgres/PostGIS is running, DATABASE_URL is correct, "
              "and the map_tiles/nodes tables are populated.")
        sys.exit(1)

    _section("All tests passed")


if __name__ == "__main__":
    main()