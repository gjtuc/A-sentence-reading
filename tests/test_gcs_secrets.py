"""Runtime secrets stay off the paper warehouse and out of other products."""

from sentence_reading.llm.gcs_secrets import (
    ALLOWLIST,
    BUCKET,
    ENV_OBJECT,
    PAPER_BUCKET,
    denied,
    parse_env_bytes,
    public_members,
    render_env,
    select_runtime,
)


def test_secrets_bucket_is_not_the_paper_warehouse() -> None:
    assert BUCKET != PAPER_BUCKET
    assert not ENV_OBJECT.startswith("asr/")
    assert ENV_OBJECT.startswith("secrets/")


def test_allowlist_drops_other_products_and_pc_paths() -> None:
    parsed = {
        "GEMINI_API_KEY": "g",
        "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.cognitiveservices.azure.com",
        "ASR_AUTH_SECRET": "s",
        "ASR_GOOGLE_CLIENT_ID": "c",
        "NAVER_APP_PASSWORD": "no",
        "IPTIME_WIFI_PSK": "no",
        "STOCK_WAREHOUSE_CREDENTIALS": "no",
        "DATA_PC_WATCH_ENABLED": "1",
        "MAIL_TO": "no",
        "GOOGLE_APPLICATION_CREDENTIALS": r"C:\secret.json",
    }
    selected = select_runtime(parsed)
    assert "NAVER_APP_PASSWORD" not in selected
    assert "IPTIME_WIFI_PSK" not in selected
    assert "STOCK_WAREHOUSE_CREDENTIALS" not in selected
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in selected
    assert selected["GEMINI_API_KEY"] == "g"
    blob = render_env(selected)
    assert b"NAVER" not in blob
    assert b"IPTIME" not in blob
    assert b"STOCK_" not in blob
    again = parse_env_bytes(blob + b"\nNAVER_APP_PASSWORD=leak\nIPTIME_WIFI_PSK=leak\n")
    assert "NAVER_APP_PASSWORD" not in again
    assert "IPTIME_WIFI_PSK" not in again
    assert denied("NAVER_EMAIL")
    assert "AZURE_DOCUMENT_INTELLIGENCE_KEY" in ALLOWLIST


def test_public_members_are_visible() -> None:
    assert public_members({"bindings": [{"members": ["allUsers"]}]}) == ["allUsers"]
    assert public_members({"bindings": [{"members": ["user:me@example.com"]}]}) == []
