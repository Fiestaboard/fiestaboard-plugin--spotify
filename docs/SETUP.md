# Spotify Setup Guide

Connect FiestaBoard to your Spotify account to show what's playing, how far through it you are, and what's up next.

## Overview

**What it does:**

- Shows the track or podcast episode playing on your Spotify account, on any device
- Shows the time and a progress bar, the device, shuffle and repeat, and the playlist or album it's playing from
- Lists the next tracks in your queue
- Shows the last track you played when nothing is playing

**Prerequisites:**

- A **Spotify Premium** account. Since February 2026, Spotify requires the owner of a developer app to have Premium, and the app stops working without it.
- About 10 minutes to create your own app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). It's free. Each person uses their own app; FiestaBoard doesn't ship one.
- A FiestaBoard version that can connect accounts (the plugin's settings have an **Account connection** section).
- Open FiestaBoard by its local address, such as `http://192.168.1.50:4420`, when you connect.

FiestaBoard only reads your playback. It can't play, pause, skip, or change anything in your account.

## Quick Setup

### 1. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in with your Spotify account. Accept the developer terms if this is your first visit.
2. Press **Create app** and fill in:
   - **App name:** anything, such as `FiestaBoard`
   - **App description:** anything, such as `Now playing on my split-flap board`
   - **Website:** leave empty
   - **Redirect URIs:** paste exactly the address below, then press **Add**:

     ```text
     https://fiestaboard.app/auth/oauth/redirect.html
     ```

   - **Which API/SDKs are you planning to use?** tick **Web API** only
3. Tick the box to agree to Spotify's Developer Terms of Service and Design Guidelines, then press **Save**.
4. On the app's page, open **Settings** and copy the **Client ID** (32 letters and numbers). You don't need the client secret: FiestaBoard signs in without one.

Spotify lets each developer account have only **one** app in Development Mode. If you already have one, you can use it: open its **Settings**, press **Edit**, add the redirect URI above under **Redirect URIs**, make sure **Web API** is ticked, and **Save**.

**Using a different Spotify account than the one that owns the app?** New apps are in *Development Mode*, which only lets the owner and up to 5 listed users sign in. Open the app, go to **Settings** > **User Management**, and add the other account's name and the email address it signs in to Spotify with. Without this, Spotify answers `403` and the plugin tells you so.

### 2. Enable the Plugin

In the FiestaBoard web UI:

1. Go to **Integrations**
2. Find **Spotify** and toggle it **On**

### 3. Configure Spotify

1. Click **Configure**
2. Paste your **Client ID** and click **Save Changes**
3. In **Account connection** at the top of the settings, press **Connect to Spotify**
4. Spotify asks you to sign in and agree to let your app see what you're playing and what you've played recently. Press **Agree**
5. On the way back you pass through `fiestaboard.app`. The first time, it shows your board's address and asks you to confirm it: check that it's the address you use for FiestaBoard and press **Continue to my board**
6. You land back on **Integrations** with Spotify connected

Optional settings:

- **Show Last Played:** show the last track when nothing is playing (on by default)
- **Show Up Next:** fetch your queue for the up-next variables (on by default)
- **Tidy Track Titles:** drop `- Remastered 2011` and `(feat. ...)` from titles (on by default)
- **Refresh Interval:** how often to check Spotify, 10 to 300 seconds (default 15)

More about what you see while connecting: [Connecting Accounts](https://fiestaboard.app/docs/features/connecting-accounts).

### 4. Create a Board Template

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

### 5. View on Your Board

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
| Client ID | Yes | | From your app's **Settings** page in the Spotify Developer Dashboard |
| Show Last Played | No | On | Show the last played track when nothing is playing |
| Show Up Next | No | On | Fetch your queue (one extra request when the track changes) |
| Tidy Track Titles | No | On | Drop remaster and featuring notes from track titles |
| Refresh Interval (seconds) | No | 15 | How often to check Spotify (10-300) |

The connection itself is made with the **Connect** button, not a setting. The plugin asks Spotify for three read-only permissions: `user-read-playback-state`, `user-read-currently-playing` and `user-read-recently-played`.

**Environment variables:** none. The Client ID must be entered in the plugin settings.

## Troubleshooting

**"Not connected to Spotify"**

- Press **Connect to Spotify** (or **Reconnect**) in the plugin's **Account connection** section. If the button is greyed out, enter the Client ID and **Save Changes** first.
- **Reconnect needed** means Spotify stopped accepting the saved sign-in, usually because you removed the app's access in your Spotify account or changed your password.

**Spotify shows "INVALID_CLIENT: Invalid redirect URI"**

- The app's redirect URI must be exactly `https://fiestaboard.app/auth/oauth/redirect.html`, with `https`, no trailing slash, and no spaces. Fix it in the app's **Settings**, **Save**, and connect again.

**Spotify shows "INVALID_CLIENT: Invalid client"** or **"The provider rejected the sign-in"**

- The Client ID doesn't match your app. Copy it again from the app's **Settings** page. Don't paste the client secret.

**"Spotify refused access (403)"**

- The Spotify account you connected isn't allowed to use the app. Add it under **Settings** > **User Management** in the Developer Dashboard, or connect with the account that owns the app.
- The app's owner needs Spotify Premium. If the Premium subscription lapsed, Spotify blocks the app.

**"Spotify rejected the sign-in (401)"** or **"Reconnect needed"**

- You removed the app's access in your Spotify account, or Spotify revoked it. Press **Reconnect**.

**"Spotify rate limit reached"**

- The plugin waits as long as Spotify asks before trying again and keeps showing the last track meanwhile (for up to two minutes). If it happens often, raise the refresh interval or turn off **Show Up Next**. Other apps using the same Client ID count toward the same limit.

**The board shows LAST PLAYED although music is playing**

- Spotify only reports playback on your account's active device. Private sessions and some devices (for example, some smart speakers playing through their own service) aren't reported.

**The playlist name is empty**

- Spotify doesn't share the names of its own playlists (Discover Weekly, Daily Mix, editorial playlists) with apps.

**"This FiestaBoard version cannot sign in to Spotify"**

- Update FiestaBoard to a version with account connection.

**Plugin shows "Not Available"**

- The error next to the plugin on the Integrations page says what went wrong. For more detail, check the logs: `docker compose logs -f`
