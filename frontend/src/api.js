// Change this if your API is running somewhere other than localhost:8000
export const API_BASE = "http://localhost:8000";

export async function findRoute(startAddress, goalAddress) {
  const response = await fetch(`${API_BASE}/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_address: startAddress, goal_address: goalAddress }),
  });

  if (!response.ok) {
    throw new Error(`Request failed: HTTP ${response.status}`);
  }

  const data = await response.json();
  if (data.error) {
    throw new Error(data.error);
  }

  return data;
}

export async function searchAddress(address) {
  const response = await fetch(`${API_BASE}/search`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
  });

  if (!response.ok) {
    throw new Error(`Request failed: HTTP ${response.status}`);
  }

  const data = await response.json();
  if (data.error) {
    throw new Error(data.error);
  }
  
  return data;
}