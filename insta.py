import streamlit as st
import subprocess
import tempfile
import json
import requests
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
    Returns a list of direct media URLs (one per media item) that contain 'cdninstagram.com'.

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
        target_url = f"https://www.instagram.com/{identifier}/posts"
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

    # 3) Build gallery-dl command in “URL‐only” mode
    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--get-url",
        "--verbose"
    ]
    if tab in ["posts", "reels", "tagged"]:
        cmd += ["--range", f"0-{max_items}"]
    cmd.append(target_url)

    # 4) Execute gallery-dl
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout, stderr = proc.stdout, proc.stderr

    if proc.returncode != 0:
        raise RuntimeError(f"gallery-dl failed (exit {proc.returncode}):\n{stderr}")

    # 5) Parse stdout to extract only 'cdninstagram.com' URLs
    urls: list[str] = []
    for line in stdout.splitlines():
        text = line.strip()
        if text.startswith("|"):
            text = text.lstrip("| ").strip()
        if text.startswith("http") and "cdninstagram.com" in text:
            urls.append(text)
    return urls

def is_video_url(url: str) -> bool:
    """
    Return True if the URL looks like a video link we can feed to st.video().
    """
    lower = url.lower()
    return any(ext in lower for ext in [".mp4", ".mov", ".gifv", ".webm", ".m3u8"])

def url_is_alive(url: str, timeout: float = 2.0) -> bool:
    """
    Quick HEAD (or small GET) to check if the URL returns 200 OK.
    Filters out placeholders or expired links.
    """
    try:
        # Try HEAD first
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code == 405:  # HEAD not allowed → try GET
            r = requests.get(url, stream=True, timeout=timeout)
            r.close()
        return r.status_code == 200
    except Exception:
        return False

def display_media_grid(urls: list[str], n_cols: int = 3):
    """
    Given a list of URLs, filter out anything that doesn’t return 200, then lay out
    the rest in a grid with n_cols columns per row. Uses st.columns() and
    calls st.image(...) or st.video(...) with use_container_width=True.
    """
    # 1) Filter out invalid or unreachable URLs
    filtered: list[str] = []
    for u in urls:
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        if "cdninstagram.com" not in u.lower():
            continue
        if url_is_alive(u):
            filtered.append(u)
        else:
            st.write(f"⚠️ Skipping unreachable URL: {u}")

    if not filtered:
        st.warning("No valid CDN URLs found after filtering out broken links.")
        return

    # 2) Break into rows of size n_cols
    for i in range(0, len(filtered), n_cols):
        row_chunk = filtered[i : i + n_cols]
        cols = st.columns(len(row_chunk))
        for col, link in zip(cols, row_chunk):
            try:
                if is_video_url(link):
                    col.video(link, use_container_width=True)
                else:
                    col.image(link, use_container_width=True)
            except Exception as e:
                col.write(f"⚠️ Failed to display media:\n{e}")

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Instagram Downloader (URL Only)",
    page_icon="https://www.freepngimg.com/download/computer/68394-computer-instagram-icons-png-file-hd.png",
    layout="centered",
)

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

st.title("📸 Instagram Downloader (URL‐Only Mode)")

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

tab_posts, tab_stories, tab_reels, tab_highlights, tab_tagged, tab_url = st.tabs(
    ["🖼️ Posts", "📖 Stories", "🎞️ Reels", "✨ Highlights", "🏷️ Tagged Posts", "🔗 URL Input"]
)

with tab_posts:
    st.subheader("Display User Posts (Grid View)")
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
                urls = run_gallerydl_urls(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} posts for @{username_posts}:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

with tab_stories:
    st.subheader("Display User Stories (Grid View)")
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
                urls = run_gallerydl_urls(
                    username_stories, "stories", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} stories for @{username_stories}:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

with tab_reels:
    st.subheader("Display User Reels (Grid View)")
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
                urls = run_gallerydl_urls(
                    username_reels, "reels", st.session_state.sessionid, max_reels
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} reels for @{username_reels}:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

with tab_highlights:
    st.subheader("Display Highlight Media (Grid View)")
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
                urls = run_gallerydl_urls(
                    highlights_url, "highlights", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check URL/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} highlight media items:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

with tab_tagged:
    st.subheader("Display Tagged‐Post Media (Grid View)")
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
                urls = run_gallerydl_urls(
                    username_tagged, "tagged", st.session_state.sessionid, max_tagged
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check username/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} tagged‐post items for @{username_tagged}:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")

with tab_url:
    st.subheader("Display Media from Any Instagram URL (Grid View)")
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
                urls = run_gallerydl_urls(
                    custom_url, "url", st.session_state.sessionid
                )
                status_msg.empty()

                if not urls:
                    st.warning("No direct CDN URLs returned. Check URL/sessionid and try again.")
                else:
                    st.success(f"✅ Displaying {len(urls)} items from the provided URL:")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                status_msg.empty()
                st.error(f"Error: {e}")
            except Exception as e:
                status_msg.empty()
                st.error(f"Unexpected error: {e}")
