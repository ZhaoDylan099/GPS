import requests

states = [
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new-hampshire",
    "new-jersey",
    "new-mexico",
    "new-york",
    "north-carolina",
    "north-dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode-island",
    "south-carolina",
    "south-dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west-virginia",
    "wisconsin",
    "wyoming"
]

for state in states:
    url = (
        f"https://download.geofabrik.de/"
        f"north-america/us/{state}-latest.osm.pbf"
    )

    with requests.get(url, stream=True) as r:
        r.raise_for_status()

        with open(f"{state}.osm.pbf", "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)

    print(f"Downloaded {state}")