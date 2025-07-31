# Kubernetes HTTPRoute Viewer
A simple internal web application that lists all HTTPRoute resources within the Kubernetes cluster. It provides a quick, read-only view of the routes, their hostnames, and backend services.

## How it Works
- It's a Python web app using FastAPI.
- It uses the pod's ServiceAccount token to securely connect to the Kubernetes API.
- It fetches all gateway.networking.k8s.io/v1 HTTPRoute resources.
- The frontend is a single HTML page rendered with Jinja2 and styled with Tailwind CSS.