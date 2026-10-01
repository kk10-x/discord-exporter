#!/usr/bin/env python3
"""
================================================================================
 Discord Exporter — README
================================================================================
Pulls message history from channels/servers you already have access to, using
your own account's API token. No bot is added and no other member is notified;
it just makes the same authenticated HTTP requests your Discord client makes.

--------------------------------------------------------------------------------
 1. Get your account token (do this in a browser, on your own account)
--------------------------------------------------------------------------------
    1. Open https://discord.com/app in a browser and log in.
    2. Open DevTools (F12) -> "Network" tab.
    3. Send any message, or scroll a channel, to trigger some traffic.
    4. Click any request to "discord.com/api/v9/..." in the list.
    5. In its request headers, find "authorization" and copy that value.
    6. Treat it exactly like a password — anyone with it can act as your
       account. Never paste it into anything but your own local terminal.

--------------------------------------------------------------------------------
 2. Get a server (guild) ID or channel ID
--------------------------------------------------------------------------------
    1. In Discord: User Settings (gear icon) -> Advanced -> enable
       "Developer Mode".
    2. Right-click a server icon -> "Copy Server ID"      (for --guild)
       Right-click a channel name -> "Copy Channel ID"    (for --channel)

--------------------------------------------------------------------------------
 3. Set the token for your terminal session
--------------------------------------------------------------------------------
    PowerShell:   $env:DISCORD_TOKEN="paste_your_token_here"
    cmd.exe:      set DISCORD_TOKEN=paste_your_token_here
    bash:         export DISCORD_TOKEN=paste_your_token_here

    This only lasts for the current terminal window — run it again each new
    session. Run it from a normal folder you can write to (not
    C:\\Windows\\System32 or another protected directory).

--------------------------------------------------------------------------------
 4. Run it
--------------------------------------------------------------------------------
    Syntax:
        python discord_export.py (--channel ID | --guild ID) [options]

    Required (pick one):
        --channel ID          Export a single channel
        --guild ID            Export every text channel in a server

    Options:
        --out DIR             Output directory (default: ./export)
        --format FORMAT        json (default, raw data), txt (readable
                               transcript), or html (styled page you can
                               open in a browser)
        --with-attachments     Also download attached images/files
        --no-threads           Skip threads (by default, active and archived
                               threads under each channel are exported too,
                               into a "<channel>_threads" subfolder)

    Examples:
        python discord_export.py --channel 123456789012345678
        python discord_export.py --guild 123456789012345678 --format html
        python discord_export.py --guild 123... --with-attachments --out my_export
        python discord_export.py --guild <server-id> --with-attachments --format html --out <output-path>
================================================================================
"""
import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://discord.com/api/v10"


def author_name(msg: dict) -> str:
    author = msg.get("author", {})
    return author.get("global_name") or author.get("username") or "unknown"


def write_json(messages: list[dict], out_file: Path):
    out_file.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")


def write_txt(messages: list[dict], out_file: Path):
    lines = []
    for m in messages:
        ts = m.get("timestamp", "")[:19].replace("T", " ")
        lines.append(f"[{ts}] {author_name(m)}: {m.get('content', '')}")
        for att in m.get("attachments", []):
            lines.append(f"    [attachment] {att.get('filename')} — {att.get('url')}")
    out_file.write_text("\n".join(lines), encoding="utf-8")


def write_html(messages: list[dict], out_file: Path, channel_name: str):
    rows = []
    for m in messages:
        ts = html.escape(m.get("timestamp", "")[:19].replace("T", " "))
        author = html.escape(author_name(m))
        content = html.escape(m.get("content", "")).replace("\n", "<br>")
        atts = ""
        for att in m.get("attachments", []):
            url = html.escape(att.get("url", ""))
            filename = html.escape(att.get("filename", ""))
            if any(att.get("filename", "").lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                atts += f'<div class="att"><img src="{url}" alt="{filename}" loading="lazy"></div>'
            else:
                atts += f'<div class="att"><a href="{url}">{filename}</a></div>'
        rows.append(
            f'<div class="msg"><span class="ts">{ts}</span> <span class="author">{author}</span>'
            f'<div class="content">{content}</div>{atts}</div>'
        )

    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(channel_name)}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background:#313338; color:#dbdee1; margin:0; padding:20px; }}
