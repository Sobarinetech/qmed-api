import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Prescription Verifier",
    page_icon="💊",
    layout="wide",
)

API_URL = "https://sqwevzxsufrbsyjrucuw.supabase.co/functions/v1/verify-prescription-api"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_key() -> str | None:
    try:
        return st.secrets["api_key"]
    except Exception:
        return None


def call_api(payload: dict) -> dict:
    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ API key not found. Add `api_key` to your Streamlit secrets.")
        st.stop()

    resp = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json=payload,
        timeout=30,
    )

    if resp.status_code == 401:
        st.error("❌ 401 – Missing or invalid API key.")
        st.stop()
    elif resp.status_code == 403:
        st.error("❌ 403 – API key disabled or unauthorized role.")
        st.stop()
    elif resp.status_code == 400:
        st.error(f"❌ 400 – Bad request: {resp.text}")
        st.stop()
    elif resp.status_code == 405:
        st.error("❌ 405 – Method not allowed.")
        st.stop()
    elif not resp.ok:
        st.error(f"❌ {resp.status_code} – {resp.text}")
        st.stop()

    return resp.json()


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return iso


def status_badge(status: str) -> str:
    colors = {"active": "🟢", "expired": "🔴", "used": "🟡", "revoked": "🔴"}
    return f"{colors.get(status, '⚪')} {status.upper()}"


def render_single_result(data: dict):
    if not data.get("valid"):
        st.error(f"❌ Invalid prescription — {data.get('error', 'Unknown error')}")
        return

    st.success("✅ Valid Prescription")

    col1, col2, col3 = st.columns(3)
    col1.metric("Rx Number", data.get("prescription_number", "—"))
    col2.metric("Status", status_badge(data.get("status", "—")))
    col3.metric("Patient", data.get("patient_name", "—"))

    col4, col5, col6 = st.columns(3)
    col4.metric("Doctor", data.get("doctor_name", "—"))
    col5.metric("Organization", data.get("organization", "—"))
    col6.metric("Patient ID", data.get("patient_id", "—"))

    col7, col8 = st.columns(2)
    col7.metric("Issued", fmt_date(data.get("created_at")))
    col8.metric("Valid Until", fmt_date(data.get("valid_until")))

    if data.get("diagnosis"):
        st.info(f"🩺 **Diagnosis:** {data['diagnosis']}")

    meds = data.get("medications", [])
    if meds:
        st.subheader("💊 Medications")
        meds_df = pd.DataFrame(meds)
        st.dataframe(meds_df, use_container_width=True, hide_index=True)


def render_batch_results(results: list):
    total = len(results)
    valid_count = sum(1 for r in results if r.get("valid"))
    invalid_count = total - valid_count

    c1, c2, c3 = st.columns(3)
    c1.metric("Total", total)
    c2.metric("✅ Valid", valid_count)
    c3.metric("❌ Invalid", invalid_count)

    st.divider()

    for i, r in enumerate(results, 1):
        label = r.get("prescription_number") or f"Result #{i}"
        with st.expander(f"{'✅' if r.get('valid') else '❌'} {label}", expanded=(total <= 3)):
            render_single_result(r)


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("💊 Prescription Verifier")
st.caption("Verify prescriptions instantly using the secure verification API.")

tab_single, tab_batch, tab_raw = st.tabs(["Single Verification", "Batch Verification", "Raw JSON"])

# ── Single ────────────────────────────────────────────────────────────────────
with tab_single:
    st.subheader("Verify a Single Prescription")

    input_type = st.radio("Input type", ["Token", "URL"], horizontal=True, key="single_type")
    value = st.text_input(
        "Prescription Token" if input_type == "Token" else "Prescription URL",
        placeholder="a1b2c3d4-e5f6-..." if input_type == "Token" else "https://yoursite.com/verify/...",
        key="single_value",
    )

    if st.button("Verify", key="btn_single", type="primary", disabled=not value.strip()):
        payload = {"token": value.strip()} if input_type == "Token" else {"url": value.strip()}
        with st.spinner("Verifying…"):
            result = call_api(payload)
        st.session_state["last_single_raw"] = result
        render_single_result(result)

# ── Batch ─────────────────────────────────────────────────────────────────────
with tab_batch:
    st.subheader("Batch Verification (up to 50)")

    batch_type = st.radio("Input type", ["Tokens", "URLs"], horizontal=True, key="batch_type")
    placeholder_text = (
        "a1b2c3d4-e5f6-...\nb2c3d4e5-f6a7-..."
        if batch_type == "Tokens"
        else "https://yoursite.com/verify/a1b2c3d4-...\nhttps://yoursite.com/verify/b2c3d4e5-..."
    )
    raw_input = st.text_area(
        "Enter one per line",
        placeholder=placeholder_text,
        height=160,
        key="batch_input",
    )

    items = [line.strip() for line in raw_input.splitlines() if line.strip()]
    if items:
        st.caption(f"{len(items)} item(s) entered — max 50 allowed per request.")

    if st.button("Verify All", key="btn_batch", type="primary", disabled=not items):
        if len(items) > 50:
            st.warning("⚠️ Maximum 50 items per request. Only the first 50 will be sent.")
            items = items[:50]

        payload = (
            {"tokens": items} if batch_type == "Tokens" else {"urls": items}
        )
        with st.spinner(f"Verifying {len(items)} prescription(s)…"):
            result = call_api(payload)

        st.session_state["last_batch_raw"] = result
        results_list = result.get("results", [result])  # fallback for single result
        render_batch_results(results_list)

# ── Raw JSON ──────────────────────────────────────────────────────────────────
with tab_raw:
    st.subheader("Raw API Response")
    st.caption("Responses from the other tabs will appear here for debugging.")

    raw_single = st.session_state.get("last_single_raw")
    raw_batch = st.session_state.get("last_batch_raw")

    if raw_single:
        st.markdown("**Single Verification Response**")
        st.json(raw_single)

    if raw_batch:
        st.markdown("**Batch Verification Response**")
        st.json(raw_batch)

    if not raw_single and not raw_batch:
        st.info("No responses yet. Run a verification in one of the other tabs.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("ℹ️ About")
    st.markdown(
        """
        **Prescription Verifier** uses the secure verification API to validate
        prescriptions by token or URL.

        **Rate Limits**
        - Max 50 tokens per batch request
        - Each token counts as 1 API call
        - All requests are logged

        **Secrets Setup**

        Create `.streamlit/secrets.toml`:
        ```toml
        api_key = "YOUR_API_KEY"
        ```
        """
    )
    st.divider()
    key_status = "✅ Loaded" if get_api_key() else "❌ Not found"
    st.markdown(f"**API Key:** {key_status}")
