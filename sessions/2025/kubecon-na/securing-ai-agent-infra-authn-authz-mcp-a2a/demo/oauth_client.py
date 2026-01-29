#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "cryptography",
#     "pyjwt",
# ]
# ///
"""
OAuth 2.0 Authorization Code Flow with PKCE and Client Assertion

This script implements:
- Dynamic client registration with private_key_jwt authentication
- RSA keypair generation for client assertion signing
- PKCE (Proof Key for Code Exchange) with S256 challenge method
- Authorization code grant type
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# Configuration
CALLBACK_PORT = 8888
CONFIG = {
    "issuer": "http://keycloak.local:30080/realms/demo",
    "token_endpoint": "http://keycloak.local:30080/realms/demo/protocol/openid-connect/token",
    "authorization_endpoint": "http://keycloak.local:30080/realms/demo/protocol/openid-connect/auth",
    "registration_endpoint": "http://keycloak.local:30080/realms/demo/clients-registrations/openid-connect",
    "redirect_uri": f"http://localhost:{CALLBACK_PORT}/callback",
    "client_name": "Python OAuth Client",
    "scopes": ["openid", "mcp"],
}


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture the OAuth callback with authorization code."""
    
    authorization_code: Optional[str] = None
    received_state: Optional[str] = None
    error: Optional[str] = None
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if "code" in params:
            CallbackHandler.authorization_code = params["code"][0]
            CallbackHandler.received_state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization successful!</h1>")
            self.wfile.write(b"<p>You can close this window.</p></body></html>")
        elif "error" in params:
            CallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Error: {CallbackHandler.error}</h1></body></html>".encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logging


