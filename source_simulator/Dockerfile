FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin simulator
COPY source_simulator /app/source_simulator
USER simulator
CMD ["uvicorn", "source_simulator.persistent_app:app", "--host", "0.0.0.0", "--port", "8099"]
