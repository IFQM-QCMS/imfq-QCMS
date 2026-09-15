# QCMS Enterprise Platform Architecture & Single Sign-On (SSO) Blueprint
**Document Version**: 2.0.0 (Enterprise Identity & Schema Specification)  
**System Name**: QCMS (Quality & Continuous Improvement Management System) / IFQM Platform  
**Target Audience**: Principal Architects, Security Engineers, DevOps, Enterprise IT Administrators  
**Status**: APPROVED FOR IMPLEMENTATION  
**Last Synchronized**: September 2026  

---

## Document Control & Metadata

| Metadata Field | Specification Details |
| :--- | :--- |
| **System Classification** | Enterprise Multi-Tenant Quality Operating System (8D / Six Sigma) |
| **Document Purpose** | Comprehensive Architecture Blueprint for Enterprise SSO Federation (SAML 2.0 / OIDC) & Relational Schema Mapping |
| **Primary Identity Providers** | Microsoft Entra ID (Azure AD), Google Workspace, Okta, Ping Identity, CyberArk, Active Directory (ADFS) |
| **Supported Protocols** | OpenID Connect (OIDC Core 1.0 with PKCE), SAML 2.0 Web Browser SSO Profile |
| **Tenant Isolation Model** | Shared Database, Shared Schema, Row-Level Isolation (`org_id` scoped) |
| **Compliance Alignment** | ISO 27001 (A.9 Access Control), SOC 2 Type II (CC6 Logical Access), GDPR |

---

## 1. Executive Summary & Enterprise Context

QCMS (Quality & Continuous Improvement Management System) is an enterprise SaaS platform engineered to digitize, automate, and enforce structured problem-solving methodologies—principally **8D (Eight Disciplines)** and **Six Sigma**. Large-scale manufacturing, automotive, aerospace, and electronics enterprises utilize QCMS as their central "Quality Operating System".

In an enterprise deployment, corporate IT security mandates that users **never** maintain disconnected local passwords. Authentication must be delegated to corporate Identity Providers (IdPs) via **Single Sign-On (SSO)**. This enforces:
1. **Centralized Access Governance**: Deactivating an employee in Microsoft Entra ID or Okta immediately revokes access to QCMS.
2. **Conditional Access & MFA**: QCMS inherits corporate multi-factor authentication, device compliance checks, and geo-fencing policies.
3. **Zero Credential Exposure**: No passwords transit or reside in the QCMS database for SSO accounts.
4. **Just-In-Time (JIT) Provisioning**: Automated account instantiation, plant assignment, department mapping, and role assignment upon first corporate login.

---

## 2. QCMS Software Architecture & Multi-Tenant Topology

### 2.1 Multi-Tenancy Architecture
QCMS employs a **Shared Database, Shared Schema, Row-Level Isolation** architectural pattern:
- **Tenant Context (`org_id`)**: Every organization is isolated by an integer `org_id` foreign key stamped across all core transactional entities (`users`, `departments`, `plants`, `projects`, `audit_logs`, `sops`).
- **Platform Separation**: Platform-level SuperAdmins operate across organizations or have `org_id = NULL` (or belong to a dedicated platform organization marked with `is_platform_org = True`).
- **Granular RBAC**: A strict 6-tier hierarchical permission model:
  1. `SuperAdmin` (Level 5): Platform owner, billing, global configurations, cross-tenant auditing.
  2. `Admin` (Level 4): Organization owner, manages users, departments, plants, and tenant SSO configurations.
  3. `Reviewer` (Level 3): Mandatory sign-off authority for critical quality stage transition gates (Stages 4, 5, 7, 8).
  4. `Facilitator` (Level 2): Technical RCA and 7 QC Tools validator.
  5. `Team Leader` (Level 1): Project manager, responsible for project execution and team coordination.
  6. `Team Member` (Level 0): Core contributor, responsible for data entry and action execution.
  7. `CEO`: Executive stakeholder with read-only visibility, stage sign-off, analytics, and audit oversight.

