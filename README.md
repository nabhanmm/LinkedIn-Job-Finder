# LinkedIn Job Finder — Web App

A Streamlit web app wrapping the LinkedIn job scraper. No Python install needed for users.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — the web app |
| `linkedin_jobs.py` | Your original scraper (unchanged) |
| `requirements.txt` | Python dependencies |

---

## 🚀 Deploy to Streamlit Cloud (Free — Recommended)

### Step 1 — Push to GitHub

```bash
# In the project folder
git init
git add app.py linkedin_jobs.py requirements.txt README.md
git commit -m "LinkedIn Job Finder web app"

# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/linkedin-job-finder.git
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub
2. Click **"New app"**
3. Select your repo → branch: `main` → main file: `app.py`
4. Click **Deploy**

Your app will be live at:
```
https://YOUR_USERNAME-linkedin-job-finder-app-XXXX.streamlit.app
```

That's it. Share the URL with anyone — they use it in a browser, no installs needed.

---

## 💻 Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501

---

## 🔧 Alternative Deployments

### Render (Free tier, always-on)
1. Push to GitHub (same as above)
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo
4. Set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
5. Deploy

### Railway
1. Push to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

### Run on a VPS / Home Server
```bash
# Install
pip install -r requirements.txt

# Run in background
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &

# Access at http://YOUR_SERVER_IP:8501
```

---

## ⚠️ Known Limitations on Cloud

- LinkedIn may **rate-limit** or temporarily block the server IP if many people use the app simultaneously. Adding delays (already present in the code) helps.
- The filesystem on Streamlit Cloud is **ephemeral** — `seen_jobs.json` resets on each deployment. The web app always shows fresh results without deduplication against previous runs.
- For high usage, consider adding a **proxy rotation layer** (Bright Data, Oxylabs) in `safe_get()`.

---

## 📧 Email Setup

In the sidebar, expand **Email Results**:
- **From Email:** Your Gmail address
- **App Password:** Generate at `myaccount.google.com → Security → 2-Step Verification → App passwords`
- **To Email:** Where to receive the Excel file

Do NOT use your regular Gmail password — Google requires App Passwords for SMTP.
