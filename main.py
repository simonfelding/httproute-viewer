import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client, config
from cachetools import cached, TTLCache

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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
def get_prepared_routes_and_urls():
    """
    Fetches HTTPRoutes, processes them to include internal URLs, and returns
    both the processed routes and a set of valid URLs for checking.
    This entire operation is cached.
    """
    print("CACHE MISS: Fetching and preparing routes from Kubernetes API...")
    api = get_kubernetes_api()
    try:
        group = "gateway.networking.k8s.io"
        version = "v1"
        plural = "httproutes"
        http_routes = api.list_cluster_custom_object(group, version, plural)
    except client.ApiException as e:
        if e.status == 404:
            http_routes = {"items": []}
        else:
            raise e

    route_items = http_routes.get("items", [])
    allowed_urls = set()

    for route in route_items:
        route_namespace = route["metadata"]["namespace"]
        for rule in route.get("spec", {}).get("rules", []):
            for backend in rule.get("backendRefs", []):
                service_name = backend.get("name")
                service_port = backend.get("port")
                service_namespace = backend.get("namespace", route_namespace)

                if service_name and service_port:
                    internal_url = f"http://{service_name}.{service_namespace}:{service_port}"
                    backend["internal_url"] = internal_url
                    allowed_urls.add(internal_url)

    return route_items, allowed_urls


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Handles the main page request using the cached and processed data."""

    processed_routes, _ = get_prepared_routes_and_urls()

    sorted_routes = sorted(processed_routes, key=lambda r: r['metadata']['name'])
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
    Checks an internal URL's status, using the cached set of allowed URLs
    for validation.
    """
    # We only need the set of allowed URLs here, so we ignore the first value.
    _, allowed_internal_urls = get_prepared_routes_and_urls()

    if url not in allowed_internal_urls:
        raise HTTPException(
            status_code=400,
            detail=f"URL '{url}' is not a valid backend defined in any HTTPRoute."
        )

    timeout = httpx.Timeout(5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            return JSONResponse({"status_code": response.status_code, "url": url})
    except httpx.RequestError as e:
        return JSONResponse({"status_code": 503, "error": str(e), "url": url}, status_code=503)