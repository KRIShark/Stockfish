ARG ARCH=x86-64-sse41-popcnt
FROM ubuntu:24.04 AS builder
ARG ARCH

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential ca-certificates wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY src ./src
COPY scripts ./scripts

RUN make -C src net && \
    make -C src -j$(nproc) ARCH=${ARCH} all && \
    strip src/stockfish

FROM ubuntu:24.04 AS runtime
ARG ARCH

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /workspace/src/stockfish /usr/local/bin/stockfish

WORKDIR /workspace
ENTRYPOINT ["sleep", "infinity"]
