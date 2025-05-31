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

def run_gallerydl(identifier: str, tab: str, sessionid: str, max_items: int = 100):
    """
    Run gallery-dl for the given Instagram identifier and tab, using the provided sessionid.
    Returns a tuple of (download_dir: Path, stdout: str, stderr: str).

    - identifier:
        • For "posts", "stories", or "reels": an Instagram username (without '@').
        • For "highlights": a full Instagram highlight URL (e.g.
          https://www.instagram.com/stories/highlights/1234567890/).
    - tab: one of ["posts", "stories", "reels", "highlights"]
    - sessionid: Instagram sessionid cookie string
    - max_items: only used when tab == "posts" or tab == "reels"
    """
    # 1) Build gallery-dl config
    cfg_path = write_gallerydl_config(sessionid)

    # 2) Determine the target URL
    if tab == "posts":
        target_url = f"https://www.instagram.com/{identifier}/"
    elif tab == "stories":
        target_url = f"https://www.instagram.com/stories/{identifier}/"
    elif tab == "reels":
        target_url = f"https://www.instagram.com/{identifier}/reels/"
    elif tab == "highlights":
        target_url = identifier  # Full highlight URL pasted by the user
    else:
        raise ValueError("Invalid tab: must be one of ['posts','stories','reels','highlights']")

    # 3) Prepare download directory
    if tab == "highlights":
        # Hash the full highlights URL so folder name is filesystem-safe
        download_dir = Path(tempfile.gettempdir()) / f"ig_highlight_{hash(identifier)}"
    else:
        download_dir = Path(tempfile.gettempdir()) / f"ig_{identifier}_{tab}"

    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    # 4) Build gallery-dl command
    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--destination", str(download_dir) + "/",
        "--verbose"
    ]
    # Only apply a range filter for posts or reels
    if tab in ["posts", "reels"]:
        cmd += ["--range", f"0-{max_items}"]

    cmd.append(target_url)

    # 5) Execute gallery-dl
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout, stderr = proc.stdout, proc.stderr
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
    1. Install the **EditThisCookie** extension (Chrome/Chromium).  
    2. Log into [instagram.com](https://www.instagram.com).  
    3. Click the EditThisCookie icon.  
    4. Find the cookie named **`sessionid`**.  
    5. Copy its **Value**.  
    6. Paste into the “Enter your Instagram sessionid” field in the main app.
    """
)

st.sidebar.header("Rate Limiting & Disclaimer")
st.sidebar.markdown(
    """
    • **Instagram Rate Limits**: Too many requests too fast can trigger blocks.  
    • **Possible Consequences**:  
      - Temporary “Action Required” messages.  
      - Permanent account bans.  
      - IP blocks.  

    Use responsibly. **I take no responsibility** for any bans, rate limits, or other consequences.
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

# ──────────────────────────────────────────────────────────────────────────────
# Tabs: Posts, Stories, Reels, Highlights
# ──────────────────────────────────────────────────────────────────────────────

tab_posts, tab_stories, tab_reels, tab_highlights = st.tabs(
    ["Posts", "Stories", "Reels", "Highlights"]
)

# ──────────────── Posts Tab ────────────────
with tab_posts:
    st.subheader("Download User Posts")
    with st.form(key="posts_form"):
        username_posts = st.text_input(
            "Instagram Username (for Posts)",
            placeholder="e.g., natgeo",
            key="username_posts"
        )
        max_posts = st.slider(
            "Max Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limits how many most recent posts to download."
        )
        submit_posts = st.form_submit_button(label="Fetch Posts")

    if submit_posts:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_posts:
            st.error("Please enter a username to download their posts.")
        else:
            status_msg = st.info(f"⏳ Downloading posts for @{username_posts} ...")
            try:
                download_dir, stdout, stderr = run_gallerydl(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                media_files = list_downloaded_media(download_dir)

                if not media_files:
                    status_msg.empty()
                    st.warning(
                        "No posts were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.code("gallery-dl stdout:\n" + stdout + "\n\nstderr:\n" + stderr,
                            language="bash")
                else:
                    status_msg.empty()
                    st.success(f"✅ Downloaded {len(media_files)} posts for @{username_posts}.")

                    cols = st.columns(3)
                    for idx, file_path in enumerate(media_files):
                        col = cols[idx % 3]
                        ext = file_path.suffix.lower()
                        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            col.image(str(file_path), use_container_width=True)
                        elif ext in [".mp4", ".mov", ".gifv"]:
                            col.video(str(file_path), format="video/mp4")
                        else:
                            col.write(f"File: {file_path.name}")

                    zip_buffer = create_zip_buffer(media_files)
                    zip_name = f"{username_posts}_posts_media.zip"
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

# ──────────────── Stories Tab ────────────────
with tab_stories:
    st.subheader("Download User Stories")
    with st.form(key="stories_form"):
        username_stories = st.text_input(
            "Instagram Username (for Stories)",
            placeholder="e.g., natgeo",
            key="username_stories"
        )
        submit_stories = st.form_submit_button(label="Fetch Stories")

    if submit_stories:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_stories:
            st.error("Please enter a username to download their stories.")
        else:
            status_msg = st.info(f"⏳ Downloading stories for @{username_stories} ...")
            try:
                download_dir, stdout, stderr = run_gallerydl(
                    username_stories, "stories", st.session_state.sessionid
                )
                media_files = list_downloaded_media(download_dir)

                if not media_files:
                    status_msg.empty()
                    st.warning(
                        "No stories were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.code("gallery-dl stdout:\n" + stdout + "\n\nstderr:\n" + stderr,
                            language="bash")
                else:
                    status_msg.empty()
                    st.success(f"✅ Downloaded {len(media_files)} stories for @{username_stories}.")

                    cols = st.columns(3)
                    for idx, file_path in enumerate(media_files):
                        col = cols[idx % 3]
                        ext = file_path.suffix.lower()
                        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            col.image(str(file_path), use_container_width=True)
                        elif ext in [".mp4", ".mov", ".gifv"]:
                            col.video(str(file_path), format="video/mp4")
                        else:
                            col.write(f"File: {file_path.name}")

                    zip_buffer = create_zip_buffer(media_files)
                    zip_name = f"{username_stories}_stories_media.zip"
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

# ──────────────── Reels Tab ────────────────
with tab_reels:
    st.subheader("Download User Reels")
    with st.form(key="reels_form"):
        username_reels = st.text_input(
            "Instagram Username (for Reels)",
            placeholder="e.g., natgeo",
            key="username_reels"
        )
        max_reels = st.slider(
            "Max Reels to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limits how many most recent reels to download."
        )
        submit_reels = st.form_submit_button(label="Fetch Reels")

    if submit_reels:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_reels:
            st.error("Please enter a username to download their reels.")
        else:
            status_msg = st.info(f"⏳ Downloading reels for @{username_reels} ...")
            try:
                download_dir, stdout, stderr = run_gallerydl(
                    username_reels, "reels", st.session_state.sessionid, max_reels
                )
                media_files = list_downloaded_media(download_dir)

                if not media_files:
                    status_msg.empty()
                    st.warning(
                        "No reels were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.code("gallery-dl stdout:\n" + stdout + "\n\nstderr:\n" + stderr,
                            language="bash")
                else:
                    status_msg.empty()
                    st.success(f"✅ Downloaded {len(media_files)} reels for @{username_reels}.")

                    cols = st.columns(3)
                    for idx, file_path in enumerate(media_files):
                        col = cols[idx % 3]
                        ext = file_path.suffix.lower()
                        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            col.image(str(file_path), use_container_width=True)
                        elif ext in [".mp4", ".mov", ".gifv"]:
                            col.video(str(file_path), format="video/mp4")
                        else:
                            col.write(f"File: {file_path.name}")

                    zip_buffer = create_zip_buffer(media_files)
                    zip_name = f"{username_reels}_reels_media.zip"
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

# ──────────────── Highlights Tab ────────────────
with tab_highlights:
    st.subheader("Download Highlights")
    with st.form(key="highlights_form"):
        highlights_url = st.text_input(
            "Instagram Highlight URL",
            placeholder="e.g., https://www.instagram.com/stories/highlights/1234567890/",
            help="Paste the full URL of the Instagram Highlight you want to download.",
            key="highlight_url"
        )
        submit_highlights = st.form_submit_button(label="Fetch Highlights")

    if submit_highlights:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not highlights_url:
            st.error("Please enter a valid Instagram Highlight URL.")
        else:
            status_msg = st.info(f"⏳ Downloading highlight from: {highlights_url} ...")
            try:
                download_dir, stdout, stderr = run_gallerydl(
                    highlights_url, "highlights", st.session_state.sessionid
                )
                media_files = list_downloaded_media(download_dir)

                if not media_files:
                    status_msg.empty()
                    st.warning(
                        "No media files were downloaded. "
                        "Check the highlight URL and sessionid, then try again."
                    )
                    st.code("gallery-dl stdout:\n" + stdout + "\n\nstderr:\n" + stderr,
                            language="bash")
                else:
                    status_msg.empty()
                    st.success(f"✅ Downloaded {len(media_files)} files from the highlight.")

                    cols = st.columns(3)
                    for idx, file_path in enumerate(media_files):
                        col = cols[idx % 3]
                        ext = file_path.suffix.lower()
                        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                            col.image(str(file_path), use_container_width=True)
                        elif ext in [".mp4", ".mov", ".gifv"]:
                            col.video(str(file_path), format="video/mp4")
                        else:
                            col.write(f"File: {file_path.name}")

                    zip_buffer = create_zip_buffer(media_files)
                    zip_name = f"highlight_{hash(highlights_url)}_media.zip"
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