### 2.2 Complete Technology Stack
| Layer | Technology | Version / Spec | Role & Functionality |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | Vanilla ES6+ JavaScript, HTML5 | Modern ES2022 | High-performance Single Page Application (SPA) utilizing Single Page Component Injection (SPCI). No virtual-DOM framework overhead. |
| **Styling & Design System** | Tailwind CSS & Modern CSS3 | Custom Glassmorphism | Premium enterprise aesthetic with CSS custom variables, light/dark mode synchronization (`data-theme`), and responsive mobile/desktop layouts. |
| **API Gateway & Routing** | Flask | 3.1.3 (Python 3.10+) | Modular Blueprint-based REST API with 30+ dedicated route modules (`auth_routes.py`, `admin_routes.py`, `workflow_routes.py`, etc.). |
| **Authentication Engine** | `Flask-JWT-Extended` + `Flask-Bcrypt` | JWT Spec (RFC 7519) | Cryptographically signed, stateless JSON Web Tokens (JWT) containing user identity, role, org, session context, and sub-roles. |
| **Session & Cache Tier** | Redis | 5.0+ | Fast in-memory session presence tracking (`sess_status:{session_id}`, `user_active:{user_id}`), rate limiting, and OTP cooldowns. |
| **Relational Database** | PostgreSQL | 15+ (Neon Serverless) | Relational storage with strict foreign keys, indexing, JSONB attributes, and transactional ACID guarantees. |
| **Asynchronous Worker** | Celery + Redis Broker | 5.3+ | Background execution for notifications, PDF generation, analytics aggregation, and email dispatch. |
| **Vector Engine** | FAISS + pgvector | 0.2.4 | Semantic knowledge retrieval for historical quality problems and RAG AI. |

---


## 3. Relational Database Schema & Identity Map

The QCMS relational schema isolates tenant data while providing unified identity lookup. Below is the detailed schema dictionary for all tables involved in identity, session management, tenancy, and workflow integration:

### 3.1 Entity Relationship Data Dictionary

#### 1. `organizations` (Tenant Boundary)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY` | Unique Organization ID; primary tenant isolation key across the system. |
| `name` | `VARCHAR(255)` | `NOT NULL, INDEX` | Registered corporate name (e.g. "Tata Motors Ltd"). |
| `org_code` | `VARCHAR(100)` | `UNIQUE, NULLABLE` | Short enterprise tenant identifier used in SSO initiate endpoints. |
| `email` | `VARCHAR(255)` | `UNIQUE, NOT NULL` | Primary administrator email. |
| `subscription_plan` | `VARCHAR(50)` | `DEFAULT 'Trial'` | Subscription tier: 'Trial', 'Starter', 'Professional', 'Enterprise'. |
| `subscription_status`| `VARCHAR(20)` | `DEFAULT 'Trialing'` | Status: 'Trialing', 'Active', 'Suspended', 'Canceled'. |
| `login_options` | `JSON` | `DEFAULT ['email']` | Allowed login identifiers for this tenant (e.g. `["email", "employee_id"]`). |
| `security_settings` | `JSON` | `NULLABLE` | Tenant-level policies: password rules, session timeout, role permissions. |
| `is_platform_org` | `BOOLEAN` | `DEFAULT FALSE` | Flag identifying internal platform management org (SuperAdmin). |
| `is_deleted` | `BOOLEAN` | `DEFAULT FALSE, INDEX`| Soft-delete flag; deleted organizations block all user authentications. |

#### 2. `roles` (RBAC Hierarchy)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY` | Unique Role ID. |
| `name` | `VARCHAR(50)` | `UNIQUE, NOT NULL` | Canonical role name: 'SuperAdmin', 'Admin', 'Reviewer', 'Facilitator', 'Team Leader', 'Team Member'. |
| `description` | `VARCHAR(255)` | `NULLABLE` | Scope and responsibility description. |

#### 3. `plants` & `departments` (Organizational Hierarchy)
| Table | Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `plants` | `id` | `INTEGER` | `PRIMARY KEY` | Physical plant or facility location ID. |
| `plants` | `org_id` | `INTEGER` | `FK -> organizations.id, NOT NULL` | Tenant ownership boundary. |
| `plants` | `name` | `VARCHAR(100)`| `NOT NULL` | Facility name (e.g. "Pune Manufacturing Plant 1"). |
| `plants` | `code` | `VARCHAR(50)` | `NULLABLE` | Facility short code (e.g. "PUN-01"). |
| `departments`| `id` | `INTEGER` | `PRIMARY KEY` | Operational department ID. |
| `departments`| `org_id` | `INTEGER` | `FK -> organizations.id, NOT NULL` | Tenant ownership boundary. |
| `departments`| `plant_id` | `INTEGER` | `FK -> plants.id, NULLABLE` | Optional association to physical plant facility. |
| `departments`| `name` | `VARCHAR(100)`| `NOT NULL` | Department name (e.g. "Quality Assurance", "Assembly"). |

