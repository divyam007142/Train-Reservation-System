"""SQLite database operations for Railway Reservation System"""
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'railway.db')

def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Trains table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_number TEXT UNIQUE NOT NULL,
            train_name TEXT NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            total_seats INTEGER NOT NULL,
            available_seats INTEGER NOT NULL,
            fare REAL NOT NULL,
            departure_time TEXT,
            arrival_time TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pnr TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            train_id INTEGER NOT NULL,
            passenger_name TEXT NOT NULL,
            passenger_age INTEGER NOT NULL,
            passenger_gender TEXT NOT NULL,
            passenger_phone TEXT NOT NULL,
            seat_number INTEGER,
            booking_status TEXT NOT NULL,
            booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (train_id) REFERENCES trains (id)
        )
    ''')
    
    # Waiting list table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waiting_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            passenger_name TEXT NOT NULL,
            passenger_age INTEGER NOT NULL,
            passenger_gender TEXT NOT NULL,
            passenger_phone TEXT NOT NULL,
            position INTEGER NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (train_id) REFERENCES trains (id)
        )
    ''')
    
    # Create default admin if not exists
    cursor.execute("SELECT * FROM users WHERE username = ?", ('admin',))
    if not cursor.fetchone():
        from passlib.hash import bcrypt
        hashed_password = bcrypt.hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
            ('admin', hashed_password, 'admin', 'System Administrator')
        )
    
    conn.commit()
    conn.close()

def dict_from_row(row):
    """Convert sqlite3.Row to dictionary"""
    return dict(zip(row.keys(), row)) if row else None
