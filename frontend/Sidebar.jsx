export default function Sidebar({
  startAddress, setStartAddress,
  goalAddress, setGoalAddress,
  onFindRoute, isLoading,
  status, route,
}) {
  return (
    <div id="sidebar">
      <p className="eyebrow">Route Planner</p>
      <h1>GPS Router</h1>

      <div className="field">
        <label htmlFor="startAddress">Start</label>
        <input
          id="startAddress"
          type="text"
          placeholder="e.g. Columbus, OH"
          value={startAddress}
          onChange={(e) => setStartAddress(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="goalAddress">Destination</label>
        <input
          id="goalAddress"
          type="text"
          placeholder="e.g. Pittsburgh, PA"
          value={goalAddress}
          onChange={(e) => setGoalAddress(e.target.value)}
        />
      </div>

      <button onClick={onFindRoute} disabled={isLoading}>
        {isLoading ? "Finding route..." : "Find Route"}
      </button>

      {status && <div className={`status ${status.kind}`}>{status.message}</div>}

      {route && (
        <div className="readout visible">
          <div className="readout-cell">
            <div className="readout-value">{route.total_time.toFixed(0)}</div>
            <div className="readout-label">Minutes</div>
          </div>
          <div className="readout-cell">
            <div className="readout-value">{(route.total_distance / 1609.34).toFixed(1)}</div>
            <div className="readout-label">Miles</div>
          </div>
          <div className="readout-cell">
            <div className="readout-value">{route.path.length}</div>
            <div className="readout-label">Nodes</div>
          </div>
        </div>
      )}
    </div>
  );
}
