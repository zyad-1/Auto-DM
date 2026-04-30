# Instagram Comment-to-DM Automation Tool

Automate Instagram comment replies and direct messages based on keywords — ManyChat-style, built with the **official Instagram Graph API**.

When a user comments a specific keyword on a chosen Instagram post, this tool automatically:
1. **Replies** to the comment publicly
2. **Sends a DM** to the commenter privately

---

## Table of Contents
- [Instagram API Setup](#instagram-api-setup)
- [Local Development](#local-development)
- [Deployment](#deployment)
- [API Reference](#api-reference)
- [DM Limitations](#dm-limitations)

---

## Instagram API Setup

> **Complete this section before running the app.** You need a Facebook Developer App connected to an Instagram Business account.

### Step 1 — Convert to Business / Creator Account
1. Open Instagram → Settings → Account → Switch to Professional Account
2. Choose **Business** (recommended) or **Creator**
3. Connect a **Facebook Page** to the Instagram account

### Step 2 — Create a Facebook Developer App
1. Go to [developers.facebook.com](https://developers.facebook.com) and log in
2. Click **My Apps → Create App**
3. Choose app type: **Business**
4. Give it a name and click **Create App**

### Step 3 — Add Instagram Graph API
1. In your app dashboard, click **Add Product**
2. Find **Instagram Graph API** and click **Set Up**
3. Under **Settings → Basic**, note your **App Secret** (you'll need it for webhook verification)

### Step 4 — Request Permissions
1. Go to **App Review → Permissions and Features**
2. Request these permissions:
   - `instagram_manage_comments` — to read and reply to comments
   - `instagram_manage_messages` — to send DMs *(see [DM Limitations](#dm-limitations))*
   - `pages_manage_metadata` — to subscribe to webhooks
   - `pages_show_list` — to list pages

### Step 5 — Generate a Long-Lived Access Token
1. Go to **[Graph API Explorer](https://developers.facebook.com/tools/explorer/)**
2. Select your app and request a **User Access Token** with the permissions above
3. Click **Generate Access Token** and authorize
4. This gives you a **short-lived token** (~1 hour). Exchange it for a **long-lived token** (~60 days):

```bash
curl -X GET "https://graph.facebook.com/v19.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=YOUR_APP_ID&\
client_secret=YOUR_APP_SECRET&\
fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

5. Save the returned `access_token` — it lasts **60 days**

**Refreshing the token** (before it expires):
```bash
curl -X GET "https://graph.facebook.com/v19.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=YOUR_APP_ID&\
client_secret=YOUR_APP_SECRET&\
fb_exchange_token=YOUR_CURRENT_LONG_LIVED_TOKEN"
```

### Step 6 — Get Your IDs
1. In the Graph API Explorer, query: `GET /me/accounts` → get your **Page ID**
2. Then query: `GET /{PAGE_ID}?fields=instagram_business_account` → get your **Instagram Business Account ID**

### Step 7 — Configure the Webhook
1. In your Facebook App dashboard, go to **Webhooks → Add Product → Webhooks**
2. Click **Subscribe to this object** for **Instagram**
3. Set the **Callback URL** to: `https://your-domain.com/webhook/instagram`
4. Set the **Verify Token** to the same value as `WEBHOOK_VERIFY_TOKEN` in your `.env`
5. Subscribe to the **comments** field

### Step 8 — Get a Post ID
1. In Graph API Explorer, query: `GET /{IG_ACCOUNT_ID}/media`
2. This returns a list of your posts with their IDs
3. Use the post ID when creating a campaign in the dashboard

---

## Local Development

### Prerequisites
- Python 3.10+
- pip

### Setup
```bash
# Clone the repo
git clone <your-repo-url>
cd DmAutomation

# Create .env from template
cp .env.example .env
# Edit .env with your credentials

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/dashboard](http://localhost:8000/dashboard) in your browser.

---

## Deployment

### Docker
```bash
docker build -t dm-automation .
docker run -p 8000:8000 --env-file .env dm-automation
```

### Railway
1. Push your code to a GitHub repo
2. Go to [railway.app](https://railway.app) and create a new project from the repo
3. Add your environment variables in Railway's dashboard
4. Railway will auto-detect the `railway.toml` and deploy

Health check endpoint: `GET /health` → `{"status": "ok"}`

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/dashboard` | Web dashboard |
| GET | `/api/config` | Get config (masked token) |
| POST | `/api/config` | Save credentials |
| GET | `/api/campaigns` | List campaigns |
| POST | `/api/campaigns` | Create campaign |
| PUT | `/api/campaigns/{id}` | Update campaign |
| DELETE | `/api/campaigns/{id}` | Delete campaign |
| PATCH | `/api/campaigns/{id}/toggle` | Toggle active/inactive |
| POST | `/api/post-preview` | Fetch post preview |
| GET | `/webhook/instagram` | Webhook verification |
| POST | `/webhook/instagram` | Receive comment events |

---

## DM Limitations

> **⚠️ Important:** Instagram DMs via the Graph API have restrictions.

The Instagram Messaging API can only send messages to users who meet one of these conditions:
1. The user has **previously sent a message** to the business account (within the 24-hour messaging window)
2. The app has **approved `instagram_manage_messages` permission** with an approved use case

### How to apply for instagram_manage_messages
1. Go to your Facebook App → **App Review → Permissions and Features**
2. Find `instagram_manage_messages` and click **Request**
3. You'll need to provide:
   - A description of your use case
   - A screencast demonstrating the feature
   - A privacy policy URL
4. Facebook will review (usually 1–5 business days)

Until approved, the DM feature will only work for users who have messaged your business first. Comment replies will still work normally.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `INSTAGRAM_ACCESS_TOKEN` | Long-lived User Access Token |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Instagram Business Account ID |
| `FACEBOOK_PAGE_ID` | Linked Facebook Page ID |
| `FACEBOOK_APP_SECRET` | App Secret for webhook signature validation |
| `WEBHOOK_VERIFY_TOKEN` | Your chosen webhook verification string |
| `DATABASE_URL` | Database connection string (default: `sqlite:///./app.db`) |
