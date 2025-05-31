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
        • For "highlights" or "url": a full Instagram URL (post/ reel/ highlight).
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
        "--get-url",        # <-- print direct media URLs instead of downloading
        "--verbose"         # optional, can be omitted if you don't need debug output
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

    # 5) Parse stdout: gallery-dl prints one URL per line
    urls = [line.strip() for line in stdout.splitlines() if line.strip()]
    return urls

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ──────────────────────────────────────────────────────────────────────────────

# Add custom favicon (browser‐tab icon)
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

# ──────────────────────────────────────────────────────────────────────────────
# Posts Tab
# ──────────────────────────────────────────────────────────────────────────────
with tab_posts:
    st.subheader("List Post URLs (Latest Media from a User)")
    with st.form(key="posts_form"):
        username_posts = st.text_input(
            "Instagram Username (for Posts)",
            placeholder="e.g., natgeo",
            key="username_posts"
        )
        max_posts = st.slider(
            "Max Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent posts to list URLs for."
        )
        submit_posts = st.form_submit_button(label="Get Post URLs")

    if submit_posts:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_posts:
            st.error("Please enter a username to list their post URLs.")
        else:
            status_msg = st.info(f"⏳ Fetching post URLs for @{username_posts} ...")
            try:
                urls = run_gallerydl_urls(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                status_msg.empty()

                if not urls:
                    st.warning("No post URLs were returned. Check the username/sessionid and try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} post URLs for @{username_posts}.")
                    for u in urls:
                        st.text(u)

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
    st.subheader("List Story URLs (Current Stories of a User)")
    with st.form(key="stories_form"):
        username_stories = st.text_input(
            "Instagram Username (for Stories)",
            placeholder="e.g., natgeo",
            key="username_stories"
        )
        submit_stories = st.form_submit_button(label="Get Story URLs")

    if submit_stories:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_stories:
            st.error("Please enter a username to list their story URLs.")
        else:
            status_msg = st.info(f"⏳ Fetching story URLs for @{username_stories} ...")
            try:
                urls = run_gallerydl_urls(
                    username_stories, "stories", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No story URLs were returned. Check the username/sessionid and try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} story URLs for @{username_stories}.")
                    for u in urls:
                        st.text(u)

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
    st.subheader("List Reel URLs (Latest Reels from a User)")
    with st.form(key="reels_form"):
        username_reels = st.text_input(
            "Instagram Username (for Reels)",
            placeholder="e.g., natgeo",
            key="username_reels"
        )
        max_reels = st.slider(
            "Max Reels to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent reels to list URLs for."
        )
        submit_reels = st.form_submit_button(label="Get Reel URLs")

    if submit_reels:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_reels:
            st.error("Please enter a username to list their reel URLs.")
        else:
            status_msg = st.info(f"⏳ Fetching reel URLs for @{username_reels} ...")
            try:
                urls = run_gallerydl_urls(
                    username_reels, "reels", st.session_state.sessionid, max_reels
                )
                status_msg.empty()

                if not urls:
                    st.warning("No reel URLs were returned. Check the username/sessionid and try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} reel URLs for @{username_reels}.")
                    for u in urls:
                        st.text(u)

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
    st.subheader("List Highlight URLs (Single Highlight Collection)")
    with st.form(key="highlights_form"):
        highlights_url = st.text_input(
            "Instagram Highlight URL",
            placeholder="e.g., https://www.instagram.com/stories/highlights/1234567890/",
            help="Paste the full URL of the Instagram Highlight you want to list URLs for.",
            key="highlight_url"
        )
        submit_highlights = st.form_submit_button(label="Get Highlight URLs")

    if submit_highlights:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not highlights_url:
            st.error("Please enter a valid Instagram Highlight URL.")
        else:
            status_msg = st.info(f"⏳ Fetching highlight URLs from: {highlights_url} ...")
            try:
                urls = run_gallerydl_urls(
                    highlights_url, "highlights", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No highlight URLs were returned. Check the highlight URL/sessionid and try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} highlight URLs.")
                    for u in urls:
                        st.text(u)

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
    st.subheader("List Tagged‐Post URLs (Media in which User Is Tagged)")
    with st.form(key="tagged_form"):
        username_tagged = st.text_input(
            "Instagram Username (for Tagged Posts)",
            placeholder="e.g., natgeo",
            key="username_tagged"
        )
        max_tagged = st.slider(
            "Max Tagged Posts to Fetch",
            min_value=1, max_value=100, value=20,
            help="Limit how many of the most recent tagged‐post URLs to list."
        )
        submit_tagged = st.form_submit_button(label="Get Tagged URLs")

    if submit_tagged:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not username_tagged:
            st.error("Please enter a username to list their tagged‐post URLs.")
        else:
            status_msg = st.info(f"⏳ Fetching tagged-post URLs for @{username_tagged} ...")
            try:
                urls = run_gallerydl_urls(
                    username_tagged, "tagged", st.session_state.sessionid, max_tagged
                )
                status_msg.empty()

                if not urls:
                    st.warning("No tagged‐post URLs were returned. Check the username/sessionid and try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} tagged-post URLs for @{username_tagged}.")
                    for u in urls:
                        st.text(u)

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
    st.subheader("List URLs from Any Instagram URL")
    with st.form(key="url_form"):
        custom_url = st.text_input(
            "Instagram URL (post/reel/highlight/story)",
            placeholder="e.g., https://www.instagram.com/p/XXXXXXXXXXX/",
            help="Paste any valid Instagram URL (post, story, reel, highlight, profile, etc.).",
            key="custom_url"
        )
        submit_url = st.form_submit_button(label="Get Media URLs")

    if submit_url:
        if not st.session_state.sessionid:
            st.error("Cannot proceed. Please provide a sessionid above.")
        elif not custom_url:
            st.error("Please enter a valid Instagram URL.")
        else:
            status_msg = st.info(f"⏳ Fetching media URLs from: {custom_url} ...")
            try:
                urls = run_gallerydl_urls(
                    custom_url, "url", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No media URLs were returned. Check the URL and sessionid, then try again.")
                else:
                    st.success(f"✅ Retrieved {len(urls)} media URLs from the provided URL.")
                    for u in urls:
                        st.text(u)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")
