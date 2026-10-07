# Install CohortOS on Linux Mint 22.3 (x86_64)

## From GitHub pre-release (recommended)

1. Open the **Release Linux** workflow artifact or the GitHub **Pre-release**.
2. Download `cohortos-linux-x86_64-<version>.tar.gz` and `SHA256SUMS`.
3. Verify and install:

```bash
sha256sum -c SHA256SUMS
mkdir -p ~/cohortos-release && tar -xzf cohortos-linux-x86_64-*.tar.gz -C ~/cohortos-release
cd ~/cohortos-release
bash install.sh
```

4. Start and open:

```bash
~/.local/bin/cohortos start --open
# or open http://127.0.0.1:8000
```

5. First centre (no SMS provider):

```bash
~/.local/bin/cohortos bootstrap 0171XXXXXXX "My Coaching Centre"
# Read OTP from ~/.local/share/cohortos/data/otp_latest.txt
# Enter the code in the browser
```

6. Backup:

```bash
~/.local/bin/cohortos backup
```

## Production notes

- `COHORTOS_ENV=production`, `COHORTOS_TEST_EXPOSE_OTP=0` (no API OTP leak).
- OTP without Twilio: `COHORTOS_LOCAL_OTP_FILE` (set by install.sh).
- Binds `127.0.0.1:8000` only.

## Uninstall

```bash
bash uninstall.sh          # keeps data
bash uninstall.sh --purge  # deletes data + config
```
