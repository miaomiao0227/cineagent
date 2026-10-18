FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /app
COPY configs/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt && pip check && pip freeze > /opt/requirements-resolved.txt
ENV PYTHONPATH=/workspace/src:/app TF_USE_LEGACY_KERAS=1 TF_NUM_INTRAOP_THREADS=4 TF_NUM_INTEROP_THREADS=2 OMP_NUM_THREADS=4
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
