# World Cup 2026 Pools — Private Web App

This is a private Streamlit web app for running the World Cup 2026 pools game.

## What it does

- Entrants submit nation and player picks using an entry code.
- KO questions can be opened later.
- Admin can lock/unlock submissions.
- Admin can enter nation, player, KO and bet scoring.
- Leaderboard calculates automatically.
- Data can be backed up and restored as a ZIP.
- Patrick Hoban's completed picks are included as the first entry.

## Local preview

Install Python 3.10 or newer, then run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Default local passwords if secrets are not configured:

- Admin password: `admin`
- Entry code: `worldcup`
- Leaderboard password: `leaderboard`

Change these before sharing.

## Deploy to Streamlit Community Cloud

1. Create a GitHub account if you do not have one.
2. Create a new private GitHub repository.
3. Upload all files in this folder to that repository.
4. Go to Streamlit Community Cloud and create a new app from that repository.
5. Set the main file path to `app.py`.
6. In Streamlit app settings, add these secrets:

```toml
ADMIN_PASSWORD = "your-secure-admin-password"
ENTRY_CODE = "your-player-entry-code"
PLAYER_VIEW_PASSWORD = "your-leaderboard-password"
```

7. Deploy the app and share the private Streamlit link plus the entry code with players.

## Important hosting note

Streamlit Community Cloud is convenient, but file-based data can be reset after app restarts or redeploys. Use **Admin > Backups > Download full data backup** regularly, especially after collecting entries and after updating scores.

For a more permanent database-backed version later, move the CSV data to Google Sheets, Airtable, Supabase or another hosted database.
