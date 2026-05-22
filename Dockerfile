FROM letta/letta:0.16.8

USER root
RUN /app/.venv/bin/pip install psycopg2-binary --quiet

USER letta
