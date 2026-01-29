# Architecture Diagrams

## Request Flow Diagram

The following diagram shows the flow of an authenticated request from the OAuth client through the ingress to the backend MCP endpoint:

```mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant Ingress as Ingress NGINX<br/>(NodePort 30080)
    participant FE_Envoy as Frontend Envoy<br/>(port 9001)
    participant FE_Auth1 as Frontend Auth-Helper 1<br/>(UMA Decision)
    participant FE_Auth2 as Frontend Auth-Helper 2<br/>(Token Exchange)
    participant FE_NGINX as Frontend NGINX<br/>(Proxy)
    participant BE_Envoy as Backend Envoy<br/>(port 9001)
    participant BE_Auth as Backend Auth-Helper<br/>(UMA Decision)
    participant BE_NGINX as Backend NGINX<br/>(/mcp endpoint)
    participant KC as Keycloak
    participant SPIRE as SPIRE Agent

    Note over Client,KC: 1. User Authentication (OAuth 2.0 + PKCE)
    Client->>KC: Authorization Code Flow
    KC-->>Client: Access Token (aud: frontend)

    Note over Client,BE_NGINX: 2. MCP Request Flow
    Client->>Ingress: POST /frontend/mcp<br/>Authorization: Bearer <token>
    Ingress->>FE_Envoy: Route to frontend (mTLS via SPIFFE)
    
    Note over FE_Envoy,KC: 3. Frontend Inbound Auth (ext_authz #1)
    FE_Envoy->>FE_Auth1: ext_authz Check
    FE_Auth1->>KC: UMA Decision Request<br/>(permission: /mcp#post)
    KC-->>FE_Auth1: {"result": true}
    FE_Auth1-->>FE_Envoy: ALLOW

    Note over FE_Envoy,SPIRE: 4. Token Exchange (ext_authz #2)
    FE_Envoy->>FE_Auth2: ext_authz Check
    FE_Auth2->>SPIRE: Fetch JWT-SVID<br/>(aud: realm URL)
    SPIRE-->>FE_Auth2: SPIFFE JWT
    FE_Auth2->>KC: RFC 8693 Token Exchange<br/>+ SPIFFE client assertion
    KC-->>FE_Auth2: New Access Token<br/>(aud: backend)
    FE_Auth2-->>FE_Envoy: ALLOW + Rewrite Auth Header

    Note over FE_Envoy,BE_NGINX: 5. Backend Request
    FE_Envoy->>FE_NGINX: Forward request
    FE_NGINX->>BE_Envoy: Proxy to backend (mTLS via SPIFFE)
    
    Note over BE_Envoy,KC: 6. Backend Auth (ext_authz)
    BE_Envoy->>BE_Auth: ext_authz Check
    BE_Auth->>KC: UMA Decision Request<br/>(permission: /mcp#post)
    KC-->>BE_Auth: {"result": true}
    BE_Auth-->>BE_Envoy: ALLOW

    BE_Envoy->>BE_NGINX: Forward to app
    BE_NGINX-->>BE_Envoy: MCP Response (mcp.json)
    BE_Envoy-->>FE_NGINX: Response
    FE_NGINX-->>FE_Envoy: Response
    FE_Envoy-->>Ingress: Response
    Ingress-->>Client: 200 OK + MCP JSON
```

## Container Architecture

```mermaid
graph TB
    subgraph "Client Machine"
        OC[OAuth Client<br/>oauth_client.py]
    end

    subgraph "Kind Cluster"
        subgraph "ingress-nginx namespace"
            ING[Ingress NGINX<br/>NodePort 30080]
        end

        subgraph "default namespace"
            subgraph "Frontend Pod"
                FE_E[Envoy Sidecar<br/>:9001]
                FE_A1[Auth-Helper 1<br/>:9020<br/>UMA Decision]
                FE_A2[Auth-Helper 2<br/>:9021<br/>Token Exchange]
                FE_N[NGINX Proxy<br/>:80]
            end

            subgraph "Backend Pod"
                BE_E[Envoy Sidecar<br/>:9001]
                BE_A[Auth-Helper<br/>:9010<br/>UMA Decision]
                BE_N[NGINX App<br/>:80<br/>/mcp endpoint]
            end

            KC[Keycloak<br/>:8080]
            PG[PostgreSQL<br/>:5432]
        end

        subgraph "spire namespace"
            SS[SPIRE Server<br/>:8081, :8443]
            SA[SPIRE Agent<br/>DaemonSet]
        end
    end

    OC -->|"POST /frontend/mcp"| ING
    ING -->|"mTLS"| FE_E
    FE_E <-->|"ext_authz"| FE_A1
    FE_E <-->|"ext_authz"| FE_A2
    FE_E --> FE_N
    FE_N -->|"mTLS"| BE_E
    BE_E <-->|"ext_authz"| BE_A
    BE_E --> BE_N

    FE_A1 -->|"UMA"| KC
    FE_A2 -->|"Token Exchange"| KC
    BE_A -->|"UMA"| KC
    KC --> PG

    FE_A2 <-->|"Workload API"| SA
    SA <--> SS

    style FE_E fill:#e1f5fe
    style BE_E fill:#e1f5fe
    style FE_A1 fill:#fff3e0
    style FE_A2 fill:#fff3e0
    style BE_A fill:#fff3e0
    style KC fill:#f3e5f5
    style SS fill:#e8f5e9
    style SA fill:#e8f5e9
```

### Legend

| Color | Component Type |
|-------|---------------|
| Blue (#e1f5fe) | Envoy Proxy |
| Orange (#fff3e0) | Auth-Helper |
| Purple (#f3e5f5) | Keycloak |
| Green (#e8f5e9) | SPIRE |
