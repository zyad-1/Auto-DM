# Instagram API Setup Guide

Follow these steps to connect your Instagram Business or Creator account to the DM Automation tool.

## Prerequisites

- A Facebook Page linked to your Instagram Business/Creator account
- Admin access to the Facebook Page
- A Meta Developer account (free)

---

## Step 1: Create a Meta App

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Click **Create App**
3. Select **Other** → **Business** type
4. Give it a name (e.g. "DM Automation")
5. Click **Create App**

## Step 2: Add Required Products

In your app dashboard, add these products:

1. **Facebook Login for Business** → Click **Set Up**
2. **Instagram Graph API** → Click **Set Up**

## Step 3: Configure Facebook Login

1. Go to **Facebook Login** → **Settings** in the left sidebar
2. Under **Valid OAuth Redirect URIs**, add:
   ```
   http://127.0.0.1:8888/auth/instagram/callback
   ```
   > For production (Fly.io), also add:
   > ```
   > https://dm-auto.fly.dev/auth/instagram/callback
   > ```
3. Click **Save Changes**

## Step 4: Copy App Credentials

1. Go to **Settings** → **Basic** in the left sidebar
2. Copy **App ID** → paste into `.env` as `META_APP_ID`
3. Copy **App Secret** → paste into `.env` as `META_APP_SECRET`

Your `.env` should look like:
```env
META_APP_ID=123456789012345
META_APP_SECRET=abcdef1234567890abcdef1234567890
REDIRECT_URI=http://127.0.0.1:8888/auth/instagram/callback
```

## Step 5: Request Permissions

Go to **App Review** → **Permissions and Features** and request:

| Permission | Required | Purpose |
|-----------|----------|---------|
| `instagram_basic` | ✅ | Read IG profile info |
| `instagram_manage_comments` | ✅ | Read & reply to comments |
| `instagram_manage_messages` | ✅ | Send DMs |
| `pages_show_list` | ✅ | List user's Facebook Pages |
| `pages_read_engagement` | ✅ | Read page data |
| `business_management` | ✅ | Access business features |

> **Note:** For development/testing, these permissions are auto-granted for
> users who have a role on the app. You only need App Review for production.

## Step 6: Add Test Users (Development)

1. Go to **App Roles** → **Roles**
2. Click **Add People**
3. Add yourself and any testers as **Testers** or **Developers**
4. Each user must accept the invitation at [developers.facebook.com/requests](https://developers.facebook.com/requests)

## Step 7: Connect in the Dashboard

1. Start your app: `uvicorn main:app --host 0.0.0.0 --port 8888`
2. Go to `http://127.0.0.1:8888/dashboard?tab=settings`
3. Click the **Connect with Instagram** button
4. Log in with your Facebook account
5. Grant all requested permissions
6. Select the Facebook Page connected to your Instagram
7. Done! Your credentials are auto-saved.

---

## Token Management

- **Long-lived tokens** are valid for **60 days**
- The dashboard shows a **yellow warning** when the token expires within 7 days
- The dashboard shows a **red alert** when the token has expired
- Click **Refresh Token** in Settings to extend for another 60 days
- You can also manually paste a token in the Manual Credentials section

## Troubleshooting

### "No Facebook Pages found"
→ Make sure your Facebook account has at least one Page

### "No Instagram Business Account linked to this Page"
→ Go to your Facebook Page → Settings → Instagram → Connect your IG account

### "Invalid OAuth state"
→ Try clicking "Connect with Instagram" again (CSRF token expired)

### Token expired / Automations paused
→ Click "Refresh Token" or "Reconnect Now" in Settings

---

## Production Deployment (Fly.io)

When deploying to Fly.io:

1. Update `.env`:
   ```env
   REDIRECT_URI=https://dm-auto.fly.dev/auth/instagram/callback
   ```

2. Add the production redirect URI in Facebook Login → Settings:
   ```
   https://dm-auto.fly.dev/auth/instagram/callback
   ```

3. Submit your app for **App Review** to get permissions approved for all users
