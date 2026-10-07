# Verify CohortOS without GitHub Actions

Proof is local and portable. Paid Actions minutes are not required.

## Option A — Docker (any 4GB+ machine)

```bash
git clone -b wip/r57-backup <repo-url> cohortos && cd cohortos
docker build -f Dockerfile.verify -t cohortos-verify .
docker run --rm -e COHORTOS_JWT_SECRET=local-verify-secret-not-for-prod32 cohortos-verify
```

Proves: unit, skip-budget, stress, chaos, route inventory, boot/backup, gate logic; npm if image has enough RAM.

## Option B — Codespaces / Dev Container

Open the repo in VS Code Dev Containers or GitHub Codespaces.  
`postCreate` installs deps; run:

```bash
bash scripts/final_verify.sh --low-mem
```

## Option C — GitLab free CI

Push a mirror and enable CI; `.gitlab-ci.yml` runs unit + stress + npm_build with no `allow_failure`.

## Option D — Laptop / self-hosted

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export COHORTOS_ENV=test COHORTOS_JWT_SECRET=local-secret-not-for-prod-32chars
export COHORTOS_TEST_EXPOSE_OTP=1 COHORTOS_SKIP_MODEL_DOWNLOAD=1
bash scripts/final_verify.sh --low-mem
```

Resume a single gate: `bash scripts/final_verify.sh --only unit`

Results land in `~/work/results/<gate>.json` and `verification-report.md`.
