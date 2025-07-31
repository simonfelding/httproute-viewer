import os
import httpx
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client, config
from cachetools import cached, TTLCache

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Caching ---
# Create a cache that holds 1 item and expires after 5 seconds.
# This ensures we don't spam the Kubernetes API on every check.
api_cache = TTLCache(maxsize=1, ttl=5)

def get_kubernetes_api():
    """Initializes and returns the Kubernetes API client."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            raise Exception("Could not configure kubernetes client")
    return client.CustomObjectsApi()

@cached(api_cache)
def get_http_routes():
    """
    Fetches all HTTPRoute resources from the cluster.
    The result is cached for 60 seconds to improve performance.
    """
    print("CACHE MISS: Fetching HTTPRoutes from Kubernetes API...")
    api = get_kubernetes_api()
    try:
        group = "gateway.networking.k8s.io"
        version = "v1"
        plural = "httproutes"
        return api.list_cluster_custom_object(group, version, plural)
    except client.ApiException as e:
        # If the CRD isn't found, return an empty list.
        if e.status == 404:
            return {"items": []}
        raise e

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Handles the main page request, using a cached list of routes."""
    http_routes = get_http_routes()
    route_items = http_routes.get("items", [])
    sorted_routes = sorted(route_items, key=lambda r: r['metadata']['name'])
    hostname = request.headers.get("host")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "hostname": hostname,
            "http_routes": sorted_routes,
        },
    )

@app.get("/api/check-status")
async def check_status(url: str):
    """
    Checks the status of a URL, but only if its hostname is present in an
    HTTPRoute resource.
    """
    # 1. Get all allowed hostnames from the cached list of routes
    http_routes = get_http_routes()
    allowed_hostnames = set()
    for route in http_routes.get("items", []):
        for hostname in route.get("spec", {}).get("hostnames", []):
            allowed_hostnames.add(hostname)

    # 2. Validate the requested URL
    try:
        parsed_url = urlparse(url)
        if not parsed_url.hostname or not parsed_url.scheme:
             raise HTTPException(status_code=400, detail="Invalid URL format provided.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Could not parse the provided URL.")

    if parsed_url.hostname not in allowed_hostnames:
        raise HTTPException(
            status_code=400,
            detail=f"Hostname '{parsed_url.hostname}' not found in any HTTPRoute resource."
        )

    # 3. If valid, proceed with the accessibility check
    timeout = httpx.Timeout(5.0)
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            return JSONResponse({"status_code": response.status_code})
    except httpx.RequestError as e:
        return JSONResponse({"status_code": 503, "error": str(e)}, status_code=503)