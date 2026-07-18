"""
Profiles a real route through the actual TileRouter/GraphTileCache code against
your live database, using cProfile, so we can see exactly where time goes
instead of continuing to guess.

Run with:
    python profile_route.py

Configure via env vars (same as test_integration.py):
    DATABASE_URL, TEST_START_ADDRESS, TEST_GOAL_ADDRESS
"""

import cProfile
import io
import os
import pstats

from sqlalchemy import create_engine

from GraphTileCache import GraphTileCache
from search import search_location
from TileRouter import TileRouter

DEFAULT_DB_URL = ""
DB_URL = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)

START_ADDRESS = os.environ.get("TEST_START_ADDRESS", "Columbus, OH")
GOAL_ADDRESS = os.environ.get("TEST_GOAL_ADDRESS", "Pittsburgh, PA")


def main():
    engine = create_engine(DB_URL)
    cache = GraphTileCache(engine)
    router = TileRouter(cache, engine)

    print(f"Geocoding '{START_ADDRESS}' and '{GOAL_ADDRESS}'...")
    start_node, start_lat, start_lon = search_location(START_ADDRESS, engine)
    goal_node, goal_lat, goal_lon = search_location(GOAL_ADDRESS, engine)

    if start_node is None or goal_node is None:
        print("Could not geocode one of the addresses.")
        return

    start_address = {"node_id": start_node, "latitude": start_lat, "longitude": start_lon}
    goal_address = {"node_id": goal_node, "latitude": goal_lat, "longitude": goal_lon}

    profiler = cProfile.Profile()
    profiler.enable()
    result = router.find_shortest_path(start_address=start_address, goal_address=goal_address)
    profiler.disable()

    if result is None:
        print("No path found.")
    else:
        path, total_time, total_distance = result
        print(f"\nRoute found: {len(path)} nodes, {total_time:.2f} min, {total_distance:.0f} m")

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)

    print("\n" + "=" * 70)
    print("TOP 25 FUNCTIONS BY CUMULATIVE TIME (includes time in sub-calls)")
    print("=" * 70)
    stats.sort_stats("cumulative")
    stats.print_stats(25)
    print(stream.getvalue())

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    print("=" * 70)
    print("TOP 25 FUNCTIONS BY SELF TIME (excludes time in sub-calls — the real hotspots)")
    print("=" * 70)
    stats.sort_stats("tottime")
    stats.print_stats(25)
    print(stream.getvalue())

    profiler.dump_stats("route_profile.prof")
    print("Full profile saved to route_profile.prof "
          "(open with `python -m pstats route_profile.prof`, or snakeviz for a visual)")


if __name__ == "__main__":
    main()