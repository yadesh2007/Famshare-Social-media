# FamShare - Social Media DBMS Project

## Features
- User registration and login
- Feed page
- Create, edit, delete posts
- Photo and video uploads
- Likes and comments
- Follow/unfollow system
- User profiles
- Search users and posts
- AI tools using offline Ollama
- Admin dashboard

## Requirements
- Python 3.10+
- Flask
- SQLite
- requests
- python-dotenv
- Werkzeug

## Install
```bash
pip install -r requirements.txt
```

## Deploy
1. Push this project to GitHub.
2. Open Render and create a new Blueprint from the GitHub repo.
3. Render will read `render.yaml`, install `requirements.txt`, create `SECRET_KEY`, and start the app.
4. Use the Render `https://...onrender.com` URL for browser location/SOS access.
