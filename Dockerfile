FROM python:3.12.11-slim
LABEL maintainer="Onestein"

# Install tools and build dependencies
RUN apt-get update && apt-get install -y curl libpq-dev gcc

# Install kubectl
RUN curl -L "https://dl.k8s.io/release/stable.txt" -o /tmp/k8s_version && \
    curl -LO "https://dl.k8s.io/release/$(cat /tmp/k8s_version)/bin/linux/amd64/kubectl" && \
    curl -LO "https://dl.k8s.io/release/$(cat /tmp/k8s_version)/bin/linux/amd64/kubectl.sha256" && \
    echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check && \
    rm -f kubectl.sha256 /tmp/k8s_version && \
    mv kubectl /usr/local/bin/ && \
    chmod +x /usr/local/bin/kubectl

# Install Argo CLI
RUN curl -sLO "https://github.com/argoproj/argo-workflows/releases/download/v3.7.2/argo-linux-amd64.gz" && \
    gunzip "argo-linux-amd64.gz" && \
    mv "argo-linux-amd64" /usr/local/bin/argo && \
    chmod +x /usr/local/bin/argo

# Copy app
COPY app /app
COPY log-config.yaml /app/log-config.yaml
COPY requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "--host", "0.0.0.0", "--log-config", "/app/log-config.yaml", "app.main:app"]