.msg {{ padding:8px 0; border-bottom:1px solid #3f4147; }}
.ts {{ color:#949ba4; font-size:12px; margin-right:8px; }}
.author {{ color:#f2f3f5; font-weight:600; }}
.content {{ margin-top:2px; white-space:pre-wrap; }}
.att img {{ max-width:400px; border-radius:4px; margin-top:6px; }}
.att a {{ color:#00a8fc; }}
</style></head><body>
<h2>{html.escape(channel_name)}</h2>
{''.join(rows)}
</body></html>"""
    out_file.write_text(page, encoding="utf-8")


def api_request(path: str, token: str, params: dict | None = None) -> dict | list:
    url = f"{API}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        if query:
            url = f"{url}?{query}"

    headers = {
        "Authorization": token,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    while True:
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                body = json.loads(e.read().decode("utf-8"))
                wait = body.get("retry_after", 1.0)
                print(f"  rate limited, waiting {wait:.1f}s...", file=sys.stderr)
                time.sleep(wait + 0.25)
                continue
            print(f"HTTP {e.code} on {path}: {e.read().decode('utf-8', 'ignore')}", file=sys.stderr)
            raise


def fetch_active_threads(guild_id: str, token: str) -> list[dict]:
    try:
        data = api_request(f"/guilds/{guild_id}/threads/active", token)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # This endpoint only works with a bot token; a user account token
            # can't list currently-active threads in bulk. Archived threads
            # (fetched per-channel below) are unaffected by this.
            print(
                "  note: can't list active threads with a user token (bot-only endpoint); "
                "still-open threads that haven't auto-archived yet will be skipped.",
                file=sys.stderr,
            )
            return []
        raise
    return data.get("threads", [])


def fetch_archived_threads(channel_id: str, token: str, private: bool) -> list[dict]:
    threads = []
    before = None
    kind = "private" if private else "public"
    while True:
        params = {"limit": 100}
        if before:
            params["before"] = before
        try:
            data = api_request(f"/channels/{channel_id}/threads/archived/{kind}", token, params)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                break  # no permission to list private archived threads here
            raise
        batch = data.get("threads", [])
        if not batch:
            break
        threads.extend(batch)
        if not data.get("has_more"):
            break
        before = batch[-1]["thread_metadata"]["archive_timestamp"]
        time.sleep(0.3)
    return threads


def collect_threads_for_channel(
    channel_id: str, guild_id: str | None, token: str, active_threads: list[dict] | None = None
) -> list[dict]:
    threads: dict[str, dict] = {}
    if active_threads is None and guild_id:
        active_threads = fetch_active_threads(guild_id, token)
    for t in active_threads or []:
        if t.get("parent_id") == channel_id:
            threads[t["id"]] = t
    for t in fetch_archived_threads(channel_id, token, private=False):
        threads[t["id"]] = t
    for t in fetch_archived_threads(channel_id, token, private=True):
        threads[t["id"]] = t
    return list(threads.values())


def fetch_channel_messages(channel_id: str, token: str) -> list[dict]:
    messages = []
    before = None
    while True:
        batch = api_request(f"/channels/{channel_id}/messages", token, {"limit": 100, "before": before})
        if not batch:
            break
        messages.extend(batch)
        before = batch[-1]["id"]
        print(f"  fetched {len(messages)} messages so far...", end="\r", file=sys.stderr)
        time.sleep(0.6)  # stay well under the rate limit
    print(file=sys.stderr)
    return messages


def download_attachments(messages: list[dict], out_dir: Path):
    att_dir = out_dir / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    for msg in messages:
        for att in msg.get("attachments", []):
            dest = att_dir / f"{msg['id']}_{att['filename']}"
            if dest.exists():
                continue
            try:
                req = urllib.request.Request(
                    att["url"],
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                        )
                    },
                )
                with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
                    f.write(resp.read())
                print(f"  downloaded {dest.name}", file=sys.stderr)
            except Exception as e:
                print(f"  failed to download {att['url']}: {e}", file=sys.stderr)


FORMAT_EXT = {"json": "json", "txt": "txt", "html": "html"}


def export_channel(
    channel_id: str,
    token: str,
    out_dir: Path,
    with_attachments: bool,
    fmt: str = "json",
    include_threads: bool = True,
    active_threads: list[dict] | None = None,
):
    channel = api_request(f"/channels/{channel_id}", token)
    name = channel.get("name") or channel_id
    print(f"Exporting #{name} ({channel_id})...", file=sys.stderr)

    messages = fetch_channel_messages(channel_id, token)
    messages.sort(key=lambda m: m["id"])  # chronological order

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{name}_{channel_id}.{FORMAT_EXT[fmt]}"

    if fmt == "json":
        write_json(messages, out_file)
    elif fmt == "txt":
        write_txt(messages, out_file)
    elif fmt == "html":
        write_html(messages, out_file, name)

    print(f"  wrote {len(messages)} messages to {out_file}", file=sys.stderr)

    if with_attachments:
        download_attachments(messages, out_dir)

    if include_threads:
        threads = collect_threads_for_channel(channel_id, channel.get("guild_id"), token, active_threads)
        if threads:
            print(f"  found {len(threads)} thread(s) in #{name}", file=sys.stderr)
            thread_dir = out_dir / f"{name}_threads"
            for t in threads:
                tname = t.get("name") or t["id"]
                try:
                    export_channel(t["id"], token, thread_dir, with_attachments, fmt, include_threads=False)
                except Exception as e:
                    print(f"    skipping thread \"{tname}\": {e}", file=sys.stderr)


def export_guild(
    guild_id: str, token: str, out_dir: Path, with_attachments: bool, fmt: str = "json", include_threads: bool = True
):
    channels = api_request(f"/guilds/{guild_id}/channels", token)
    text_channels = [c for c in channels if c.get("type") in (0, 5)]  # 0=text, 5=announcement
    print(f"Found {len(text_channels)} text channels in guild {guild_id}", file=sys.stderr)

    active_threads = fetch_active_threads(guild_id, token) if include_threads else []

    for c in text_channels:
        try:
            export_channel(
                c["id"],
                token,
                out_dir / (channels_guild_name(channels) or guild_id),
                with_attachments,
                fmt,
                include_threads=include_threads,
                active_threads=active_threads,
            )
        except Exception as e:
            print(f"  skipping channel {c.get('name', c['id'])}: {e}", file=sys.stderr)


def channels_guild_name(channels: list[dict]) -> str | None:
    return None  # kept simple; folder falls back to guild id


def main():
    parser = argparse.ArgumentParser(description="Export your own Discord message history locally.")
    parser.add_argument("--channel", help="Export a single channel ID")
    parser.add_argument("--guild", help="Export every text channel in a guild/server ID")
    parser.add_argument("--out", default="export", help="Output directory (default: ./export)")
    parser.add_argument("--with-attachments", action="store_true", help="Also download attached files/images")
    parser.add_argument(
        "--format", choices=["json", "txt", "html"], default="json",
        help="Output format: json (raw, default), txt (readable transcript), or html (styled page)",
    )
    parser.add_argument(
        "--no-threads", action="store_true",
        help="Skip exporting threads (active and archived) under each channel",
    )
    args = parser.parse_args()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Set DISCORD_TOKEN in your environment first.", file=sys.stderr)
        sys.exit(1)
    if not args.channel and not args.guild:
        print("Pass --channel <id> or --guild <id>.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    include_threads = not args.no_threads
    if args.channel:
        export_channel(args.channel, token, out_dir, args.with_attachments, args.format, include_threads)
    if args.guild:
        export_guild(args.guild, token, out_dir, args.with_attachments, args.format, include_threads)


if __name__ == "__main__":
    main()
