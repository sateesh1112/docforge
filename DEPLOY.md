# DocForge — Deploy to GitHub Pages + Render.com

## What you get
- **Frontend**: GitHub Pages (free, your URL: `https://USERNAME.github.io/docforge`)
- **Backend**: Render.com free tier (FastAPI + all PDF tools)

---

## STEP 1 — Push to GitHub

```bash
# In your terminal / Git Bash
git init
git add .
git commit -m "DocForge initial deploy"
git remote add origin https://github.com/YOUR_USERNAME/docforge.git
git push -u origin main
```

---

## STEP 2 — Deploy Backend to Render.com

1. Go to **https://render.com** → Sign up (free)
2. Click **New → Web Service**
3. Connect your GitHub repo `YOUR_USERNAME/docforge`
4. Fill in:
   - **Name**: `docforge-api`
   - **Region**: Singapore (closest to UAE)
   - **Branch**: `main`
   - **Build Command**: (leave blank — render.yaml handles it)
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan**: Free
5. Add **Environment Variables**:
   | Key | Value |
   |-----|-------|
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | any random string |
   | `OPENAI_API_KEY` | your OpenAI key (optional) |
   | `MAX_FILE_SIZE_MB` | `50` |
6. Click **Create Web Service**
7. Wait ~5 mins for build
8. Your API URL: `https://docforge-api.onrender.com`

**Test it:**
```
https://docforge-api.onrender.com/api/v1/health
https://docforge-api.onrender.com/api/docs
```

---

## STEP 3 — Enable GitHub Pages (Frontend)

1. Go to your repo on GitHub
2. **Settings → Pages**
3. Source: **GitHub Actions**
4. Add a secret: **Settings → Secrets → Actions → New secret**
   - Name: `RENDER_BACKEND_URL`
   - Value: `https://docforge-api.onrender.com`
5. Push any change to `main` to trigger deployment
6. Frontend URL: `https://USERNAME.github.io/docforge`

---

## STEP 4 — Connect Frontend to Backend

If you skipped the GitHub secret, you can set the backend URL manually:
1. Open your GitHub Pages URL
2. An orange banner will appear at the top
3. Enter your Render URL and click **Connect**
4. Saved in browser localStorage — done

---

## Free Tier Limits

| Service | Limit |
|---------|-------|
| Render free | 750 hrs/month, sleeps after 15min inactivity |
| File upload | 50 MB max |
| File retention | 2 hours (auto-deleted) |
| LibreOffice | Not available (too large for free tier) |
| OCR / Compress / Merge | ✅ All work |
| AI features | ✅ Works (needs OpenAI key) |

**Upgrade to Render Starter ($7/mo)** to get no sleep, persistent disk, and LibreOffice.

---

## Upgrade: Add LibreOffice on Render (paid tier)

In `render.yaml`, the build command already includes LibreOffice install.
On free tier it's excluded due to 750MB size limit.
On paid tier it installs automatically.

---

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env   # edit as needed
uvicorn app.main:app --reload --port 8000
```

Open: http://localhost:8000/api/docs
