FROM cineagent-base:local
COPY configs/backend-extra.lock.txt /tmp/backend-extra.lock.txt
RUN pip install --no-cache-dir -r /tmp/backend-extra.lock.txt && pip check
