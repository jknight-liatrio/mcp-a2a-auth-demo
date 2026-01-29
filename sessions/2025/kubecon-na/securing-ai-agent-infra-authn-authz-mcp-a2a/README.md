
# Securing AI Agent Infrastructure: AuthN/AuthZ Patterns for MCP and A2A — Minimal Demo Assets

This folder contains the **essential, reproducible assets** for the KubeCon NA 2025 session demo.
The focus is on **Envoy external authorization (ext_authz)** patterns for:
- **Inbound**: UMA decision delegation to Keycloak.
- **Outbound**: RFC 8693 **Token Exchange** for downstream services.
- **MCP**: Proper `WWW-Authenticate: Bearer resource_metadata=...` challenges and a simple MCP response path.

---

## Directory Layout

```
sessions/2025/kubecon-na/securing-ai-agent-infra-authn-authz-mcp-a2a/
├── README.md                    # this file
└── demo/
    ├── envoy-jwt-auth-helper/   # ext_authz helper (Go)
    │   ├── main.go
    │   └── pkg/auth/ext_auth_server.go
    ├── config/
    │   ├── keycloak.yaml        # demo Keycloak manifests
    │   └── demo-realm.template.json  # example realm
    └── k8s/
        ├── frontend/
        │   ├── frontend-deployment.yaml
        │   └── config/
        │       ├── envoy.yaml
        │       ├── envoy-jwt-auth-helper1.conf   # inbound (UMA decision)
        │       ├── envoy-jwt-auth-helper2.conf   # outbound (token exchange)
        │       └── proxy.conf                    # nginx: /.well-known + /mcp proxy
        └── backend/
            ├── backend-deployment.yaml
            └── config/
                ├── envoy.yaml
                ├── envoy-jwt-auth-helper.conf    # inbound decision helper for backend
                ├── backend-mcp.conf              # nginx: serve mcp.json with application/mcp+json
                └── mcp.json
```

## Prerequisites

- Kubernetes cluster (kind or minikube recommended).
- Docker CLI (or compatible build tool).
- SPIRE (SPIFFE) quickstart applied separately (SDS used by Envoy). Obtain from upstream.
- Keycloak 26.x (container image) for UMA and token operations.

> SPIRE examples: https://github.com/spiffe/spire-examples
> Envoy docs: https://www.envoyproxy.io/
> Keycloak: https://www.keycloak.org/

---

## Configuration

- **Keycloak token endpoint**: set in `envoy-jwt-auth-helper*.conf` files (`keycloak_token_endpoint`).
- **SPIFFE IDs**: examples use `spiffe://example.org/...`. Replace with your own IDs where required.
- **SPIRE Workload socket**: `unix:///run/spire/sockets/agent.sock` (adjust if your agent differs).
- **Downstream audience**:
  - Inbound decision mode: `envoy-jwt-auth-helper1.conf` (frontend) and backend helper conf.
  - Outbound token exchange: `envoy-jwt-auth-helper2.conf` (frontend) expects the backend audience.

---

