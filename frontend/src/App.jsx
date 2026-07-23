import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import MapView from "./components/MapView.jsx";
import { findRoute } from "./api.js";
import SearchBar from "./components/SearchBar.jsx";

export default function App() {
  const [startAddress, setStartAddress] = useState("Columbus, OH");
  const [goalAddress, setGoalAddress] = useState("Pittsburgh, PA");
  const [route, setRoute] = useState(null);
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleFindRoute() {
    if (!startAddress.trim() || !goalAddress.trim()) {
      setStatus({ message: "Enter both a start and destination.", kind: "error" });
      return;
    }

    setIsLoading(true);
    setRoute(null);
    setStatus({ message: "Finding route... (long routes can take a few seconds)", kind: "" });

    try {
      const data = await findRoute(startAddress, goalAddress);
      if (!data.path_coordinates || data.path_coordinates.length === 0) {
        setStatus({ message: "Route found, but no coordinates were returned.", kind: "error" });
        return;
      }
      setRoute(data);
      setStatus({ message: "Route found.", kind: "success" });
    } catch (err) {
      setStatus({
        message: `Could not reach the API. Is it running, and is CORS enabled? (${err.message})`,
        kind: "error",
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div id="layout">
      <Sidebar
        startAddress={startAddress}
        setStartAddress={setStartAddress}
        goalAddress={goalAddress}
        setGoalAddress={setGoalAddress}
        onFindRoute={handleFindRoute}
        isLoading={isLoading}
        status={status}
        route={route}
      />
      <MapView route={route} startAddress={startAddress} goalAddress={goalAddress} />
    </div>
  );

  async function handleSearchAddress(address) {
    try {
      const data = await searchAddress(address);
      if (!data.coordinates) {
        setStatus({ message: "Address found, but no coordinates were returned.", kind: "error" });
        return;
      }
      return data.coordinates;
    } catch (err) {
      setStatus({
        message: `Could not reach the API. Is it running, and is CORS enabled? (${err.message})`,
        kind: "error",
      });
    }
  }

  return (
    <div id="layout">
      <SearchBar
        address={startAddress}
        setAddress={setStartAddress}
        onSearch={handleSearchAddress}
        isLoading={isLoading}
        status={status}
      />
    </div>
  );

}

