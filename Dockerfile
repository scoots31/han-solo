FROM lettaai/letta:latest

USER root
RUN pip install psycopg2-binary --quiet

USER letta