## Quick Start with Kind

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) (Kubernetes in Docker)
- [Tilt](https://docs.tilt.dev/install.html) for local development
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (optional, for running the test client)

### 1. Create a Kind Cluster

```bash
kind create cluster --name mcp-demo
```

Or use the default cluster name (also supported by the Tiltfile):

```bash
kind create cluster  # Creates default 'kind' cluster
```

### 2. Configure Local DNS

Add the following entry to your `/etc/hosts` file to resolve `keycloak.local`:

```bash
# Get the kind node IP
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' mcp-demo-control-plane

# Add to /etc/hosts (replace IP with the output above)
echo "172.18.0.3 keycloak.local" | sudo tee -a /etc/hosts
```

This allows the OAuth client to reach Keycloak via the ingress NodePort.

### 3. Deploy with Tilt

Navigate to the demo directory and start Tilt:

```bash
cd demo
tilt up
```

Tilt will:
- Build the `envoy-jwt-auth-helper` Docker image
- Load the image into the kind cluster
- Deploy all Kubernetes resources via kustomize
- Set up port forwards:
  - **Ingress**: `localhost:30080` → Keycloak and services
  - **Frontend**: `localhost:3000` → Frontend service

Press `space` to open the Tilt UI in your browser, or visit http://localhost:10350.

### 4. Wait for Services to Start

Monitor the Tilt UI until all resources are green. The startup order is:

```
SPIRE (spire-server → spire-agent)
         ↓
Infrastructure (postgres → keycloak)
         ↓
Applications (backend → frontend)
```

Keycloak may take 1-2 minutes to fully initialize on first startup.

### 5. Test the Full Auth Flow

Run the OAuth test client to verify the complete authentication flow:

```bash
cd demo
uv run oauth_client.py
```

This script will:
1. Dynamically register an OAuth client with Keycloak
2. Open a browser for user authentication (login: `joek` / `password`)
3. Complete the OAuth 2.0 Authorization Code Flow with PKCE
4. Call the MCP endpoint through the frontend → backend chain
5. Display the MCP response

Expected output on success:
```
[MCP] Status: 200
[MCP] Response:
{
  "jsonrpc": "2.0",
  "id": "req-profile_1",
  "result": { ... }
}
```

### 6. Access Services

- **Keycloak Admin Console**: http://keycloak.local:30080 (admin/admin)
- **Frontend via Ingress**: http://keycloak.local:30080/frontend/
- **Tilt Dashboard**: http://localhost:10350

---

## Tilt Development Workflow

The Tiltfile provides a streamlined development experience with automatic rebuilds and hot reloading.

### Tilt Configuration

The Tiltfile (`demo/Tiltfile`) configures:

| Resource | Labels | Port Forwards | Dependencies |
|----------|--------|---------------|--------------|
| `spire-server` | spire | - | - |
| `spire-agent` | spire | - | spire-server |
| `postgres` | infra | - | spire-agent |
| `keycloak` | infra | - | postgres, spire-agent, ingress-nginx |
| `ingress-nginx` | infra | 30080:80 | - |
| `backend` | app | - | keycloak, spire-agent, ingress-nginx |
| `frontend` | app | 3000:3000 | backend, keycloak, spire-agent, ingress-nginx |

### Allowed Kubernetes Contexts

The Tiltfile only allows deployment to these contexts:
- `kind-kind` (default kind cluster)
- `kind-mcp-demo` (named cluster)

### Live Updates

The `envoy-jwt-auth-helper` image supports live updates:
- Go source files are synced to the container
- Automatic rebuild triggered on `*.go` file changes
- No need to restart Tilt for code changes

### Watched Files

Tilt automatically redeploys when these files change:
- `k8s/backend/config/*` - Backend Envoy and auth-helper configs
- `k8s/frontend/config/*` - Frontend Envoy and auth-helper configs
- `config/*` - Keycloak realm and infrastructure configs
- `k8s/ingress-nginx/config/*` - Ingress configuration

### Useful Tilt Commands

```bash
# Start Tilt (foreground)
tilt up

# Start Tilt and open UI
tilt up --stream

# Trigger manual rebuild of a resource
tilt trigger frontend

# View logs for a specific resource
tilt logs frontend

# Tear down all resources
tilt down
```

---

## Manual Deployment (without Tilt)

### 1. Build and Load the Docker Image

```bash
cd demo/envoy-jwt-auth-helper
docker build -t envoy-jwt-auth-helper:latest .
kind load docker-image envoy-jwt-auth-helper:latest --name mcp-demo
```

### 2. Deploy with Kustomize

```bash
cd demo
kubectl apply -k .
```

### 3. Port Forward Services

```bash
kubectl port-forward svc/keycloak 8080:8080 &
kubectl port-forward svc/frontend 3000:3000 &
```

---

## Architecture

### SPIRE Integration

The demo uses [SPIRE](https://spiffe.io/docs/latest/spire-about/) for workload identity:

- **Trust Domain**: `example.org`
- **SPIRE Server**: Deployed as a StatefulSet in the `spire` namespace
- **SPIRE Agent**: Deployed as a DaemonSet on each node
- **Workload Attestation**: Uses Kubernetes Projected Service Account Tokens (PSAT)

Workloads receive SPIFFE Verifiable Identity Documents (SVIDs) for mutual TLS and JWT-based authentication.

### Envoy JWT Auth Helper

A Go-based external authorization service that integrates with Envoy and SPIRE:

- **Token Validation**: Validates incoming JWTs against Keycloak
- **Token Exchange**: Performs OAuth 2.0 token exchange using SPIFFE JWTs
- **UMA Authorization**: Integrates with Keycloak's User-Managed Access for fine-grained permissions

Configuration modes:
- `access_token_validator_with_decision`: Validates tokens and makes authorization decisions
- `access_token_exchanger`: Exchanges tokens for downstream service calls

### Keycloak Configuration

Keycloak is configured with:
- SPIFFE trust bundle for verifying workload JWTs
- UMA 2.0 support for resource-based authorization
- OAuth 2.0 token exchange enabled

The SPIRE CA certificate is mounted from the `spire-server-ca` ConfigMap.

---

## Troubleshooting

### Check SPIRE Status

```bash
# Verify SPIRE server is running
kubectl get pods -n spire

# Check SPIRE server logs
kubectl logs -n spire spire-server-0

# Verify agent is connected
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server agent list
```

### Check Workload SVIDs

```bash
# List registered workloads
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show
```

### Verify Keycloak

```bash
# Check Keycloak logs
kubectl logs -l app=keycloak

# Verify SPIRE CA is mounted
kubectl exec deployment/keycloak -- ls -la /opt/keycloak/conf/truststores/
```

### Architecture Diagrams

For detailed request flow and container architecture diagrams, see [docs/architecture-diagrams.md](docs/architecture-diagrams.md).

### Common Issues

1. **SPIRE Agent not connecting**: Ensure the cluster name in SPIRE server config matches your k8s cluster

2. **Keycloak startup failure**: Verify the `spire-server-ca-chain.pem` contains a valid PEM certificate

3. **Token validation errors**: Check that workloads have valid SPIRE registrations

4. **"Token was issued too far in the past"**: Keycloak rejects SPIFFE JWTs with `iat` claims older than 300 seconds. The SPIRE server's `default_jwt_svid_ttl` is set to `120s` to ensure the agent refreshes JWTs frequently enough.

5. **"Invalid identity" from backend UMA decision**: The backend uses `hostNetwork: true` but cannot resolve `keycloak.local`. Ensure the backend auth-helper config uses the internal Keycloak URL (`http://keycloak:8080/...`).

6. **Timeout errors during token exchange**: The Envoy `ext_authz` timeout is set to 30 seconds. If you see timeouts, check Keycloak logs for slow responses.

7. **404 on /mcp endpoint**: Ensure the backend nginx config has `server_name localhost` to match incoming requests with `Host: localhost`.

8. **OAuth client cannot reach Keycloak**: Verify `keycloak.local` is in your `/etc/hosts` pointing to the kind node IP.

### Debugging Commands

```bash
# Check frontend auth-helper logs (token exchange)
kubectl logs -l app=frontend -c auth-helper --tail=50

# Check backend auth-helper logs (UMA decision)
kubectl logs -l app=backend -c auth-helper --tail=50

# Check Envoy access logs
kubectl exec deploy/frontend -c envoy -- cat /tmp/inbound-proxy.log | tail -20

# Decode a JWT token (replace <token>)
echo "<token>" | cut -d. -f2 | base64 -d 2>/dev/null | jq .

# Verify SPIRE workload registrations
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show

# Check SPIRE agent health
kubectl exec -n spire -l app=spire-agent -- /opt/spire/bin/spire-agent healthcheck
```
