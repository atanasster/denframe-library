# Security policy

Use [private vulnerability reporting](https://github.com/atanasster/mantel-library/security/advisories/new)
for suspected archive-validation escapes, unsafe media processing, identity or signing
failures. Include the affected tool version, minimal reproduction and expected impact.
Do not disclose credentials, household records or a working exploit in a public issue.
Maintainers will investigate reports privately; no response deadline is promised.

The latest tagged format release is maintained. Upgrade after a security fix.
Assets are data, never executable extensions. Validation does not establish publisher
identity, rights or content accuracy. Do not run arbitrary commands supplied by an asset.
Repository CI runs untrusted contributions with a read-only default token, and no
`pull_request_target` workflow. Signing credentials do not belong in this repository.