#### 4. `users` (Identity Container)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY` | Unique User ID; mapped to JWT token `sub` claim. |
| `org_id` | `INTEGER` | `FK -> organizations.id, INDEX` | Tenant reference. NULL for platform SuperAdmins. |
| `plant_id` | `INTEGER` | `FK -> plants.id, NULLABLE` | Assigned plant/facility. |
| `department_id` | `INTEGER` | `FK -> departments.id, NULLABLE` | Assigned operational department. |
| `role_id` | `INTEGER` | `FK -> roles.id, NOT NULL` | Primary RBAC classification. |
| `username` | `VARCHAR(100)` | `UNIQUE, NOT NULL, INDEX` | Unique login username handle. |
| `email` | `VARCHAR(255)` | `UNIQUE, INDEX, NULLABLE` | Primary corporate email; principal anchor for SSO matching. |
| `employee_id` | `VARCHAR(100)` | `INDEX, NULLABLE` | Corporate badge/employee ID. |
| `hashed_password` | `VARCHAR(255)` | `NOT NULL` | Bcrypt password hash. Set to unusable randomized hash for SSO accounts. |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE, INDEX` | Account active state. False blocks login immediately. |
| `is_verified` | `BOOLEAN` | `DEFAULT FALSE` | Email verification status. Pre-verified for SSO users. |
| `status` | `VARCHAR(20)` | `DEFAULT 'Active', INDEX` | Lifecycle state: 'Active', 'Inactive', 'Suspended'. |
| `sso_provider_id` | `INTEGER` | `FK -> sso_providers.id` | Reference to federated IdP provider configuration. |
| `sso_subject_id` | `VARCHAR(255)` | `INDEX, NULLABLE` | Immutable unique identifier passed by IdP (`sub` in OIDC, `NameID` in SAML). |
| `sso_enforced` | `BOOLEAN` | `DEFAULT FALSE` | When True, native password login is completely blocked. |
| `custom_fields` | `JSON` | `NULLABLE` | Custom attributes: phone, badges, super_admin_role, language. |

#### 5. `saas_user_sessions` (Active Presence & Concurrency)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `session_id` | `VARCHAR(100)` | `PRIMARY KEY` | Unique session handle (e.g. `SESS-1726384200-42`). Stored in JWT claims. |
| `user_id` | `INTEGER` | `FK -> users.id, NOT NULL` | Owning user reference. |
| `org_id` | `INTEGER` | `FK -> organizations.id, NULLABLE` | Tenant reference. |
| `device` / `browser` / `os` | `VARCHAR(50)` | `NULLABLE` | Parsed User-Agent environment fingerprint. |
| `ip_address` | `VARCHAR(45)` | `NULLABLE` | Real client IPv4/IPv6 address. |
| `location` | `VARCHAR(100)` | `NULLABLE` | Geo-IP resolution (City, Country). |
| `status` | `VARCHAR(20)` | `DEFAULT 'Active'` | Session state: 'Active', 'LoggedOut', 'Terminated', 'Expired'. |
| `login_time` / `last_activity` | `DATETIME` | `DEFAULT UTC_NOW` | Timestamps for idle timeout and session duration calculation. |

#### 6. `sso_providers` (Proposed Model for Enterprise Federation)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY` | Unique SSO Provider record ID. |
| `org_id` | `INTEGER` | `FK -> organizations.id, NULLABLE` | Owning tenant. NULL indicates platform-wide SSO default. |
| `provider_name` | `VARCHAR(100)` | `NOT NULL` | Descriptive name (e.g. "Tata Motors Azure AD", "Bosch Okta SSO"). |
| `protocol` | `VARCHAR(20)` | `NOT NULL DEFAULT 'OIDC'`| Federation protocol: 'OIDC' or 'SAML'. |
| `provider_type` | `VARCHAR(50)` | `NOT NULL` | Provider archetype: 'azure_ad', 'google', 'okta', 'ping', 'generic_saml'. |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Master enable/disable toggle. |
| `enforce_sso` | `BOOLEAN` | `DEFAULT FALSE` | If True, password login is disabled for users with mapped domains. |
| `allowed_domains` | `JSONB` | `DEFAULT '[]'` | List of corporate domains (e.g. `["tatamotors.com", "tata.com"]`). |
| `client_id` / `client_secret` | `VARCHAR` | `NULLABLE` | OIDC credentials (secret stored encrypted). |
| `idp_entity_id` / `idp_sso_url`| `VARCHAR(500)`| `NULLABLE` | SAML 2.0 Issuer URI and Single Sign-On HTTP-POST / Redirect URL. |
| `idp_x509_cert` | `TEXT` | `NULLABLE` | Public X.509 certificate for validating SAML XML assertion signatures. |
| `attribute_mapping` | `JSONB` | `NULLABLE` | Rules mapping IdP assertion claims to QCMS fields (email, name, role, dept, plant). |
| `default_role_id` | `INTEGER` | `FK -> roles.id` | Fallback role for JIT auto-provisioned users (defaults to Team Member). |
| `auto_provision_users` | `BOOLEAN` | `DEFAULT TRUE` | Enables Just-In-Time user creation on first successful SSO login. |

