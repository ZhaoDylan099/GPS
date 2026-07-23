# GPS Routing Engine

A high-performance full-stack GPS navigation system built from scratch using **OpenStreetMap**, **PostGIS**, **FastAPI**, and **React**. The project computes real driving routes across **Ohio and Pennsylvania** by implementing a custom A* search algorithm over a road network containing approximately **21.5 million nodes** and **22.5 million edges**. Through multiple rounds of profiling and optimization, long-distance routing performance improved from **75+ seconds** to approximately **3.5 seconds** for a 300 km route.

---

## Features

* Route computation using a custom A* pathfinding implementation
* OpenStreetMap road network ingestion with Pyrosm
* PostgreSQL/PostGIS spatial database
* Dynamic graph tile loading with in-memory caching
* Address search using OpenStreetMap Nominatim
* Interactive React + Leaflet map visualization
* REST API built with FastAPI
* Dockerized backend and database deployment
* Optimized routing for long-distance navigation

---

## Demo

*(Add screenshots or a demo GIF here)*

```
Frontend (React)
        │
        ▼
 FastAPI REST API
        │
        ▼
 Graph Tile Cache
        │
        ▼
 PostgreSQL + PostGIS
        │
        ▼
 OpenStreetMap Road Network
```

---

## Tech Stack

### Backend

* Python
* FastAPI
* SQLAlchemy
* psycopg2

### Database

* PostgreSQL
* PostGIS

### Frontend

* React
* Vite
* React Leaflet
* CSS

### Data Processing

* Pyrosm
* GeoPandas
* Shapely
* OpenStreetMap (.osm.pbf)

### Deployment

* Docker
* Docker Compose

---

## System Architecture

The routing engine is divided into four major components:

### 1. Data Pipeline

Raw OpenStreetMap extracts are parsed using **Pyrosm** before being transformed into a routing graph stored inside PostgreSQL/PostGIS.

During preprocessing the pipeline:

* Extracts road intersections as graph nodes
* Builds directed road edges
* Computes travel time for every road segment
* Assigns road hierarchy rankings
* Partitions the graph into spatial tiles for efficient loading

The resulting dataset contains roughly:

* **21.5 million nodes**
* **22.5 million edges**

---

### 2. Graph Tile Cache

Loading an entire road network into memory would require several gigabytes of RAM.

Instead, the application loads only the map regions necessary for the current route.

The custom `GraphTileCache`:

* Dynamically loads tiles from PostGIS
* Caches previously visited regions
* Preloads tiles along the expected route corridor
* Merges neighboring tiles into one in-memory graph
* Reuses cached tiles across API requests

This dramatically reduces database access while keeping memory usage manageable.

---

### 3. Custom A* Router

The routing engine implements A* search with several custom optimizations.

Key improvements include:

* Straight-line heuristic using an equirectangular distance approximation
* Heuristic caching
* Dynamic road-rank filtering
* Route corridor preloading
* Lazy graph expansion

The router returns:

* Route coordinates
* Estimated travel time
* Total driving distance

---

### 4. React Frontend

The frontend provides an interactive navigation interface built with React and React Leaflet.

Users can:

* Search for start and destination addresses
* Compute driving routes
* Visualize the route on an interactive map
* View total travel distance and estimated driving time

---

## Performance Optimizations

Performance optimization became one of the largest portions of this project.

### Initial Performance

| Route                  | Time        |
| ---------------------- | ----------- |
| Local (26 km)          | 41 seconds  |
| Long Distance (300 km) | 75+ seconds |

### Final Performance

| Route                  | Time         |
| ---------------------- | ------------ |
| Local (26 km)          | ~0.6 seconds |
| Long Distance (300 km) | ~3.5 seconds |

Major optimizations included:

* Geometry-based tile caching
* Batch tile preloading
* Bounding-box lookups instead of expensive geometry operations
* Deferred graph hydration
* Reduced duplicate neighbor processing
* Extensive profiling using `cProfile`

Rather than relying on assumptions, performance improvements were guided through profiling, which identified Python-level bottlenecks that traditional optimization attempts had missed.

---

## API Endpoints

| Method | Endpoint  | Description                                    |
| ------ | --------- | ---------------------------------------------- |
| GET    | `/search` | Convert an address into the nearest graph node |
| POST   | `/route`  | Compute the shortest driving route             |
| POST   | `/tiles`  | Debug endpoint for tile loading                |

---

## Project Structure

```
project-root/
│
├── app/
│   ├── main.py
│   ├── TileRouter.py
│   ├── GraphTileCache.py
│   └── search.py
│
├── scripts/
│   ├── data.py
│   └── tile_graph.py
│
├── frontend/
│
├── tests/
│
├── init_db/
│
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Running the Project

### Clone the repository

```bash
git clone https://github.com/yourusername/gps-routing-engine.git

cd gps-routing-engine
```

### Start the backend

```bash
docker compose up --build
```

### Start the frontend

```bash
cd frontend

npm install

npm run dev
```

---

## Future Improvements

* Nationwide routing support
* Turn-by-turn navigation
* Live traffic integration
* Alternative route generation
* Frontend Docker container
* Automated edge deduplication
* Smarter corridor sizing
* End-to-end frontend testing

---

## What I Learned

This project involved much more than implementing A* search. It required solving practical software engineering challenges involving large-scale spatial data processing, database design, caching strategies, algorithm optimization, profiling, Docker deployment, and full-stack application development.

One of the biggest lessons was that **profiling should drive optimization**. Several intuitive optimization ideas produced little improvement, while profiling quickly revealed the true performance bottlenecks.


