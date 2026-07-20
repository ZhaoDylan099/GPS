import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from "react-leaflet";
import { divIcon } from "leaflet";
import { useEffect } from "react";

const OHIO_PA_CENTER = [40.3, -81.5];
const DEFAULT_ZOOM = 7;

function pinIcon(className) {
  return divIcon({
    className: "",
    html: `<div class="pin ${className}"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

// react-leaflet doesn't auto-fit the map to new data — this component just
// watches for a new set of coordinates and re-fits the view when they change.
function FitBoundsOnRoute({ coords }) {
  const map = useMap();

  useEffect(() => {
    if (coords && coords.length > 0) {
      map.fitBounds(coords, { padding: [40, 40] });
    }
  }, [coords, map]);

  return null;
}

export default function MapView({ route, startAddress, goalAddress }) {
  const coords = route ? route.path_coordinates.map((p) => [p.latitude, p.longitude]) : null;

  return (
    <div id="map">
      <MapContainer center={OHIO_PA_CENTER} zoom={DEFAULT_ZOOM} zoomControl style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={19}
        />

        {coords && (
          <>
            {/* Glow: a wide, translucent line behind the crisp accent line —
                reads as a "highlighted route", the way modern nav apps render
                an active path. */}
            <Polyline positions={coords} pathOptions={{ color: "#4C8DFF", opacity: 0.35, weight: 10 }} />
            <Polyline positions={coords} pathOptions={{ color: "#4C8DFF", weight: 4 }} />

            <Marker position={coords[0]} icon={pinIcon("pin-start")}>
              <Popup>Start: {startAddress}</Popup>
            </Marker>
            <Marker position={coords[coords.length - 1]} icon={pinIcon("pin-goal")}>
              <Popup>Destination: {goalAddress}</Popup>
            </Marker>

            <FitBoundsOnRoute coords={coords} />
          </>
        )}
      </MapContainer>
    </div>
  );
}