---

## 4. Current Authentication System & SSO Gap Analysis

### 4.1 Current Local Authentication Execution Flow
1. **Identifier Discovery (`GET /api/auth/login-config?identifier=user@domain.com`)**:
   - The frontend calls this endpoint to determine if the user's organization has custom login options (e.g., employee ID) and inspects `PlatformSettings.authentication_settings`.
2. **Credential Authentication (`POST /api/auth/login`)**:
   - The user submits `{ identifier, password }`.
   - The backend checks brute-force locks via `record_failed_login(identifier)` in `app/presentation/middleware/security.py`.
   - The password is authenticated using `bcrypt.check_password_hash()`.
   - If verified, a unique session token is created (`session_id = SESS-{timestamp}-{user.id}`) and logged in `SaaSUserSession`.
   - A stateless JWT is minted with claims:
     ```json
     {
       "identity": "42",
       "session_id": "SESS-1726384200-42",
       "org_id": 14,
       "role": "Team Leader",
       "dept_id": 3,
       "sa_sub_role": null,
       "exp": 1726470600
     }
     ```
   - Redis session presence is cached (`sess_status:{session_id} = "Active"`).
   - Cookies and JSON response are dispatched to the browser.

### 4.2 Gap Analysis of Earlier SSO Stub
In `backend/app/presentation/routes/auth_routes.py` (lines 2205–2312), a commented-out endpoint `/api/auth/sso/<provider>` existed. A rigorous architectural review reveals critical security and functional deficiencies that prevented its production release:
1. **Zero Cryptographic Proof**: The endpoint accepted raw client-supplied JSON `{ email, token }` and authenticated the user based solely on the email address without verifying the signature of the token or validating it against the IdP's JSON Web Key Set (JWKS).
2. **Missing SAML Engine**: No capability to parse, decrypt, or verify XML Digital Signatures (`ds:Signature`) against IdP X.509 public certificates.
3. **No Multi-Tenant Routing**: The endpoint assumed a single global IdP and lacked the ability to match an email domain (e.g., `@acme.com`) to a specific enterprise customer's dedicated Azure AD tenant.
4. **No JIT Attribute Mapping**: Failed to extract and synchronize corporate organizational attributes (plants, departments, roles, employee badges) from incoming IdP assertions.

---

## 5. Enterprise SSO Target Architecture (OIDC & SAML 2.0)

To fulfill enterprise requirements, QCMS implements a **Dual-Level SSO Federation Architecture**:
1. **Platform-Wide SSO (Internal SuperAdmins)**:
   - Dedicated federation with the QCMS corporate Identity Provider (e.g., IFQM Google Workspace or Microsoft Entra ID).
   - Authenticated users receive `SuperAdmin` role privileges with `org_id = NULL`.
2. **Tenant-Specific Enterprise SSO (B2B Customers)**:
   - Each enterprise tenant configures their own corporate IdP inside `sso_providers`.
   - Domain-based routing auto-routes employees entering `@tatamotors.com` to Tata's corporate Entra ID, while `@bosch.com` routes to Bosch's Okta SAML 2.0 endpoint.

