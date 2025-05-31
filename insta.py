import streamlit as st
import subprocess
import tempfile
import shutil
import os
import json
import zipfile
from pathlib import Path
from io import BytesIO

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions for Gallery-dl Integration
# ──────────────────────────────────────────────────────────────────────────────

def write_gallerydl_config(sessionid: str) -> Path:
    """
    Create a temporary JSON config file for gallery-dl containing only the
    Instagram sessionid cookie. Returns the path to this config file.
    """
    cfg_dir = Path(tempfile.gettempdir()) / "gdl_instagram_configs"
    cfg_dir.mkdir(exist_ok=True)
    cfg_path = cfg_dir / f"{hash(sessionid)}_ig_config.json"

    config_data = {
        "extractor": {
            "instagram": {
                "cookies": {
                    "sessionid": sessionid
                }
            }
        }
    }
    cfg_path.write_text(json.dumps(config_data, indent=2))
    return cfg_path

def run_gallerydl(username: str, tab: str, sessionid: str, max_posts: int = 100):
    """
    Run gallery-dl for the given Instagram username and tab, using the provided sessionid.
    Returns a tuple of (download_dir: Path, stdout: str, stderr: str)

    - username: Instagram handle (without '@')
    - tab: one of "posts", "stories", "reels"
    - sessionid: Instagram sessionid cookie string
    - max_posts: maximum number of posts to fetch (used with --range 0-max_posts)
    """
    # 1) Write a minimal gallery-dl config
    cfg_path = write_gallerydl_config(sessionid)

    # 2) Build the correct HTTPS-based target URL
    if tab == "posts":
        target_url = f"https://www.instagram.com/{username}/"
    elif tab == "stories":
        target_url = f"https://www.instagram.com/stories/{username}/"
    elif tab == "reels":
        target_url = f"https://www.instagram.com/{username}/reels/"
    else:
        raise ValueError("Invalid tab")

    # 3) Create a temporary directory for downloads
    download_dir = Path(tempfile.gettempdir()) / f"ig_{username}_{tab}"
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    # 4) Build the gallery-dl command
    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--destination", str(download_dir) + "/",
        "--verbose"
    ]

    # If we're fetching “posts,” add a range filter
    if tab == "posts":
        cmd += ["--range", f"0-{max_posts}"]

    cmd.append(target_url)

    # 5) Execute gallery-dl, capturing stdout and stderr
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout
    stderr = proc.stderr

    if proc.returncode != 0:
        raise RuntimeError(f"Download failed (exit {proc.returncode}):\n{stderr}")

    return download_dir, stdout, stderr

def list_downloaded_media(download_dir: Path) -> list[Path]:
    """
    Return a sorted list of Path objects for each file in download_dir and its subdirectories.
    """
    if not download_dir.exists():
        return []
    return sorted(p for p in download_dir.rglob("*") if p.is_file())

def create_zip_buffer(file_paths: list[Path]) -> BytesIO:
    """
    Given a list of Path objects, create an in-memory ZIP (BytesIO) containing them.
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            zf.write(file_path, arcname=file_path.name)
    buffer.seek(0)
    return buffer

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Instagram Downloader", layout="centered")

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar: Instructions & Disclaimer
# ──────────────────────────────────────────────────────────────────────────────

st.sidebar.header("How to Obtain Your Instagram Session ID")
st.sidebar.markdown(
    """
    1. Install the **EditThisCookie** extension (available for Chrome and other Chromium-based browsers).  
    2. Navigate to [instagram.com](https://www.instagram.com) and log into your account.  
    3. Click the EditThisCookie icon in your browser toolbar.  
    4. In the list of cookies, find the one named **`sessionid`**.  
    5. Copy its **Value** (the long string of numbers/letters).  
    6. Paste that value into the “Enter your Instagram sessionid” field in the main app.  
    """
)

st.sidebar.header("Rate Limiting & Disclaimer")
st.sidebar.markdown(
    """
    • **Instagram Rate Limits**: Making too many requests in a short period can trigger Instagram’s rate-limiting.  
    • **Possible Consequences**: Excessive scraping may result in:  
      - Temporary blocks or “Action Required” messages.  
      - Permanent bans of your Instagram account.  
      - IP address blocks if detected.  

    Use this tool responsibly. **I take no responsibility for any bans, rate limits, or other consequences** arising from your usage.
    """
)

# ──────────────────────────────────────────────────────────────────────────────
# Main App Content
# ──────────────────────────────────────────────────────────────────────────────

st.title("📸 Instagram Downloader")

# Store sessionid in session state
if "sessionid" not in st.session_state:
    st.session_state.sessionid = ""

with st.expander("🔑 Enter your Instagram sessionid"):
    st.session_state.sessionid = st.text_input(
        "Paste your sessionid here:",
        value=st.session_state.sessionid,
        placeholder="e.g., 6340488244%3Aabcdef...:28:AYdga9Fow4Lb ...",
        help="Use the steps in the sidebar to copy your sessionid cookie from instagram.com",
        key="input_sessionid",
    )
    if not st.session_state.sessionid:
        st.warning("A valid sessionid is required to download private or rate-limited content.")
    else:
        st.success("Session ID saved.")

st.markdown("---")

with st.form(key="ig_form"):
    username = st.text_input(
        "Instagram Username",
        placeholder="e.g., natgeo",
        key="ig_username"
    )

    tabs = st.radio(
        "Select Content Type:",
        options=["posts", "stories", "reels"],
        index=0,
        horizontal=True
    )

    max_posts = st.slider(
        "Max Posts to Fetch (only for Posts)",
        min_value=1, max_value=100, value=20,
        help="gallery-dl --range 0-max_posts"
    )

    submit_button = st.form_submit_button(label="Fetch Media")

if submit_button:
    if not username:
        st.error("Please enter a valid Instagram username.")
    elif not st.session_state.sessionid:
        st.error("Cannot proceed. Please provide a sessionid above.")
    else:
        status_msg = st.info(f"⏳ Downloading media for @{username} ({tabs}) ...")

        try:
            download_dir, stdout, stderr = run_gallerydl(
                username, tabs, st.session_state.sessionid, max_posts
            )
            media_files = list_downloaded_media(download_dir)

            if not media_files:
                status_msg.empty()
                st.warning("No media files were downloaded. Check the username/sessionid and try again.")
                st.code("gallery-dl stdout:\n" + stdout + "\n\nstderr:\n" + stderr, language="bash")
            else:
                status_msg.empty()
                st.success(f"✅ Downloaded {len(media_files)} files for @{username} ({tabs}).")

                cols = st.columns(3)
                for idx, file_path in enumerate(media_files):
                    col = cols[idx % 3]
                    ext = file_path.suffix.lower()
                    if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                        # Display images using use_container_width instead of the deprecated use_column_width
                        col.image(str(file_path), use_container_width=True)
                    elif ext in [".mp4", ".mov", ".gifv"]:
                        col.video(str(file_path), format="video/mp4")
                    else:
                        col.write(f"File: {file_path.name}")

                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"{username}_{tabs}_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

        except RuntimeError as e:
            status_msg.empty()
            st.error(f"Error: {e}")
        except Exception as e:
            status_msg.empty()
            st.error(f"Unexpected error: {e}")
