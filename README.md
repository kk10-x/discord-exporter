# discord-exporter

Export your own Discord message history (channels or entire servers) to local files, using your own account's API token — no bot invite, no notification to other members.

Useful before deleting/leaving a server you want to keep a copy of.

## Quick start

```powershell
$env:DISCORD_TOKEN="paste_your_token_here"
python discord_export.py --guild YOUR_SERVER_ID --with-attachments --format html --out my_export
```

Full instructions (getting your token, getting server/channel IDs, all options) are in the docstring at the top of [`discord_export.py`](discord_export.py).

## Known limitations

- Active and archived threads under each text/announcement channel are exported into a `<channel>_threads` subfolder (use `--no-threads` to skip). Forum channels themselves are not yet handled.
- Voice channel text chat is not included.
- Embeds (link previews), stickers, and who-reacted-with-what are not exported/rendered.
- DMs aren't bulk-exportable, but you can pass a DM's channel ID to `--channel` directly.

## A note on ToS

This uses your personal account token to call the API directly (the same approach tools like DiscordChatExporter use), which is technically outside Discord's terms on client automation. It only performs read requests against content you already have access to — nothing is posted, and no one is notified.
