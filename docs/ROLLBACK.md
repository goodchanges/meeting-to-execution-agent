# Rollback

Keep a known-good image tagged with its git SHA. Rehearse expand-only migrations before release. If readiness fails, capture the image tag and request ID, stop ingress and verify the pre-migration snapshot exists.

For staging with the matching schema head, run `bash scripts/rollback.sh PREVIOUS_GIT_SHA HTTPS_PUBLIC_URL` with the existing Compose project and credentials. The script starts the prior image and polls readiness. Verify login and existing decisions afterward.

An older image requires its own Alembic head to report ready. If the deployment advanced the head, use a compatible forward fix or restore the pre-migration snapshot into a fresh path with writers stopped. A snapshot rollback can lose newer writes. Reconcile externally created issues before retrying tasks.

Docker rollback not tested locally.
