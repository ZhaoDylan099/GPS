CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE nodes (
	node_id BIGINT PRIMARY KEY,
	lat DOUBLE PRECISION NOT NULL,
	lon DOUBLE PRECISION NOT NULL,
	geom GEOMETRY(Point, 4326) NOT NULL,
	state text
);

CREATE INDEX nodes_idx ON nodes USING GIST(geom);

CREATE TABLE edges (
    edge_id BIGSERIAL PRIMARY KEY,
	osm_way_id BIGINT,
    source BIGINT NOT NULL,
    target BIGINT NOT NULL,
    road_name TEXT,
    length_m DOUBLE PRECISION,
    speed_limit DOUBLE PRECISION,
    travel_time DOUBLE PRECISION,
    oneway TEXT,
	road_rank SMALLINT,
	road_type TEXT NOT NULL,										
    geom GEOMETRY(LineString, 4326) NOT NULL,
	state text
);

CREATE INDEX idx_edges_source
ON edges(source);

CREATE INDEX idx_edges_target
ON edges(target);

CREATE INDEX idx_edges_geom
ON edges
USING GIST (geom);

CREATE INDEX idx_edges_type
ON edges(road_type);

CREATE INDEX idx_edges_rank
ON edges(road_rank);

CREATE TABLE map_tiles (
    tile_id SERIAL PRIMARY KEY,
    tile_geom GEOMETRY(Polygon, 4326) NOT NULL, 
    graph_data BYTEA NOT NULL                 
);


CREATE INDEX idx_map_tiles_geom ON map_tiles USING GIST (tile_geom);