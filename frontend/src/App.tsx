import { useEffect, useState } from "react";

type Health = {
  status: string;
  database: { connected: boolean; extensions: string[]; missing: string[] };
  config: Record<string, string>;
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640 }}>
      <h1>Documentation Intelligence</h1>
      <p style={{ color: "#666" }}>STEP 1 — skeleton. Chat, search and viewer land in STEP 6.</p>
      {error && <pre style={{ color: "crimson" }}>{error}</pre>}
      {health && <pre>{JSON.stringify(health, null, 2)}</pre>}
    </main>
  );
}
