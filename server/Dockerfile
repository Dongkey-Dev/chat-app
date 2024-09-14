FROM python:3.12-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ./server/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ./server /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]