### Protocol Comparison for QCMS Integration
| Architectural Criterion | OpenID Connect (OIDC) | SAML 2.0 Web Browser SSO |
| :--- | :--- | :--- |
| **Primary Target IdPs** | Microsoft Entra ID, Google Workspace, AWS Cognito | Okta, Ping Identity, CyberArk, Active Directory (ADFS) |
| **Token Payload Format** | JSON Web Token (JWT / JWS / JWE) | XML Document with `ds:Signature` & `<saml:Assertion>` |
| **Transport Binding** | HTTP Redirect + Back-channel HTTP POST | HTTP-Redirect (AuthnRequest) + HTTP-POST (SAMLResponse) |
| **Security Validation** | Asymmetric RSA (RS256) via live JWKS endpoint | Public X.509 Certificate verification of XML digest |
| **PKCE Support** | Yes (Mandatory Proof Key for Code Exchange) | N/A (Secured via RelayState & InResponseTo correlation) |
| **JIT Provisioning** | Standardized ID Token claims (`email`, `name`, `sub`) | SAML `<AttributeStatement>` attribute mapping |

---


## 6. OpenID Connect (OIDC) / Azure AD / Google Flow Deep-Dive

The OpenID Connect flow implements the **Authorization Code Grant with Proof Key for Code Exchange (PKCE)** to prevent authorization code interception attacks:

1. **Client Domain Resolution**:
   - The user inputs their email address (e.g. `john@acme.com`).
   - The frontend calls `GET /api/auth/login-config?email=john@acme.com`.
   - The backend checks `sso_providers` for a matching domain (`acme.com`).
   - Returns SSO provider details and initiates the flow.
2. **Initiating Authorization (`GET /api/auth/sso/oidc/login/<provider_id>`)**:
   - The backend generates a cryptographically random `code_verifier` (43–128 characters) and hashes it with SHA-256 to create the `code_challenge`.
   - A unique `state` and `nonce` are generated and cached in Redis with a 10-minute TTL.
   - The browser is redirected (HTTP 302) to the IdP's `/authorize` endpoint with parameters:
     ```text
     https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?
       client_id={CLIENT_ID}&
       response_type=code&
       redirect_uri=https://qcms.company.com/api/auth/sso/oidc/callback&
       response_mode=query&
       scope=openid profile email&
       state={RANDOM_STATE}&
       nonce={RANDOM_NONCE}&
       code_challenge={CODE_CHALLENGE}&
       code_challenge_method=S256
     ```
3. **IdP Authentication & MFA**:
   - The user authenticates against Microsoft Entra ID or Google Workspace, satisfying all corporate Conditional Access and Multi-Factor Authentication requirements.
4. **Callback & Back-Channel Token Exchange (`POST /api/auth/sso/oidc/callback`)**:
   - The IdP redirects to QCMS with `?code=AUTH_CODE&state=STATE`.
   - The backend validates `state` against Redis.
   - The backend directly calls the IdP's `/token` endpoint over TLS (back-channel), passing `code` and the plaintext `code_verifier`.
   - The IdP responds with the signed `id_token` (JWT) and `access_token`.
5. **Cryptographic Validation & Claim Extraction**:
   - The backend retrieves the IdP's public signing keys from its `jwks_uri` (cached in Redis for 24h).
   - Validates:
     1. Signature matches the published key ID (`kid`).
     2. Issuer (`iss`) matches the expected IdP authority.
     3. Audience (`aud`) matches the QCMS registered `client_id`.
     4. Expiration (`exp`) is strictly in the future.
     5. Nonce (`nonce`) matches the initial session request.
   - Extracts claims: `email`, `name`, `sub` (immutable IdP user ID), `groups` / `roles`.
6. **JIT Execution & QCMS Token Generation**:
   - The JIT engine provisions or updates the user in `users`.
   - Creates a new active session in `saas_user_sessions` and Redis.
   - Mints the QCMS JWT access token and returns it to the client.

---

## 7. SAML 2.0 Enterprise Federation Flow Deep-Dive

For organizations utilizing **Okta**, **Ping Identity**, **CyberArk**, or on-premises **ADFS**, QCMS operates as a certified SAML 2.0 Service Provider (SP):

1. **Service Provider Metadata (`GET /api/auth/sso/saml/metadata/<provider_id>`)**:
   - QCMS publishes standard SAML XML metadata containing its `EntityID`, `AssertionConsumerService` (ACS) endpoint, and public X.509 signing certificate.
