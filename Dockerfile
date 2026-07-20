FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG LLM_PROVIDER=github
RUN if [ "$LLM_PROVIDER" = "anthropic" ] || [ "$LLM_PROVIDER" = "vertex" ]; then \
      pip install --no-cache-dir 'anthropic[vertex]>=0.39.0'; \
    fi

COPY app/ app/
COPY profiles/ profiles/

USER 1001

CMD ["python", "-m", "app.main"]
