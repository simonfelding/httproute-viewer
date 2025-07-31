FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN mkdir -p static && wget https://unpkg.com/tailwindcss@^3/dist/tailwind.min.css -O static/tailwind.css
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]