# Serialized Asset Trust Policy

Pickle, joblib, PyTorch, and similar model files can execute code while loading. A matching checksum proves file identity, not safety.

1. Obtain assets only from the upstream project release or an approved internal store over authenticated transport.
2. Record upstream URL, release/tag, license, retrieval date, and expected SHA256 in an adjacent manifest before use.
3. Verify `assets/checksums.sha256` with `python 08_runtime/environment_check.py --verify-assets`.
4. Load only an approved checksum in an isolated, least-privilege environment without secrets or write access to source data.
5. Treat checksum changes as a new asset review. Never overwrite an existing checksum to silence a mismatch.

The current checksum list inventories local files but does not establish their upstream provenance. Until source provenance is completed, all listed serialized assets remain research-only and untrusted. Large external assets are ignored by Git; checksum and JSON manifest files are the governed records.
