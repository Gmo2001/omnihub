# Import Side Effects Report

## Summary
The following modules execute potential side-effect code (network calls, file reads, authentication) immediately upon import. This violates the "Safe Import" principle and causes issues in CI/CD and build steps.

## Detected Side Effects

### 1. `app/core/gcp_clients.py`
- **Line 9-16**: `firebase_admin.initialize_app(...)` is called at module level.
  - **Reason**: Condition `if not firebase_admin._apps:` executes on import.
  - **Side Effect**: Attempts to read `GOOGLE_APPLICATION_CREDENTIALS` file and establish connection to Firebase/GCP.
- **Line 18**: `db = firestore.client()`
  - **Reason**: Global variable initialization.
  - **Side Effect**: Establishes Firestore gRPC connection. Fails if creds missing.
- **Line 28 (inside get_drive_service)**: `service_account.Credentials.from_service_account_file(...)`
  - Note: This is inside a function, so it's safer, but `get_drive_service` usage needs checking.

### 2. `app/services/drive_service.py`
- **Line 11**: `from app.core.gcp_clients import db`
  - **Side Effect**: Triggers `app/core/gcp_clients.py` execution.
- **Line 97 (inside stream_file_to_gcs)**: `storage.Client.from_service_account_json(...)`
  - Note: Inside function, safe from import side-effect, but function call triggers file read.

## Planned Remediation (STEP 2)
1. **Lazy Initialization**: Wrap `db` and `firebase_admin` init in a `get_db()` function or `Lifespan` event.
2. **Dependency Injection**: Pass `db` client to services instead of importing global `db`.