def generate_rsa_keypair():
    """Generate an RSA keypair for client assertion signing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    return private_key


def get_jwks_from_public_key(private_key, kid: str) -> dict:
    """Extract JWKS from RSA public key for client registration."""
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()
    
    # Convert to base64url encoding (no padding)
    def int_to_base64url(n: int, length: int) -> str:
        data = n.to_bytes(length, byteorder="big")
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    
    # RSA modulus (n) - 256 bytes for 2048-bit key
    n = int_to_base64url(public_numbers.n, 256)
    # RSA exponent (e) - 3 bytes for 65537
    e = int_to_base64url(public_numbers.e, 3)
    
    return {
        "keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": n,
            "e": e,
        }]
    }


def register_client(registration_endpoint: str, client_name: str, redirect_uri: str, jwks: dict) -> dict:
    """Register a new OAuth client with Keycloak using private_key_jwt authentication."""
    data = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": "private_key_jwt",
        "jwks": jwks,
    }
    
    response = requests.post(
        registration_endpoint,
        json=data,
        headers={"Content-Type": "application/json"},
    )
    
    response.raise_for_status()
    return response.json()


def create_client_assertion(client_id: str, token_endpoint: str, private_key, kid: str) -> str:
    """Create a signed JWT client assertion for private_key_jwt authentication."""
    now = int(time.time())
    
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "exp": now + 300,
        "iat": now,
        "jti": secrets.token_hex(16),
    }
    
    # Get PEM-encoded private key for PyJWT
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})


def generate_code_verifier() -> str:
    """Generate a cryptographically random code verifier for PKCE."""
    return secrets.token_urlsafe(32)


def generate_code_challenge(verifier: str) -> str:
    """Generate S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str,
    state: str,
) -> str:
    """Build the authorization URL with PKCE parameters."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(
    token_endpoint: str,
    client_id: str,
    authorization_code: str,
    redirect_uri: str,
    code_verifier: str,
    client_assertion: str,
) -> dict:
    """Exchange authorization code for tokens using client assertion."""
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion,
    }
    
    response = requests.post(
        token_endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    
    return response.json()


def main():
    """Run the OAuth 2.0 authorization code flow with PKCE and client assertion."""
    print("=" * 60)
    print("OAuth 2.0 Authorization Code Flow")
    print("with PKCE and Client Assertion (private_key_jwt)")
    print("=" * 60)
    
    # Step 1: Generate RSA keypair
    print("\n[Keypair] Generating RSA keypair...")
    private_key = generate_rsa_keypair()
    kid = f"key-{secrets.token_hex(4)}"
    jwks = get_jwks_from_public_key(private_key, kid)
    print(f"[Keypair] Generated key with kid: {kid}")
    
    # Step 2: Register client with Keycloak
    print("\n[Registration] Registering client with Keycloak...")
    try:
        registration = register_client(
            CONFIG["registration_endpoint"],
            CONFIG["client_name"],
            CONFIG["redirect_uri"],
            jwks,
        )
        client_id = registration["client_id"]
        print(f"[Registration] Client registered with ID: {client_id}")
    except requests.HTTPError as e:
        print(f"[Error] Client registration failed: {e}")
        print(f"[Error] Response: {e.response.text}")
        return
    
    # Step 3: Generate PKCE values
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)
    
    print(f"\n[PKCE] Code Verifier: {code_verifier}")
    print(f"[PKCE] Code Challenge: {code_challenge}")
    print(f"[State] {state}")
    
    # Step 4: Build authorization URL
    auth_url = build_authorization_url(
        CONFIG["authorization_endpoint"],
        client_id,
        CONFIG["redirect_uri"],
        CONFIG["scopes"],
        code_challenge,
        state,
    )
    
    print(f"\n[Auth URL] {auth_url}")
    
    # Start callback server
    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    print(f"\n[Server] Callback server listening on http://localhost:{CALLBACK_PORT}/callback")
    
    # Open browser for user authentication
    print("[Browser] Opening browser for authentication...")
    webbrowser.open(auth_url)
    
    # Wait for callback
    print("[Waiting] Waiting for authorization callback...")
    CallbackHandler.authorization_code = None
    CallbackHandler.error = None
    while CallbackHandler.authorization_code is None and CallbackHandler.error is None:
        server.handle_request()
    
    server.server_close()
    
    if CallbackHandler.error:
        print(f"\n[Error] Authorization failed: {CallbackHandler.error}")
        return
    
    authorization_code = CallbackHandler.authorization_code
    print(f"\n[Code] Received authorization code: {authorization_code[:20]}...")
    
    # Verify state
    if CallbackHandler.received_state != state:
        print("[Error] State mismatch! Possible CSRF attack.")
        return
    print("[State] State verified successfully")
    
    # Step 5: Create client assertion and exchange code for tokens
    print("\n[Assertion] Creating client assertion JWT...")
    client_assertion = create_client_assertion(
        client_id,
        CONFIG["token_endpoint"],
        private_key,
        kid,
    )
    print(f"[Assertion] JWT created (first 50 chars): {client_assertion[:50]}...")
    
    print("\n[Token] Exchanging authorization code for tokens...")
    token_response = exchange_code_for_tokens(
        CONFIG["token_endpoint"],
        client_id,
        authorization_code,
        CONFIG["redirect_uri"],
        code_verifier,
        client_assertion,
    )
    
    if "error" in token_response:
        print(f"\n[Error] Token exchange failed:")
        print(json.dumps(token_response, indent=2))
        return
    
    print("\n" + "=" * 60)
    print("TOKEN RESPONSE")
    print("=" * 60)
    print(json.dumps(token_response, indent=2))
    
    # Decode and display the access token claims (for debugging)
    if "access_token" in token_response:
        print("\n" + "=" * 60)
        print("ACCESS TOKEN CLAIMS (decoded, unverified)")
        print("=" * 60)
        try:
            # Decode JWT payload (second part) without verification
            payload_b64 = token_response["access_token"].split(".")[1]
            # Add padding if needed
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            print(json.dumps(claims, indent=2))
        except Exception as e:
            print(f"Could not decode access token: {e}")
        
        # Print access token for use
        print("\n" + "=" * 60)
        print("ACCESS TOKEN")
        print("=" * 60)
        access_token = token_response["access_token"]
        print(access_token)
        
        # Step 6: Call MCP endpoint with bearer token
        print("\n" + "=" * 60)
        print("CALLING MCP ENDPOINT")
        print("=" * 60)
        mcp_request = {
            "jsonrpc": "2.0",
            "id": "req-profile_1",
            "method": "resources/read",
            "params": {"uri": "resource://profiles/profile_1"}
        }
        
        mcp_response = requests.post(
            "http://localhost:3000/mcp",
            json=mcp_request,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "mcp-session": "xyz",
            },
        )
        
        print(f"[MCP] Status: {mcp_response.status_code}")
        print(f"[MCP] Response:")
        try:
            print(json.dumps(mcp_response.json(), indent=2))
        except Exception:
            print(mcp_response.text)


if __name__ == "__main__":
    main()
