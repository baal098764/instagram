import streamlit as st
import subprocess
import tempfile
import json
import shutil
import os
import zipfile
import requests
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

def run_gallerydl(identifier: str, tab: str, sessionid: str, max_items: int = 100) -> Path:
    """
    Run gallery-dl for the given Instagram identifier and tab, using the provided sessionid.
    Returns the Path to the directory where media were downloaded.

    - identifier:
        • For "posts", "stories", "reels", "tagged": an Instagram username (without '@').
        • For "highlights" or "url": a full Instagram URL (e.g., post, reel, highlight, story).
    - tab: one of ["posts", "stories", "reels", "highlights", "tagged", "url"]
    - sessionid: Instagram sessionid cookie string
    - max_items: only used when tab in ["posts", "reels", "tagged"]
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
    elif tab == "tagged":
        target_url = f"https://www.instagram.com/{identifier}/tagged/"
    elif tab in ["highlights", "url"]:
        target_url = identifier
    else:
        raise ValueError("Invalid tab: must be one of ['posts','stories','reels','highlights','tagged','url']")

    # 3) Prepare download directory (unique per identifier+tab)
    if tab == "highlights":
        download_dir = Path(tempfile.gettempdir()) / f"ig_highlight_{hash(identifier)}"
    elif tab == "url":
        download_dir = Path(tempfile.gettempdir()) / f"ig_url_{hash(identifier)}"
    else:
        download_dir = Path(tempfile.gettempdir()) / f"ig_{identifier}_{tab}"

    # If previous run exists, wipe it first
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    # 4) Build gallery-dl command
    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--destination", str(download_dir) + os.sep,
        "--verbose"
    ]
    if tab in ["posts", "reels", "tagged"]:
        cmd += ["--range", f"0-{max_items}"]
    cmd.append(target_url)

    # 5) Execute gallery-dl
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Download failed (exit {proc.returncode}):\n{proc.stderr}")

    return download_dir

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

def clear_downloaded_folder(download_dir: Path) -> bool:
    """
    If the folder exists, delete it and return True. Otherwise return False.
    """
    if download_dir.exists():
        shutil.rmtree(download_dir)
        return True
    return False

def is_video_file(file_path: Path) -> bool:
    """
    Return True if the local file’s extension indicates a video.
    """
    ext = file_path.suffix.lower()
    return ext in [".mp4", ".mov", ".gifv", ".webm", ".mkv", ".avi"]

def display_media_grid_from_paths(file_paths: list[Path], n_cols: int = 3):
    """
    Given a list of local Paths, display them in a grid of n_cols columns per row.
    Uses st.columns() and calls st.image(...) or st.video(...) with use_container_width=True.
    """
    if not file_paths:
        return
    for i in range(0, len(file_paths), n_cols):
        chunk = file_paths[i : i + n_cols]
        cols = st.columns(len(chunk))
        for col, path in zip(cols, chunk):
            try:
                if is_video_file(path):
                    col.video(str(path), format="video/mp4", use_container_width=True)
                else:
                    col.image(str(path), use_container_width=True)
            except Exception as e:
                col.write(f"⚠️ Could not display {path.name}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Instagram Downloader",
    page_icon="https://www.freepngimg.com/download/computer/68394-computer-instagram-icons-png-file-hd.png",
    layout="centered",
)

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
        st.warning("A valid sessionid is required to download and display private or rate-limited content.")
    else:
        st.success("Session ID saved.")

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────────
# Tabs: Posts, Stories, Reels, Highlights, Tagged Posts, URL Input
# ──────────────────────────────────────────────────────────────────────────────

tab_posts, tab_stories, tab_reels, tab_highlights, tab_tagged, tab_url = st.tabs(
    ["🖼️ Posts", "📖 Stories", "🎞️ Reels", "✨ Highlights", "🏷️ Tagged Posts", "🔗 URL Input"]
)

# ──────────────────────────────────────────────────────────────────────────────
# Posts Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_posts:
    st.subheader("Download & Display User Posts (Grid View)")
    with st.form(key="posts_form"):
        username_posts = st.text_input(
            "Instagram Username (for Posts)",
            placeholder="e.g., natgeo",
            key="username_posts"
        )
        max_posts = st.slider(
            "Max Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limits how many of the most recent posts to download."
        )
        submit_posts = st.form_submit_button(label="Fetch Posts")

    if submit_posts:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_posts:
            st.error("Please enter a username to download their posts.")
        else:
            status_msg = st.info(f"⏳ Downloading posts for @{username_posts} …")
            try:
                download_dir = run_gallerydl(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No posts were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} posts for @{username_posts}.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"{username_posts}_posts_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded Posts"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded post files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded post folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Stories Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_stories:
    st.subheader("Download & Display User Stories (Grid View)")
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
            status_msg = st.info(f"⏳ Downloading stories for @{username_stories} …")
            try:
                download_dir = run_gallerydl(
                    username_stories, "stories", st.session_state.sessionid
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No stories were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} stories for @{username_stories}.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"{username_stories}_stories_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded Stories"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded story files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded story folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Reels Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_reels:
    st.subheader("Download & Display User Reels (Grid View)")
    with st.form(key="reels_form"):
        username_reels = st.text_input(
            "Instagram Username (for Reels)",
            placeholder="e.g., natgeo",
            key="username_reels"
        )
        max_reels = st.slider(
            "Max Reels to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limits how many of the most recent reels to download."
        )
        submit_reels = st.form_submit_button(label="Fetch Reels")

    if submit_reels:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_reels:
            st.error("Please enter a username to download their reels.")
        else:
            status_msg = st.info(f"⏳ Downloading reels for @{username_reels} …")
            try:
                download_dir = run_gallerydl(
                    username_reels, "reels", st.session_state.sessionid, max_reels
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No reels were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} reels for @{username_reels}.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"{username_reels}_reels_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded Reels"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded reel files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded reel folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Highlights Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_highlights:
    st.subheader("Download & Display Highlights (Grid View)")
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
            status_msg = st.info(f"⏳ Downloading highlight from: {highlights_url} …")
            try:
                download_dir = run_gallerydl(
                    highlights_url, "highlights", st.session_state.sessionid
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No media files were downloaded. "
                        "Check the highlight URL and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} files from the highlight.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"highlight_{hash(highlights_url)}_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded Highlights"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded highlight files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded highlight folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Tagged Posts Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_tagged:
    st.subheader("Download & Display Tagged Posts (Grid View)")
    with st.form(key="tagged_form"):
        username_tagged = st.text_input(
            "Instagram Username (for Tagged Posts)",
            placeholder="e.g., natgeo",
            key="username_tagged"
        )
        max_tagged = st.slider(
            "Max Tagged Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limits how many of the most recent tagged posts to download."
        )
        submit_tagged = st.form_submit_button(label="Fetch Tagged Posts")

    if submit_tagged:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_tagged:
            st.error("Please enter a username to download their tagged posts.")
        else:
            status_msg = st.info(f"⏳ Downloading tagged posts for @{username_tagged} …")
            try:
                download_dir = run_gallerydl(
                    username_tagged, "tagged", st.session_state.sessionid, max_tagged
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No tagged posts were downloaded. "
                        "Check the username and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} tagged posts for @{username_tagged}.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"{username_tagged}_tagged_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded Tagged Posts"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded tagged-post files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded tagged-post folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# URL Input Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_url:
    st.subheader("Download & Display from Custom URL (Grid View)")
    with st.form(key="url_form"):
        custom_url = st.text_input(
            "Instagram URL",
            placeholder="e.g., https://www.instagram.com/p/XXXXXXXXXXX/",
            help="Paste any valid Instagram URL (post, story, reel, highlight, profile, etc.).",
            key="custom_url"
        )
        submit_url = st.form_submit_button(label="Fetch from URL")

    if submit_url:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not custom_url:
            st.error("Please enter a valid Instagram URL.")
        else:
            status_msg = st.info(f"⏳ Downloading media from: {custom_url} …")
            try:
                download_dir = run_gallerydl(
                    custom_url, "url", st.session_state.sessionid
                )
                media_files = list_downloaded_media(download_dir)

                status_msg.empty()
                if not media_files:
                    st.warning(
                        "No media files were downloaded. "
                        "Check the URL and sessionid, then try again."
                    )
                    st.stop()

                st.success(f"✅ Downloaded {len(media_files)} files from the URL.")

                # 1) Display media grid
                display_media_grid_from_paths(media_files, n_cols=3)

                # 2) ZIP download for convenience (only “Download All”)
                zip_buffer = create_zip_buffer(media_files)
                zip_name = f"url_{hash(custom_url)}_media.zip"
                st.download_button(
                    label="💾 Download All as ZIP",
                    data=zip_buffer,
                    file_name=zip_name,
                    mime="application/zip"
                )

                # 3) “Clear Media” button to remove files from server storage
                if st.button("🗑️ Clear Downloaded URL Media"):
                    success = clear_downloaded_folder(download_dir)
                    if success:
                        st.success("All downloaded URL media files have been cleared from server storage.")
                    else:
                        st.warning("No downloaded URL folder found to clear.")

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")
