# Spotify Setup Guide

Connect FiestaBoard to your Spotify account to show what's playing, how far through it you are, and what's up next.

## Overview

**What it does:**

- Shows the track or podcast episode playing on your Spotify account, on any device
- Shows the time and a progress bar, the device, shuffle and repeat, and the playlist or album it's playing from
- Lists the next tracks in your queue
- Shows the last track you played when nothing is playing

**Prerequisites:**

- A Spotify account that has been added to FiestaBoard's Spotify app (see below).
- A FiestaBoard version that can connect accounts (the plugin's settings have an **Account connection** section).
- Open FiestaBoard by its local address, such as `http://192.168.1.50:4420`, when you sign in.

FiestaBoard only reads your playback. It can't play, pause, skip, or change anything in your account.

> **Spotify accounts are added by hand for now.** FiestaBoard's Spotify app is in Spotify's *Development Mode*. Spotify only lets accounts that the app's owner has added by email sign in to an app in that mode, up to five of them, and it does not offer a wider mode to open-source projects. If your account hasn't been added, signing in appears to work but the plugin then shows "Spotify refused access (403)".

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI:

1. Go to **Integrations**
2. Find **Spotify** and toggle it **On**

### 2. Sign in to Spotify

1. Click **Configure**
2. In **Account connection** at the top of the settings, press **Sign in with Spotify**
3. Spotify asks you to sign in and agree to let FiestaBoard see what you're playing and what you've played recently. Press **Agree**
4. On the way back you pass through `fiestaboard.app`. The first time, it shows your board's address and asks you to confirm it: check that it's the address you use for FiestaBoard and press **Continue to my board**
5. You land back on **Integrations** with Spotify connected

There is nothing to copy or paste: the plugin brings its own Spotify app.

Optional settings:

- **Show Last Played:** show the last track when nothing is playing (on by default)
- **Show Up Next:** fetch your queue for the up-next variables (on by default)
- **Tidy Track Titles:** drop `- Remastered 2011` and `(feat. ...)` from titles (on by default)
- **Refresh Interval:** how often to check Spotify, 10 to 300 seconds (default 15)

More about what you see while connecting: [Connecting Accounts](https://fiestaboard.app/docs/features/connecting-accounts).

### 3. Create a Board Template

Create a page from the plugin's demo, or add variables to your own page. Center-align the lines:

```jinja
{{spotify.state_tile}} {{spotify.headline}}
{{spotify.title}}
{{spotify.artist}}
{{spotify.album}}
{{spotify.time_line}}
{{spotify.progress_bar}}
```

On a Note, try:

```jinja
{{spotify.title}}
{{spotify.artist}}
{{spotify.state_tile}} {{spotify.time_line}}
```

### 4. View on Your Board

Play something on Spotify on any device. The board updates on the next refresh (every 15 seconds by default). Progress and time are as of that refresh.

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{spotify.headline}}` | `NOW PLAYING`, `PAUSED`, `LAST PLAYED`, `AD BREAK` or `NOTHING PLAYING` | `NOW PLAYING` |
| `{{spotify.title}}` | Track or episode title | `NEON HARBOR` |
| `{{spotify.artist}}` | Artists; the show for a podcast | `PAPER LANTERNS` |
| `{{spotify.album}}` | Album; the publisher for a podcast | `MIDNIGHT FERRY` |
| `{{spotify.title_artist}}` | Title and artist on one line | `LOW TIDE - JUNE ARCADE` |
| `{{spotify.item_type}}` | `TRACK`, `EPISODE` or `AD` | `TRACK` |
| `{{spotify.last_played_ago}}` | When the last track finished, if nothing is playing | `12M AGO` |
| `{{spotify.is_playing}}` | Playing right now | `true` |
| `{{spotify.state}}` | `PLAYING`, `PAUSED` or `STOPPED` | `PLAYING` |
| `{{spotify.state_tile}}` | Green, yellow or red tile for the state | `{66}` |
| `{{spotify.progress}}` | Position | `1:23` |
| `{{spotify.duration}}` | Length | `3:45` |
| `{{spotify.time_line}}` | Position and length | `1:23 / 3:45` |
| `{{spotify.remaining}}` | Time left | `-2:22` |
| `{{spotify.progress_percent}}` | How far through, 0-100 | `37` |
| `{{spotify.progress_bar}}` | Bar as wide as the board | `{66}{66}{66}---` |
| `{{spotify.progress_ms}}` | Position in milliseconds | `83000` |
| `{{spotify.duration_ms}}` | Length in milliseconds | `225000` |
| `{{spotify.device_name}}` | Device playing | `KITCHEN SPEAKER` |
| `{{spotify.device_type}}` | Kind of device | `SPEAKER` |
| `{{spotify.volume_percent}}` | Device volume | `65` |
| `{{spotify.shuffle}}` | Shuffle on | `false` |
| `{{spotify.repeat}}` | `OFF`, `ALL` or `ONE` | `ALL` |
| `{{spotify.modes}}` | Shuffle and repeat together | `SHUFFLE REPEAT ALL` |
| `{{spotify.context_type}}` | `PLAYLIST`, `ALBUM`, `ARTIST`, `PODCAST` or `LIKED SONGS` | `PLAYLIST` |
| `{{spotify.context_name}}` | Its name | `SUNDAY COFFEE` |
| `{{spotify.next_title}}` | Next track | `LOW TIDE` |
| `{{spotify.next_artist}}` | Next artist | `JUNE ARCADE` |
| `{{spotify.next_line}}` | Next track and artist | `LOW TIDE - JUNE ARCADE` |
| `{{spotify.queue_count}}` | Upcoming tracks known, up to 5 | `5` |
| `{{spotify.queue.N.title}}`, `.artist`, `.line` | Queue entry N (0-4) | `SALT AND STATIC` |

## Configuration Reference

| Setting | Required | Default | Description |
|---------|----------|---------|-------------|
| Show Last Played | No | On | Show the last played track when nothing is playing |
| Show Up Next | No | On | Fetch your queue (one extra request when the track changes) |
| Tidy Track Titles | No | On | Drop remaster and featuring notes from track titles |
| Refresh Interval (seconds) | No | 15 | How often to check Spotify (10-300) |

The connection itself is made with the **Sign in with Spotify** button, not a setting. The plugin asks Spotify for three read-only permissions: `user-read-playback-state`, `user-read-currently-playing` and `user-read-recently-played`.

**Environment variables:** none.

## Troubleshooting

**"Not connected to Spotify"**

- Press **Sign in with Spotify** (or **Reconnect**) in the plugin's **Account connection** section.
- **Reconnect needed** means Spotify stopped accepting the saved sign-in, usually because you removed the app's access in your Spotify account or changed your password.

**"Spotify refused access (403)"**

- Your Spotify account hasn't been added to FiestaBoard's Spotify app yet. See the note at the top of this guide.

**Spotify shows "INVALID_CLIENT"** or **"The provider rejected the sign-in"**

- Something is wrong on FiestaBoard's side of the Spotify app, not yours. Please [open an issue](https://github.com/Fiestaboard/fiestaboard-plugin--spotify/issues).

**"Spotify rejected the sign-in (401)"** or **"Reconnect needed"**

- You removed the app's access in your Spotify account, or Spotify revoked it. Press **Reconnect**.

**"Spotify rate limit reached"**

- The plugin waits as long as Spotify asks before trying again and keeps showing the last track meanwhile (for up to two minutes). If it happens often, raise the refresh interval or turn off **Show Up Next**. Spotify counts requests from every board using FiestaBoard's Spotify app together.

**The board shows LAST PLAYED although music is playing**

- Spotify only reports playback on your account's active device. Private sessions and some devices (for example, some smart speakers playing through their own service) aren't reported.

**The playlist name is empty**

- Spotify doesn't share the names of its own playlists (Discover Weekly, Daily Mix, editorial playlists) with apps.

**"This FiestaBoard version cannot sign in to Spotify"**

- Update FiestaBoard to a version with account connection.

**Plugin shows "Not Available"**

- The error next to the plugin on the Integrations page says what went wrong. For more detail, check the logs: `docker compose logs -f`
