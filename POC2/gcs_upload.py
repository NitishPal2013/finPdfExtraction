"""
Direct-to-GCS upload helpers for POC2.

Why this exists
---------------
Cloud Run has a hard **32 MiB HTTP request body limit** baked into the
Google Frontend (GFE) layer in front of every Cloud Run service. PDFs
larger than 32 MiB get rejected with a 413 *before* they reach the
Streamlit container — so `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` never gets a
chance to see them. The limit is not configurable.

The Google-recommended workaround is **direct-to-GCS upload**: the browser
uploads the file straight to a GCS bucket using a short-lived V4 signed
PUT URL, and the Cloud Run service then reads the object by name. The
file bytes never traverse Cloud Run, so the 32 MiB cap never applies.

   Browser ─── PUT 100+ MB ──▶ GCS bucket
                                   │
                                   ▼
                              Cloud Run reads by object name

One-time GCP setup
------------------
1. Create a regional GCS bucket (same region as your Cloud Run service):

       gsutil mb -l asia-south1 gs://YOUR-BUCKET-NAME

2. Grant the Cloud Run service account two roles. The first lets it
   read/write objects in the bucket; the second lets it sign URLs from
   inside Cloud Run (where the metadata-server credentials lack a
   private key, so `iam.signBlob` is the only signing path).

   Find your Cloud Run service account:

       gcloud run services describe YOUR-SERVICE \\
           --region=asia-south1 \\
           --format='value(spec.template.spec.serviceAccountName)'

   Then grant:

       gsutil iam ch \\
           serviceAccount:SA-EMAIL:objectAdmin \\
           gs://YOUR-BUCKET-NAME

       gcloud iam service-accounts add-iam-policy-binding SA-EMAIL \\
           --member=serviceAccount:SA-EMAIL \\
           --role=roles/iam.serviceAccountTokenCreator

3. Configure CORS so browsers on your Cloud Run domain can PUT to the
   bucket (without this you get a CORS error in the browser console
   before the upload even starts):

       cat > /tmp/cors.json <<'EOF'
       [{
         "origin": ["https://YOUR-SERVICE-HASH.asia-south1.run.app"],
         "method": ["PUT"],
         "responseHeader": ["Content-Type"],
         "maxAgeSeconds": 3600
       }]
       EOF
       gsutil cors set /tmp/cors.json gs://YOUR-BUCKET-NAME

4. Lifecycle rule — auto-delete uploads after 1 day. (GCS lifecycle's
   minimum age unit is 1 day; for finer granularity, run
   `delete_gcs_object()` from a Cloud Scheduler job.)

       cat > /tmp/lifecycle.json <<'EOF'
       {
         "lifecycle": {
           "rule": [{
             "action": {"type": "Delete"},
             "condition": {"age": 1, "matchesPrefix": ["uploads/"]}
           }]
         }
       }
       EOF
       gsutil lifecycle set /tmp/lifecycle.json gs://YOUR-BUCKET-NAME

5. Tell the Streamlit app which bucket to use:

       gcloud run services update YOUR-SERVICE \\
           --region=asia-south1 \\
           --set-env-vars=GCS_UPLOAD_BUCKET=YOUR-BUCKET-NAME

After step 5 the app picks up the bucket name automatically on its
next cold start.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Iterator

from google.auth import default as google_auth_default
from google.auth.transport import requests as auth_requests
from google.cloud import storage


_BUCKET_ENV_VAR = "GCS_UPLOAD_BUCKET"


def get_upload_bucket() -> str:
    """Return the configured GCS upload bucket name, or raise if missing."""
    name = os.environ.get(_BUCKET_ENV_VAR, "").strip()
    if not name:
        raise RuntimeError(
            f"Environment variable {_BUCKET_ENV_VAR} is not set. "
            "See POC2/gcs_upload.py for the required GCP setup."
        )
    return name


def _signing_credentials():
    """Get credentials that can sign V4 URLs from inside Cloud Run.

    The metadata-server credentials don't include a private key, so
    `generate_signed_url(version='v4')` without help would raise. Passing
    `service_account_email` + `access_token` to it routes the signing
    through the IAM `signBlob` API instead, which the service account is
    allowed to call on itself (provided we granted
    `roles/iam.serviceAccountTokenCreator` — see module docstring).
    """
    creds, _ = google_auth_default()
    creds.refresh(auth_requests.Request())
    return creds


def generate_signed_put_url(
    object_name: str,
    *,
    expires_in_minutes: int = 30,
    content_type: str = "application/pdf",
    bucket_name: str | None = None,
) -> str:
    """Generate a V4 signed PUT URL for direct-from-browser upload to GCS.

    The URL is single-purpose: it only allows writes to the exact
    `object_name`, it expires after `expires_in_minutes`, and the browser
    must send the matching `Content-Type` header on its PUT.
    """
    bucket_name = bucket_name or get_upload_bucket()
    blob = storage.Client().bucket(bucket_name).blob(object_name)
    creds = _signing_credentials()
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expires_in_minutes),
        method="PUT",
        content_type=content_type,
        service_account_email=creds.service_account_email,
        access_token=creds.token,
    )


def gcs_object_exists(
    object_name: str, *, bucket_name: str | None = None,
) -> bool:
    """True iff `object_name` currently exists in the bucket."""
    bucket_name = bucket_name or get_upload_bucket()
    client = storage.Client()
    return client.bucket(bucket_name).blob(object_name).exists(client=client)


def delete_gcs_object(
    object_name: str, *, bucket_name: str | None = None,
) -> None:
    """Best-effort delete. Silently no-ops if the object is already gone
    or if the network blip — we always have the lifecycle rule as backup."""
    bucket_name = bucket_name or get_upload_bucket()
    try:
        storage.Client().bucket(bucket_name).blob(object_name).delete()
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def gcs_pdf_to_temp(
    object_name: str, *, bucket_name: str | None = None,
) -> Iterator[Path]:
    """Download a GCS object to a tempfile, yield its Path, delete on exit.

    Mirror of POC2.paths.temp_pdf so the rest of the pipeline can swap
    upload sources without other changes.
    """
    bucket_name = bucket_name or get_upload_bucket()
    blob = storage.Client().bucket(bucket_name).blob(object_name)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.close()
        blob.download_to_filename(tmp.name)
        yield Path(tmp.name)
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass
