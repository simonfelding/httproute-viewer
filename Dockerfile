FROM alpine:latest AS builder
RUN apk add --no-cache curl && curl -Lo tailwind.css https://unpkg.com/tailwindcss@^3/dist/tailwind.min.css

FROM python:3.13-alpine AS main

WORKDIR /app
COPY requirements.txt .

COPY --from=builder /tailwind.css static/tailwind.css
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]