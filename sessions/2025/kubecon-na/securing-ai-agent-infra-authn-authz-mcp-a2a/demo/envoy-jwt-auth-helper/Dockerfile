# Build stage
FROM golang:1.22-alpine AS builder

RUN apk add --no-cache git ca-certificates

WORKDIR /build

# Copy go mod files first for better caching
COPY go.mod go.sum* ./
RUN go mod download || true

# Copy source code
COPY . .

# Tidy and download dependencies
RUN go mod tidy && go mod download

# Build the binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -o envoy-jwt-auth-helper \
    .

# Runtime stage
FROM alpine:3.19

RUN apk add --no-cache ca-certificates

# Create non-root user
RUN addgroup -g 1000 helper && \
    adduser -u 1000 -G helper -s /bin/sh -D helper

# Create config directory
RUN mkdir -p /opt/helper /run/auth-helper/config && \
    chown -R helper:helper /opt/helper /run/auth-helper

COPY --from=builder /build/envoy-jwt-auth-helper /opt/helper/envoy-jwt-auth-helper

USER helper

ENTRYPOINT ["/opt/helper/envoy-jwt-auth-helper"]
CMD ["-config", "/run/auth-helper/config/envoy-jwt-auth-helper.conf"]
