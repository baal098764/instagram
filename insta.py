import streamlit as st
import subprocess
import tempfile
import shutil
import os
import json
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions for “URL‐only” Gallery‐dl Integration
# ──────────────────────────────────────────────────────────────────────────────

def write_gallerydl_config(sessionid: str) -> Path:
    """
    Create a minimal JSON config file for gallery-dl containing only the
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

def run_gallerydl_urls(identifier: str, tab: str, sessionid: str, max_items: int = 100) -> list[str]:
    """
    Runs gallery-dl in “URL‐only” mode (with --get-url) for the given Instagram identifier.
    Returns a list of URLs (one per media item).

    - identifier:
        • For "posts", "stories", "reels", "tagged": an Instagram username (without '@').
        • For "highlights" or "url": a full Instagram URL (post/reel/highlight/story).
    - tab: one of ["posts", "stories", "reels", "highlights", "tagged", "url"]
    - sessionid: Instagram sessionid cookie string
    - max_items: only used when tab in ["posts", "reels", "tagged"]
    """
    # 1) Build gallery-dl config file
    cfg_path = write_gallerydl_config(sessionid)

    # 2) Determine target URL
    if tab == "posts":
        target_url = f"https://www.instagram.com/{identifier}/"
    elif tab == "stories":
        target_url = f"https://www.instagram.com/stories/{identifier}/"
    elif tab == "reels":
        target_url = f"https://www.instagram.com/{identifier}/reels/"
    elif tab == "tagged":
        target_url = f"https://www.instagram.com/{identifier}/tagged/"
    elif tab in ["highlights", "url"]:
        # “highlights” and “url” expect a full URL string
        target_url = identifier
    else:
        raise ValueError("Invalid tab: must be one of ['posts','stories','reels','highlights','tagged','url']")

    # 3) Build gallery-dl command in “URL‐only” mode
    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--get-url",
        "--verbose"
    ]
    # Only apply a range filter for “posts”, “reels”, “tagged”
    if tab in ["posts", "reels", "tagged"]:
        cmd += ["--range", f"0-{max_items}"]

    cmd.append(target_url)

    # 4) Execute gallery-dl
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout, stderr = proc.stdout, proc.stderr

    if proc.returncode != 0:
        # If gallery-dl fails, propagate an error
        raise RuntimeError(f"gallery-dl failed (exit {proc.returncode}):\n{stderr}")

    # 5) Parse stdout: gallery-dl prints one URL (or directive) per line
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return lines

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ──────────────────────────────────────────────────────────────────────────────

# Set page config with a custom favicon (browser‐tab icon)
st.set_page_config(
    page_title="Instagram Downloader (URL Only)",
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

st.title("📸 Instagram Downloader (URL‐Only Mode)")

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
        st.warning("A valid sessionid is required to access private or rate-limited content.")
    else:
        st.success("Session ID saved.")

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────────
# Tabs: Posts, Stories, Reels, Highlights, Tagged Posts, URL Input
# ──────────────────────────────────────────────────────────────────────────────
tab_posts, tab_stories, tab_reels, tab_highlights, tab_tagged, tab_url = st.tabs(
    ["🖼️ Posts", "📖 Stories", "🎞️ Reels", "✨ Highlights", "🏷️ Tagged Posts", "🔗 URL Input"]
)

def is_video_url(url: str) -> bool:
    """
    Naively check if a URL points to a video by inspecting known video extensions.
    """
    return any(ext in url.lower() for ext in [".mp4", ".mov", ".gifv", ".webm"])

def filter_media_urls(lines: list[str]) -> tuple[list[str], int]:
    """
    Given a list of lines returned by run_gallerydl_urls, 
    return (clean_urls, skipped_count), where:
      - clean_urls: only those lines that start with 'http' 
        AND end in an image/video extension.
      - skipped_count: how many lines were dropped (e.g. 'ytdl:dash').
    """
    clean = []
    skipped = 0
    for ln in lines:
        if ln.startswith("http"):
            # If it looks like a media link (common extensions), keep it.
            if any(ln.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp",
                                                       ".mp4", ".mov", ".gifv", ".webm"]):
                clean.append(ln)
            else:
                # It's an HTTP link but with no known extension; include anyway.
                clean.append(ln)
        else:
            # Non-http (e.g. "ytdl:dash") → skip
            skipped += 1
    return clean, skipped

# ──────────────────────────────────────────────────────────────────────────────
# Posts Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_posts:
    st.subheader("Display User Posts (Inline Media)")
    with st.form(key="posts_form"):
        username_posts = st.text_input(
            "Instagram Username (for Posts)",
            placeholder="e.g., natgeo",
            key="username_posts"
        )
        max_posts = st.slider(
            "Max Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent posts to display."
        )
        submit_posts = st.form_submit_button(label="Get & Display Posts")

    if submit_posts:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_posts:
            st.error("Please enter a username to display their posts.")
        else:
            status_msg = st.info(f"⏳ Fetching post URLs for @{username_posts} ...")
            try:
                all_lines = run_gallerydl_urls(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                status_msg.empty()

                # Filter out non-http lines (like ytdl:dash, etc.)
                clean_urls, skipped_count = filter_media_urls(all_lines)

                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines (e.g. ‘ytdl:dash’).")

                if not clean_urls:
                    st.warning("No valid media URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} posts for @{username_posts}:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

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
    st.subheader("Display User Stories (Inline Media)")
    with st.form(key="stories_form"):
        username_stories = st.text_input(
            "Instagram Username (for Stories)",
            placeholder="e.g., natgeo",
            key="username_stories"
        )
        submit_stories = st.form_submit_button(label="Get & Display Stories")

    if submit_stories:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_stories:
            st.error("Please enter a username to display their stories.")
        else:
            status_msg = st.info(f"⏳ Fetching story URLs for @{username_stories} ...")
            try:
                all_lines = run_gallerydl_urls(
                    username_stories, "stories", st.session_state.sessionid
                )
                status_msg.empty()

                clean_urls, skipped_count = filter_media_urls(all_lines)
                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines.")

                if not clean_urls:
                    st.warning("No valid story URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} stories for @{username_stories}:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

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
    st.subheader("Display User Reels (Inline Media)")
    with st.form(key="reels_form"):
        username_reels = st.text_input(
            "Instagram Username (for Reels)",
            placeholder="e.g., natgeo",
            key="username_reels"
        )
        max_reels = st.slider(
            "Max Reels to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent reels to display."
        )
        submit_reels = st.form_submit_button(label="Get & Display Reels")

    if submit_reels:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_reels:
            st.error("Please enter a username to display their reels.")
        else:
            status_msg = st.info(f"⏳ Fetching reel URLs for @{username_reels} ...")
            try:
                all_lines = run_gallerydl_urls(
                    username_reels, "reels", st.session_state.sessionid, max_reels
                )
                status_msg.empty()

                clean_urls, skipped_count = filter_media_urls(all_lines)
                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines.")

                if not clean_urls:
                    st.warning("No valid reel URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} reels for @{username_reels}:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

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
    st.subheader("Display Highlight Media (Inline)")
    with st.form(key="highlights_form"):
        highlights_url = st.text_input(
            "Instagram Highlight URL",
            placeholder="e.g., https://www.instagram.com/stories/highlights/1234567890/",
            help="Paste the full URL of the Instagram Highlight you want to display.",
            key="highlight_url"
        )
        submit_highlights = st.form_submit_button(label="Get & Display Highlights")

    if submit_highlights:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not highlights_url:
            st.error("Please enter a valid Instagram Highlight URL.")
        else:
            status_msg = st.info(f"⏳ Fetching highlight URLs from: {highlights_url} ...")
            try:
                all_lines = run_gallerydl_urls(
                    highlights_url, "highlights", st.session_state.sessionid
                )
                status_msg.empty()

                clean_urls, skipped_count = filter_media_urls(all_lines)
                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines.")

                if not clean_urls:
                    st.warning("No valid highlight URLs returned. Check URL/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} highlight media items:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

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
    st.subheader("Display Tagged‐Post Media (Inline)")
    with st.form(key="tagged_form"):
        username_tagged = st.text_input(
            "Instagram Username (for Tagged Posts)",
            placeholder="e.g., natgeo",
            key="username_tagged"
        )
        max_tagged = st.slider(
            "Max Tagged Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent tagged‐post items to display."
        )
        submit_tagged = st.form_submit_button(label="Get & Display Tagged Posts")

    if submit_tagged:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_tagged:
            st.error("Please enter a username to display their tagged posts.")
        else:
            status_msg = st.info(f"⏳ Fetching tagged-post URLs for @{username_tagged} ...")
            try:
                all_lines = run_gallerydl_urls(
                    username_tagged, "tagged", st.session_state.sessionid, max_tagged
                )
                status_msg.empty()

                clean_urls, skipped_count = filter_media_urls(all_lines)
                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines.")

                if not clean_urls:
                    st.warning("No valid tagged‐post URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} tagged‐post items for @{username_tagged}:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

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
    st.subheader("Display Media from Any Instagram URL (Inline)")
    with st.form(key="url_form"):
        custom_url = st.text_input(
            "Instagram URL (post/reel/highlight/story)",
            placeholder="e.g., https://www.instagram.com/p/XXXXXXXXXXX/",
            help="Paste any valid Instagram URL (post, story, reel, highlight, profile, etc.).",
            key="custom_url"
        )
        submit_url = st.form_submit_button(label="Get & Display Media")

    if submit_url:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not custom_url:
            st.error("Please enter a valid Instagram URL.")
        else:
            status_msg = st.info(f"⏳ Fetching media URLs from: {custom_url} ...")
            try:
                all_lines = run_gallerydl_urls(
                    custom_url, "url", st.session_state.sessionid
                )
                status_msg.empty()

                clean_urls, skipped_count = filter_media_urls(all_lines)
                if skipped_count > 0:
                    st.warning(f"⚠️ Skipped {skipped_count} non-media lines.")

                if not clean_urls:
                    st.warning("No valid media URLs returned. Check URL/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(clean_urls)} items from the provided URL:")
                    for url in clean_urls:
                        if is_video_url(url):
                            st.video(url)
                        else:
                            st.image(url, use_container_width=True)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")
