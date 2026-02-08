'use client';

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function Home() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [dbCheck, setDbCheck] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      const healthUrl = `${API_BASE}/health`;
      const dbCheckUrl = `${API_BASE}/db-check`;
      try {
        const [hRes, dRes] = await Promise.all([
          fetch(healthUrl),
          fetch(dbCheckUrl),
        ]);
        setHealth(await hRes.json());
        setDbCheck(await dRes.json());
        setFetchError(null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setFetchError(`Fetch failed: ${msg}. Check CORS and that the API is reachable at ${API_BASE}.`);
        setHealth({ error: msg });
        setDbCheck({ error: msg });
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  return (
    <main>
      <h1>Traffic-lyt Phase 0 ✅</h1>
      <p>NYC-first traffic/parking violations analytics — local stack.</p>
      <p style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: '#94a3b8' }}>
        API base: <code>{API_BASE}</code>
      </p>

      {fetchError && (
        <div className="status err" style={{ marginTop: '1rem' }}>
          <div className="label">Error</div>
          <div className="pre"><pre>{fetchError}</pre></div>
        </div>
      )}

      {loading ? (
        <p style={{ marginTop: '1rem' }}>Loading API checks…</p>
      ) : (
        <>
          <div className="status ok" style={{ marginTop: '1.5rem' }}>
            <div className="label">GET /health</div>
            <div className="pre">
              <pre>{JSON.stringify(health, null, 2)}</pre>
            </div>
          </div>
          <div
            className={
              dbCheck && 'db' in dbCheck && dbCheck.db === 'ok'
                ? 'status ok'
                : 'status err'
            }
            style={{ marginTop: '1rem' }}
          >
            <div className="label">GET /db-check</div>
            <div className="pre">
              <pre>{JSON.stringify(dbCheck, null, 2)}</pre>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
