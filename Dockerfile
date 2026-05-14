FROM python:3.11-slim
WORKDIR /app

# Install curl for Docker healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir -i http://mirrors.cloud.aliyuncs.com/pypi/simple/ --trusted-host mirrors.cloud.aliyuncs.com ".[web]"
RUN mkdir -p /app/data /app/data_backup

# Entrypoint: restore from persistent backup, start backup loop, launch app
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
ENV PYTHONUNBUFFERED=1

CMD ["/entrypoint.sh"]
