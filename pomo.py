import sqlite3
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware


DB_NAME = "jobs.db"

# ---------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_minutes REAL,
                status TEXT NOT NULL DEFAULT 'running'
            )
        """)
        conn.commit()

init_db()

# ---------------------------------------------------------
# FastAPI App & Models
# ---------------------------------------------------------
app = FastAPI(title="Simple Timer App Backend")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, or specific ports like ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],  # Ensures GET, POST, PUT, DELETE, and OPTIONS are allowed
    allow_headers=["*"],
)
VALID_GOALS = {"Jobhunt", "Job Apply", "Study", "Improve App"}

class TimerStartRequest(BaseModel):
    goal: str = "Study"  # Defaults to Study if not specified

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.post("/timers/start")
def start_timer(payload: TimerStartRequest):
    """Starts a new timer session."""
    if payload.goal not in VALID_GOALS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid goal. Must be one of {list(VALID_GOALS)}"
        )
    
    start_time_str = datetime.utcnow().isoformat()
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO timers (goal, start_time, status) VALUES (?, ?, ?)",
            (payload.goal, start_time_str, "running")
        )
        conn.commit()
        timer_id = cursor.lastrowid

    return {
        "message": "Timer started successfully",
        "timer_id": timer_id,
        "goal": payload.goal,
        "start_time": start_time_str,
        "default_duration_minutes": 25
    }


@app.post("/timers/{timer_id}/stop")
def stop_timer(timer_id: int):
    """Stops an active timer and calculates the elapsed duration."""
    end_time = datetime.utcnow()
    end_time_str = end_time.isoformat()

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Check if the timer exists and is actually running
        cursor.execute("SELECT start_time, status FROM timers WHERE id = ?", (timer_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Timer not found.")
        
        start_time_str, status = row
        if status == "completed":
            raise HTTPException(status_code=400, detail="Timer has already been stopped.")
        
        # Calculate precise elapsed duration
        start_time = datetime.fromisoformat(start_time_str)
        elapsed_seconds = (end_time - start_time).total_seconds()
        duration_minutes = round(elapsed_seconds / 60, 2)
        
        # Update the record
        cursor.execute(
            """
            UPDATE timers 
            SET end_time = ?, duration_minutes = ?, status = 'completed' 
            WHERE id = ?
            """,
            (end_time_str, duration_minutes, timer_id)
        )
        conn.commit()

    return {
        "message": "Timer stopped successfully",
        "timer_id": timer_id,
        "end_time": end_time_str,
        "duration_minutes": duration_minutes
    }


@app.get("/timers/active")
def get_active_timers():
    """Fetches currently running timers."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timers WHERE status = 'running'")
        rows = cursor.fetchall()
        
    return [dict(row) for row in rows]


@app.get("/timers/history")
def get_timer_history():
    """Fetches all past and present timer sessions."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM timers ORDER BY id DESC")
        rows = cursor.fetchall()
        
    return [dict(row) for row in rows]