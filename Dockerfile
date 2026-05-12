FROM lettaai/letta:latest

USER root
RUN /app/.venv/bin/pip install psycopg2-binary --quiet

USER letta
