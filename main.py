import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client, config

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_kubernetes_api():
    """
    Initializes and returns the Kubernetes API client.
    It tries to load in-cluster config first, and falls back to kubeconfig
    for local development.
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            raise Exception("Could not configure kubernetes client")
    return client.CustomObjectsApi()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Handles the main page request. It fetches HTTPRoutes and renders them
    in an HTML template.
    """
    api = get_kubernetes_api()
    try:
        # Gateway API group and version
        group = "gateway.networking.k8s.io"
        version = "v1"
        plural = "httproutes"

        # List all HTTPRoute resources in the cluster
        http_routes = api.list_cluster_custom_object(group, version, plural)

    except client.ApiException as e:
        # Handle cases where the CRD might not be installed
        if e.status == 404:
            http_routes = {"items": []}
        else:
            raise e

    # Get the hostname from the request
    hostname = request.headers.get("host")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "hostname": hostname,
            "http_routes": http_routes.get("items", []),
        },
    )