2. **Generating AuthnRequest (`GET /api/auth/sso/saml/login/<provider_id>`)**:
   - QCMS generates a `<samlp:AuthnRequest>` XML document:
     ```xml
     <samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
         ID="QCMS_REQ_5b2d8e4..." Version="2.0"
         IssueInstant="2026-09-15T08:30:00Z"
         Destination="https://okta.acme.com/app/qcms/sso/saml"
         AssertionConsumerServiceURL="https://qcms.company.com/api/auth/sso/saml/acs/14">
       <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
         https://qcms.company.com/sp/saml/metadata
       </saml:Issuer>
       <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>
     </samlp:AuthnRequest>
     ```
   - The request is deflated, base64-encoded, signed using QCMS's private key, and dispatched via HTTP Redirect.
3. **IdP Processing & Response**:
   - The IdP authenticates the employee and generates a signed `<samlp:Response>` containing a `<saml:Assertion>`.
   - The assertion is submitted via an automated browser HTTP-POST to the QCMS ACS URL.
4. **ACS Verification (`POST /api/auth/sso/saml/acs/<provider_id>`)**:
   - The backend validates:
     1. XML Digital Signature using the pre-configured `idp_x509_cert`.
     2. `NotBefore` and `NotOnOrAfter` timestamp constraints (allowing a 300s clock skew tolerance).
     3. `AudienceRestriction` matches the QCMS SP Entity ID.
     4. `InResponseTo` correlates to an active pending request.
   - Extracts attributes from `<saml:AttributeStatement>`:
     - `NameID` -> `sso_subject_id`
     - `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress` -> `email`
     - `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name` -> `full_name`
     - `http://schemas.microsoft.com/ws/2008/06/identity/claims/role` -> `role`
     - `department`, `plant`, `employeeId`

---

## 8. Multi-Tenant Domain Routing & Just-In-Time (JIT) Provisioning Engine

### 8.1 Domain Routing Logic
1. When a user enters `rohit.verma@tatamotors.com`, the domain `tatamotors.com` is extracted.
2. The query checks:
   ```sql
   SELECT * FROM sso_providers 
   WHERE allowed_domains ? 'tatamotors.com' 
     AND is_active = TRUE;
   ```
3. If found and `enforce_sso = TRUE`, password authentication is blocked and the user is routed to Tata's corporate IdP.

### 8.2 Just-In-Time (JIT) User Provisioning Algorithm
```python
def execute_jit_provisioning(provider, identity_claims):
    email = identity_claims['email'].strip().lower()
    subject_id = str(identity_claims['sub'])
    org_id = provider.org_id
    
    # 1. Lookup existing user by SSO Subject ID or Email
    user = User.query.filter(
        (User.sso_subject_id == subject_id) | 
        (db.func.lower(User.email) == email)
    ).first()
    
    # 2. Extract mapped attributes
    full_name = identity_claims.get('name') or email.split('@')[0]
    idp_roles = identity_claims.get('roles', [])
    idp_dept  = identity_claims.get('department')
    idp_plant = identity_claims.get('plant')
    
    # 3. Resolve Plant and Department within Tenant
    plant_obj = None
    if idp_plant and org_id:
        plant_obj = Plant.query.filter(
            Plant.org_id == org_id,
            db.or_(Plant.name.ilike(idp_plant), Plant.code.ilike(idp_plant))
        ).first()
        
    dept_obj = None
    if idp_dept and org_id:
        dept_obj = Department.query.filter(
            Department.org_id == org_id,
            Department.name.ilike(idp_dept)
        ).first()
        
    # 4. Resolve Role from IdP group mapping or fallback to default
    assigned_role_id = provider.default_role_id
    if idp_roles:
        mapping = provider.attribute_mapping.get('role_map', {})
        for r in idp_roles:
            if r in mapping:
                target_role = Role.query.filter_by(name=mapping[r]).first()
                if target_role:
                    assigned_role_id = target_role.id
                    break

    # 5. Create or Update User Record
    if not user:
        if not provider.auto_provision_users:
            raise PermissionError("Auto-provisioning is disabled for this organization.")
            
        username = email.split('@')[0]
        base_user = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_user}{counter}"
            counter += 1
            
        user = User(
            org_id=org_id,
            plant_id=plant_obj.id if plant_obj else None,
            department_id=dept_obj.id if dept_obj else None,
            username=username,
            full_name=full_name,
            email=email,
            role_id=assigned_role_id,
            hashed_password=bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode('utf-8'),
            is_active=True,
            is_verified=True,
            status='Active',
            sso_provider_id=provider.id,
            sso_subject_id=subject_id,
            sso_enforced=provider.enforce_sso
        )
        db.session.add(user)
    else:
        # Sync existing user
        user.sso_provider_id = provider.id
        user.sso_subject_id = subject_id
        user.full_name = full_name
        if plant_obj: user.plant_id = plant_obj.id
        if dept_obj:  user.department_id = dept_obj.id
        user.is_verified = True
        
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return user
```

