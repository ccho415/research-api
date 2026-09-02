FROM python:3.13-slim

# pg_dump must be at least as new as the server it dumps, and the database is
# PostgreSQL 17.
#
# This used to add the PGDG apt repository, because the base image was Debian
# 12 (bookworm) whose default client is PostgreSQL 15. It is now Debian 13
# (trixie), which ships 17 - so the repository, the signing key, curl and gnupg
# are all unnecessary, and pinning the version keeps the guarantee.
#
# Removing it is not tidying. Fetching the PGDG key needs www.postgresql.org
# from inside Zeabur's builder, and that is what broke: `curl: (56) Recv
# failure: Connection timed out` after **1032 seconds**. A build that hangs
# seventeen minutes and then fails reads exactly like a slow build, and the old
# container keeps serving the whole time, so the deploy looks stuck rather than
# broken. This step is now the only one that needed the public internet.
#
# The version is pinned rather than left to the `postgresql-client` metapackage
# so that a future base image with an older default fails loudly here instead of
# silently installing a pg_dump too old to read the server.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates postgresql-client-17; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
