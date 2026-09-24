FROM rust@sha256:64232e656c058f4468e8d024e990acff04f0fd5a5c0a88a574dc37773d7325c9 AS build

WORKDIR /src
COPY Cargo.toml ./
RUN mkdir src && printf 'fn main() {}\n' > src/main.rs && cargo build --release
COPY src ./src
COPY static ./static
RUN touch src/main.rs && cargo build --release
RUN cargo test --release

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app \
    && mkdir -p /data \
    && chown app:app /data

COPY --from=build /src/target/release/laya-dataset-manager /usr/local/bin/laya-dataset-manager
USER app
ENV APP_DATABASE_URL=/data/laya-dataset-manager.db \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080
EXPOSE 8080
ENTRYPOINT ["laya-dataset-manager"]