---

## 9. Database Schema Enhancements & DDL Migration Script

Execute the following SQL migration against PostgreSQL / Neon DB to instantiate the SSO federation layer:

```sql
-- ==============================================================================
-- QCMS ENTERPRISE SSO SCHEMA MIGRATION SCRIPT (v2.0)
-- ==============================================================================

-- 1. Create SSO Providers Table
CREATE TABLE IF NOT EXISTS sso_providers (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    provider_name VARCHAR(100) NOT NULL,
    protocol VARCHAR(20) NOT NULL DEFAULT 'OIDC', -- 'OIDC' or 'SAML'
    provider_type VARCHAR(50) NOT NULL,            -- 'azure_ad', 'google', 'okta', 'ping', 'generic_saml'
    is_active BOOLEAN DEFAULT TRUE,
    is_platform_default BOOLEAN DEFAULT FALSE,
    enforce_sso BOOLEAN DEFAULT FALSE,
    allowed_domains JSONB DEFAULT '[]'::jsonb,
    
    -- OIDC Credentials & Endpoints
    client_id VARCHAR(255),
    client_secret_encrypted TEXT,
    discovery_url VARCHAR(500),
    auth_endpoint VARCHAR(500),
    token_endpoint VARCHAR(500),
    userinfo_endpoint VARCHAR(500),
    jwks_uri VARCHAR(500),
    
    -- SAML 2.0 Endpoints & Certificates
    idp_entity_id VARCHAR(500),
    idp_sso_url VARCHAR(500),
    idp_slo_url VARCHAR(500),
    idp_x509_cert TEXT,
    sp_entity_id VARCHAR(500),
    sp_acs_url VARCHAR(500),
    
    -- JIT Provisioning Rules
    attribute_mapping JSONB DEFAULT '{
        "email": "email",
        "full_name": "name",
        "employee_id": "employeeId",
        "department": "department",
        "plant": "physicalDeliveryOfficeName",
        "role_map": {
            "QCMS-Admins": "Admin",
            "QCMS-Reviewers": "Reviewer",
            "QCMS-Facilitators": "Facilitator",
            "QCMS-TeamLeaders": "Team Leader",
            "QCMS-Users": "Team Member"
        }
    }'::jsonb,
    default_role_id INTEGER REFERENCES roles(id),
    auto_provision_users BOOLEAN DEFAULT TRUE,
    sync_profile_on_login BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_sso_providers_org ON sso_providers(org_id);
CREATE INDEX IF NOT EXISTS idx_sso_providers_protocol ON sso_providers(protocol);
CREATE INDEX IF NOT EXISTS idx_sso_providers_domains ON sso_providers USING gin(allowed_domains);

-- 2. Enhance Users Table with SSO Fields
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_provider_id INTEGER REFERENCES sso_providers(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_subject_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_enforced BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_users_sso_sub ON users(sso_subject_id);
CREATE INDEX IF NOT EXISTS idx_users_sso_provider ON users(sso_provider_id);

-- 3. Enhance PlatformSettings Table with Global SSO Fallback
UPDATE platform_settings
SET authentication_settings = COALESCE(authentication_settings, '{}'::jsonb) || '{
    "sso_global_enabled": true,
    "sso_allow_jit": true,
    "default_sso_protocol": "OIDC",
    "jwt_expiry_hours": 24
}'::jsonb
WHERE id = 1;
```

---

## 10. Frontend Integration (`auth.js` & `login.html`)

### 10.1 Real-Time SSO Button Injection
When the user types their email into the login input, the frontend dynamically presents corporate SSO options:

