/* Single place to point the frontend at your backend.
   - Local dev (backend running on your machine): leave as-is.
   - Docker / deployed: set to your backend's public URL, e.g. "https://api.yourdomain.com"
     or "" (empty string) if the frontend is served behind an nginx proxy that
     forwards /api to the backend on the same origin. */
window.MPESA_API_BASE = "http://localhost:8000";
