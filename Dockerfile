# Runs the complaint portal and API for hosting (Render, Railway, Fly.io or any Docker host).
#
# Build the Flutter web app first, so it is included under /app/ (optional):
#     cd flutter_app && flutter build web --base-href /app/ && cd ..
# Then build and run:
#     docker build -t chennai-complaints .
#     docker run -p 8000:8000 -v portal-data:/data chennai-complaints
#
# The database is kept in /data. Mount a persistent volume there, or data is lost on restart.

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    COMPLAINT_PORTAL_DB=/data/portal.db

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

EXPOSE 8000

# PORT is set by most hosts. The server reads it when no --port is given.
CMD ["python", "portal/server.py"]