```javascript
// Dynamic SSO Provider Detection in frontend/assets/js/auth.js
const emailInput = document.getElementById('username');
const ssoContainer = document.getElementById('ssoButtonsContainer');

emailInput?.addEventListener('blur', async () => {
    const val = emailInput.value.trim();
    if (!val.includes('@')) return;

    try {
        const res = await fetch(`/api/auth/login-config?identifier=${encodeURIComponent(val)}`);
        const data = await res.json();
        
        if (data.sso_config && data.sso_config.enforce_sso) {
            // Hide password fields and show corporate SSO button
            document.getElementById('passwordContainer').style.display = 'none';
            document.getElementById('loginBtn').style.display = 'none';
            
            ssoContainer.innerHTML = `
                <button type="button" onclick="initiateCorporateSSO('${data.sso_config.provider_id}')"
                    class="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold transition">
                    <svg width="20" height="20" viewBox="0 0 23 23">
                        <path fill="#f35325" d="M1 1h10v10H1z"/>
                        <path fill="#81bc06" d="M12 1h10v10H12z"/>
                        <path fill="#05a6f0" d="M1 12h10v10H1z"/>
                        <path fill="#ffba08" d="M12 12h10v10H12z"/>
                    </svg>
                    Sign in with ${data.sso_config.provider_name || 'Corporate SSO'}
                </button>
            `;
            ssoContainer.style.display = 'block';
        }
    } catch (e) {
        console.warn('SSO configuration query failed:', e);
    }
});

function initiateCorporateSSO(providerId) {
    window.location.href = `/api/auth/sso/initiate?provider_id=${providerId}`;
}
```

---

## 11. Enterprise Identity Provider Configuration Playbooks

### 11.1 Microsoft Entra ID (Azure AD) Setup
1. Log in to **Microsoft Entra Admin Center** (`entra.microsoft.com`).
2. Navigate to **Applications** > **App registrations** > **New registration**.
   - **Name**: `QCMS Enterprise Quality System`
   - **Supported account types**: `Accounts in this organizational directory only` (Single tenant)
   - **Redirect URI**: Web -> `https://qcms.company.com/api/auth/sso/oidc/callback`
3. Under **Certificates & secrets**, generate a new **Client secret** (Record Value).
4. Under **API permissions**, verify `openid`, `profile`, `email` permissions are granted.
5. Under **Token configuration**, add Optional Claims: `family_name`, `given_name`, `upn`, `groups`.
6. Record `Application (client) ID`, `Directory (tenant) ID`, and Client Secret into the QCMS `sso_providers` table.

### 11.2 Okta SAML 2.0 Setup
1. In the **Okta Admin Console**, go to **Applications** > **Create App Integration** > **SAML 2.0**.
2. **General Settings**: App name: `QCMS Quality Management System`.
3. **SAML Settings**:
   - **Single Sign-On URL**: `https://qcms.company.com/api/auth/sso/saml/acs/{org_id}`
   - **Audience URI (SP Entity ID)**: `https://qcms.company.com/sp/saml/metadata`
   - **Name ID format**: `EmailAddress`
   - **Application username**: `Email`
4. **Attribute Statements**:
   - `email` -> `user.email`
   - `name` -> `user.displayName`
   - `department` -> `user.department`
   - `plant` -> `user.city`
5. Download Okta's **X.509 Certificate** and paste it into `sso_providers.idp_x509_cert`.

---

## 12. Security, Hardening & Compliance Standards

1. **Cryptographic Validation**:
   - Mandatory verification of OIDC ID token signatures against live HTTPS JWKS endpoints.
   - Enforce SHA-256 or SHA-512 for SAML signatures; reject deprecated SHA-1.
2. **Replay & Timestamp Protection**:
   - All SAML assertions must validate `InResponseTo` correlation and reject timestamps older than 300 seconds.
   - OIDC nonces must be single-use and invalidated immediately from Redis.
3. **Session Revocation & Single Logout (SLO)**:
   - When a session is terminated via IdP SLO, QCMS invalidates `SaaSUserSession` and removes the Redis session key (`sess_status:{session_id}`).
4. **ISO 27001 & SOC 2 Compliance**:
   - All SSO authentication events, provisioning actions, and signature failures are written to `audit_logs` with timestamp, client IP, User-Agent, and detailed diagnostic context.

---
**END OF BLUEPRINT**
