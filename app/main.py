# app/main.py
from fastapi import FastAPI
from app.api import sessions, pose_analysis

app = FastAPI(title="Interview Backend")

# include routers
app.include_router(sessions.router)
app.include_router(pose_analysis.router)

@app.get("/")
def root():
    return {"ok": True}
