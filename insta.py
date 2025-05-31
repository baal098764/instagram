import streamlit as st
import subprocess
import tempfile
import json
import requests
from pathlib import Path

def write_gallerydl_config(sessionid: str) -> Path:
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
    cfg_path = write_gallerydl_config(sessionid)

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
        raise ValueError("Invalid tab")

    cmd = [
        "gallery-dl",
        "--config", str(cfg_path),
        "--get-url",
        "--verbose"
    ]
    if tab in ["posts", "reels", "tagged"]:
        cmd += ["--range", f"0-{max_items}"]
    cmd.append(target_url)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gallery-dl failed: {proc.stderr}")

    urls: list[str] = []
    for line in proc.stdout.splitlines():
        text = line.strip()
        if text.startswith("|"):
            text = text.lstrip("| ").strip()
        if text.startswith("http") and "cdninstagram.com" in text:
            urls.append(text)
    return urls

def is_video_url(url: str) -> bool:
    lower = url.lower()
    return any(ext in lower for ext in [".mp4", ".mov", ".gifv", ".webm", ".m3u8"])

def url_is_alive(url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code == 405:  # HEAD not allowed
            r = requests.get(url, stream=True, timeout=timeout)
            r.close()
        return r.status_code == 200
    except Exception:
        return False

def display_media_grid(urls: list[str], n_cols: int = 3):
    # 1) Filter out anything that isn't a valid 200‐OK media URL
    filtered = []
    for u in urls:
        if not (isinstance(u, str) and u.startswith("http") and "cdninstagram.com" in u.lower()):
            continue
        if url_is_alive(u):
            filtered.append(u)
        else:
            st.write(f"⚠️ Skipping unreachable URL: {u}")

    if not filtered:
        st.warning("No valid CDN URLs found after filtering.")
        return

    # 2) Lay them out in rows of up to n_cols
    for i in range(0, len(filtered), n_cols):
        row = filtered[i : i + n_cols]
        cols = st.columns(len(row))
        for col, link in zip(cols, row):
            try:
                if is_video_url(link):
                    col.video(link)
                else:
                    col.image(link, use_column_width=True)
            except Exception as e:
                col.write(f"⚠️ Could not display: {e}")

# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Instagram Downloader (URL Only)",
    page_icon="📸",
    layout="centered",
)
st.title("📸 Instagram Downloader (Grid Debug)")

if "sessionid" not in st.session_state:
    st.session_state.sessionid = ""

with st.expander("🔑 Enter your Instagram sessionid"):
    st.session_state.sessionid = st.text_input(
        "Paste your sessionid here:",
        value=st.session_state.sessionid,
        placeholder="e.g., 6340488244%3Aabcdef...:28:AYdga9Fow4Lb ...",
        key="input_sessionid",
    )
    if not st.session_state.sessionid:
        st.warning("You need a valid sessionid to see private/rate‐limited content.")

tab_posts, tab_stories, tab_reels, tab_highlights, tab_tagged, tab_url = st.tabs(
    ["🖼️ Posts", "📖 Stories", "🎞️ Reels", "✨ Highlights", "🏷️ Tagged", "🔗 URL"]
)

with tab_posts:
    st.subheader("Display Posts (Grid + Debug)")
    with st.form(key="posts_form"):
        username_posts = st.text_input(
            "Instagram Username (for Posts)", placeholder="e.g., natgeo", key="username_posts"
        )
        max_posts = st.slider(
            "Max Posts to Fetch", min_value=1, max_value=100, value=10
        )
        submit_posts = st.form_submit_button(label="Get & Display Posts")

    if submit_posts:
        if not st.session_state.sessionid:
            st.error("Please supply sessionid above.")
        elif not username_posts:
            st.error("Please enter a username.")
        else:
            info = st.info(f"⏳ Fetching post URLs for @{username_posts} …")
            try:
                urls = run_gallerydl_urls(
                    username_posts, "posts", st.session_state.sessionid, max_posts
                )
                info.empty()
                if not urls:
                    st.warning("No direct CDN URLs returned. Check your username/sessionid.")
                else:
                    st.success(f"✅ Found {len(urls)} raw URLs. Now filtering…")
                    display_media_grid(urls, n_cols=3)

            except RuntimeError as e:
                info.empty()
                st.error(f"gallery-dl error:\n{e}")
            except Exception as e:
                info.empty()
                st.error(f"Unexpected error:\n{e}")
