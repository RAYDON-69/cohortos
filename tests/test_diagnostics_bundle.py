from services.diagnostics import build_diagnostics_bundle, redact


def test_redact_phone_and_token():
    s = "user 01712345678 token Bearer abcdefghij.klmnopqrst.uvwxyz123456"
    out = redact(s)
    assert "01712345678" not in out
    assert "Bearer" not in out or "REDACTED" in out


def test_bundle_excludes_seeded_pii():
    phone = "01998887766"
    name = "SECRET_STUDENT_NAME_XYZ"
    token = "aaaabbbbccccddddeeee.ffffgggghhhhiiii.jjjjkkkkllllmmmm"
    logs = [f"attendance for {name} phone={phone} auth={token}"]
    blob = build_diagnostics_bundle(
        log_lines=logs,
        versions={"app": "0.11.0"},
        config={"jwt_secret": "SHOULD_NOT_APPEAR", "mode": "test"},
        integrity="ok",
        extra_secrets=[name],
    )
    # unzip and scan
    import zipfile, io
    zf = zipfile.ZipFile(io.BytesIO(blob))
    all_text = ""
    for n in zf.namelist():
        all_text += zf.read(n).decode(errors="ignore")
    assert phone not in all_text
    assert name not in all_text
    assert "SHOULD_NOT_APPEAR" not in all_text
    assert "jwt_secret" not in all_text
