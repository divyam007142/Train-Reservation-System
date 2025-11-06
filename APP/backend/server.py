from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
import random
import string

from database import init_database, get_db_connection, dict_from_row
from auth import hash_password, verify_password, create_access_token, decode_token
from data_structures import LinkedList, Queue

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Initialize database
init_database()

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Global data structures for efficient operations
trains_linked_list = LinkedList()  # Store trains in linked list
waiting_queues = {}  # Dictionary of train_id -> Queue for waiting lists
passenger_cache = {}  # Dictionary for quick passenger lookups

def sync_trains_to_linked_list():
    """Load trains from database into linked list"""
    global trains_linked_list
    trains_linked_list = LinkedList()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trains ORDER BY id")
    trains = cursor.fetchall()
    conn.close()
    
    for train_row in trains:
        train_dict = dict_from_row(train_row)
        trains_linked_list.insert_at_end(train_dict)
        
        # Initialize waiting queue for this train if not exists
        if train_dict['id'] not in waiting_queues:
            waiting_queues[train_dict['id']] = Queue()
    
    return len(trains)

def sync_waiting_lists():
    """Load waiting lists from database into queues"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM waiting_list ORDER BY train_id, position")
    waiting_list = cursor.fetchall()
    conn.close()
    
    for w_row in waiting_list:
        w_dict = dict_from_row(w_row)
        train_id = w_dict['train_id']
        
        if train_id not in waiting_queues:
            waiting_queues[train_id] = Queue()
        
        waiting_queues[train_id].enqueue(w_dict)

# Initialize data structures on startup
sync_trains_to_linked_list()
sync_waiting_lists()

@app.on_event("startup")
async def startup_event():
    """Sync data structures on startup"""
    sync_trains_to_linked_list()
    sync_waiting_lists()
    logging.info(f"Data structures initialized: {trains_linked_list.get_all().__len__()} trains loaded")

# Pydantic Models
class UserRegister(BaseModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "passenger"

class UserLogin(BaseModel):
    username: str
    password: str

class TrainCreate(BaseModel):
    train_number: str
    train_name: str
    source: str
    destination: str
    total_seats: int
    fare: float
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None

class TrainUpdate(BaseModel):
    train_name: Optional[str] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    total_seats: Optional[int] = None
    fare: Optional[float] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None

class BookingCreate(BaseModel):
    train_id: int
    passenger_name: str
    passenger_age: int
    passenger_gender: str
    passenger_phone: str

# Helper functions
def generate_pnr() -> str:
    """Generate unique PNR number"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

def get_current_user(authorization: Optional[str] = Header(None)):
    """Verify JWT token and return user"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(' ')[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload

# Authentication Routes
@api_router.post("/auth/register")
async def register(user: UserRegister):
    """Register new user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        hashed_pwd = hash_password(user.password)
        cursor.execute(
            """INSERT INTO users (username, password, role, full_name, email, phone) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user.username, hashed_pwd, user.role, user.full_name, user.email, user.phone)
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        return {
            "message": "User registered successfully",
            "user_id": user_id,
            "username": user.username
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Username already exists or invalid data")
    finally:
        conn.close()

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    """Login user and return JWT token"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE username = ?", (credentials.username,))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    user = dict_from_row(user_row)
    
    if not verify_password(credentials.password, user['password']):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_access_token(data={
        "user_id": user['id'],
        "username": user['username'],
        "role": user['role']
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "role": user['role'],
            "full_name": user['full_name']
        }
    }

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, full_name, email, phone FROM users WHERE id = ?", 
                   (current_user['user_id'],))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    
    return dict_from_row(user_row)

# Train Management Routes
@api_router.post("/trains")
async def create_train(train: TrainCreate, current_user: dict = Depends(get_current_user)):
    """Create new train and add to LinkedList (Admin only)"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO trains (train_number, train_name, source, destination, 
               total_seats, available_seats, fare, departure_time, arrival_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (train.train_number, train.train_name, train.source, train.destination,
             train.total_seats, train.total_seats, train.fare, 
             train.departure_time, train.arrival_time)
        )
        conn.commit()
        train_id = cursor.lastrowid
        
        # Add to linked list data structure
        train_dict = {
            'id': train_id,
            'train_number': train.train_number,
            'train_name': train.train_name,
            'source': train.source,
            'destination': train.destination,
            'total_seats': train.total_seats,
            'available_seats': train.total_seats,
            'fare': train.fare,
            'departure_time': train.departure_time,
            'arrival_time': train.arrival_time
        }
        trains_linked_list.insert_at_end(train_dict)
        
        # Initialize waiting queue for this train
        waiting_queues[train_id] = Queue()
        
        return {"message": "Train created and added to LinkedList", "train_id": train_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Train number already exists")
    finally:
        conn.close()

@api_router.get("/trains")
async def get_all_trains():
    """Get all trains using LinkedList data structure"""
    # Use linked list for efficient traversal
    trains = trains_linked_list.get_all()
    
    # Add waiting list count from queue to each train
    for train in trains:
        train_id = train['id']
        if train_id in waiting_queues:
            train['waiting_count'] = waiting_queues[train_id].size()
        else:
            train['waiting_count'] = 0
    
    return trains

@api_router.get("/trains/search")
async def search_trains(source: Optional[str] = None, destination: Optional[str] = None, 
                       train_number: Optional[str] = None):
    """Search trains using LinkedList traversal"""
    all_trains = trains_linked_list.get_all()
    results = []
    
    # Search using linked list traversal
    for train in all_trains:
        match = True
        
        if source and source.lower() not in train['source'].lower():
            match = False
        
        if destination and destination.lower() not in train['destination'].lower():
            match = False
        
        if train_number and train_number not in train['train_number']:
            match = False
        
        if match:
            # Add waiting list info from queue
            if train['id'] in waiting_queues:
                train['waiting_count'] = waiting_queues[train['id']].size()
            else:
                train['waiting_count'] = 0
            results.append(train)
    
    return results

@api_router.get("/trains/{train_id}")
async def get_train(train_id: int):
    """Get train by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trains WHERE id = ?", (train_id,))
    train = cursor.fetchone()
    conn.close()
    
    if not train:
        raise HTTPException(status_code=404, detail="Train not found")
    
    return dict_from_row(train)

@api_router.put("/trains/{train_id}")
async def update_train(train_id: int, train_update: TrainUpdate, 
                      current_user: dict = Depends(get_current_user)):
    """Update train details (Admin only)"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current train data
    cursor.execute("SELECT * FROM trains WHERE id = ?", (train_id,))
    current_train = cursor.fetchone()
    
    if not current_train:
        conn.close()
        raise HTTPException(status_code=404, detail="Train not found")
    
    current_train = dict_from_row(current_train)
    
    # Build update query
    updates = []
    params = []
    
    if train_update.train_name:
        updates.append("train_name = ?")
        params.append(train_update.train_name)
    if train_update.source:
        updates.append("source = ?")
        params.append(train_update.source)
    if train_update.destination:
        updates.append("destination = ?")
        params.append(train_update.destination)
    if train_update.fare:
        updates.append("fare = ?")
        params.append(train_update.fare)
    if train_update.departure_time:
        updates.append("departure_time = ?")
        params.append(train_update.departure_time)
    if train_update.arrival_time:
        updates.append("arrival_time = ?")
        params.append(train_update.arrival_time)
    if train_update.total_seats:
        seat_diff = train_update.total_seats - current_train['total_seats']
        updates.append("total_seats = ?")
        params.append(train_update.total_seats)
        updates.append("available_seats = available_seats + ?")
        params.append(seat_diff)
    
    if not updates:
        conn.close()
        return {"message": "No updates provided"}
    
    params.append(train_id)
    query = f"UPDATE trains SET {', '.join(updates)} WHERE id = ?"
    
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    
    return {"message": "Train updated successfully"}

@api_router.delete("/trains/{train_id}")
async def delete_train(train_id: int, current_user: dict = Depends(get_current_user)):
    """Delete train from database and LinkedList (Admin only)"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM trains WHERE id = ?", (train_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Train not found")
    
    conn.commit()
    conn.close()
    
    # Remove from linked list using delete operation
    trains_linked_list.delete_by_value(
        train_id,
        lambda train, tid: train['id'] == tid
    )
    
    # Remove waiting queue
    if train_id in waiting_queues:
        del waiting_queues[train_id]
    
    return {"message": "Train deleted from LinkedList and database"}

# Booking Routes
@api_router.post("/bookings")
async def create_booking(booking: BookingCreate, current_user: dict = Depends(get_current_user)):
    """Create new booking or add to Queue (waiting list)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check train availability from linked list
    train = trains_linked_list.search(
        booking.train_id,
        lambda t, tid: t['id'] == tid
    )
    
    if not train:
        conn.close()
        raise HTTPException(status_code=404, detail="Train not found in LinkedList")
    
    # Verify with database for consistency
    cursor.execute("SELECT * FROM trains WHERE id = ?", (booking.train_id,))
    train_db = dict_from_row(cursor.fetchone())
    
    if train_db['available_seats'] > 0:
        # Book ticket
        pnr = generate_pnr()
        seat_number = train_db['total_seats'] - train_db['available_seats'] + 1
        
        cursor.execute(
            """INSERT INTO bookings (pnr, user_id, train_id, passenger_name, passenger_age,
               passenger_gender, passenger_phone, seat_number, booking_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pnr, current_user['user_id'], booking.train_id, booking.passenger_name,
             booking.passenger_age, booking.passenger_gender, booking.passenger_phone,
             seat_number, 'confirmed')
        )
        
        # Update available seats in database
        cursor.execute(
            "UPDATE trains SET available_seats = available_seats - 1 WHERE id = ?",
            (booking.train_id,)
        )
        
        # Update linked list
        train['available_seats'] -= 1
        trains_linked_list.update(
            booking.train_id,
            train,
            lambda t, tid: t['id'] == tid
        )
        
        # Cache passenger info in dictionary
        passenger_cache[pnr] = {
            'name': booking.passenger_name,
            'age': booking.passenger_age,
            'gender': booking.passenger_gender,
            'phone': booking.passenger_phone,
            'train_id': booking.train_id,
            'seat': seat_number
        }
        
        conn.commit()
        conn.close()
        
        return {
            "status": "confirmed",
            "pnr": pnr,
            "seat_number": seat_number,
            "message": "Ticket booked (LinkedList updated)"
        }
    else:
        # Add to waiting queue
        if booking.train_id not in waiting_queues:
            waiting_queues[booking.train_id] = Queue()
        
        position = waiting_queues[booking.train_id].size() + 1
        
        waiting_data = {
            'user_id': current_user['user_id'],
            'passenger_name': booking.passenger_name,
            'passenger_age': booking.passenger_age,
            'passenger_gender': booking.passenger_gender,
            'passenger_phone': booking.passenger_phone,
            'position': position
        }
        
        # Enqueue to waiting list
        waiting_queues[booking.train_id].enqueue(waiting_data)
        
        cursor.execute(
            """INSERT INTO waiting_list (train_id, user_id, passenger_name, passenger_age,
               passenger_gender, passenger_phone, position)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (booking.train_id, current_user['user_id'], booking.passenger_name,
             booking.passenger_age, booking.passenger_gender, booking.passenger_phone, position)
        )
        
        conn.commit()
        conn.close()
        
        return {
            "status": "waiting",
            "position": position,
            "message": "No seats. Added to Queue (waiting list)"
        }

@api_router.get("/bookings/my-bookings")
async def get_my_bookings(current_user: dict = Depends(get_current_user)):
    """Get current user's bookings"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT b.*, t.train_number, t.train_name, t.source, t.destination, t.fare,
           t.departure_time, t.arrival_time
           FROM bookings b
           JOIN trains t ON b.train_id = t.id
           WHERE b.user_id = ?
           ORDER BY b.booking_date DESC""",
        (current_user['user_id'],)
    )
    
    bookings = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    
    return bookings

@api_router.get("/bookings/all")
async def get_all_bookings(current_user: dict = Depends(get_current_user)):
    """Get all bookings (Admin only)"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT b.*, t.train_number, t.train_name, u.username, u.full_name
           FROM bookings b
           JOIN trains t ON b.train_id = t.id
           JOIN users u ON b.user_id = u.id
           ORDER BY b.booking_date DESC"""
    )
    
    bookings = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    
    return bookings

@api_router.get("/bookings/pnr/{pnr}")
async def get_booking_by_pnr(pnr: str):
    """Get booking details by PNR"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT b.*, t.train_number, t.train_name, t.source, t.destination, t.fare,
           t.departure_time, t.arrival_time
           FROM bookings b
           JOIN trains t ON b.train_id = t.id
           WHERE b.pnr = ?""",
        (pnr,)
    )
    
    booking = cursor.fetchone()
    conn.close()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    return dict_from_row(booking)

@api_router.delete("/bookings/{pnr}")
async def cancel_booking(pnr: str, current_user: dict = Depends(get_current_user)):
    """Cancel booking and promote from Queue (waiting list)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get booking
    cursor.execute("SELECT * FROM bookings WHERE pnr = ?", (pnr,))
    booking = cursor.fetchone()
    
    if not booking:
        conn.close()
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking = dict_from_row(booking)
    
    # Check if user owns booking or is admin
    if booking['user_id'] != current_user['user_id'] and current_user['role'] != 'admin':
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized to cancel this booking")
    
    if booking['booking_status'] == 'cancelled':
        conn.close()
        raise HTTPException(status_code=400, detail="Booking already cancelled")
    
    # Update booking status
    cursor.execute("UPDATE bookings SET booking_status = 'cancelled' WHERE pnr = ?", (pnr,))
    
    # Remove from passenger cache
    if pnr in passenger_cache:
        del passenger_cache[pnr]
    
    # Check waiting queue (FIFO - First In First Out)
    train_id = booking['train_id']
    if train_id in waiting_queues and not waiting_queues[train_id].is_empty():
        # Dequeue first waiting passenger
        waiting_passenger = waiting_queues[train_id].dequeue()
        
        # Promote waiting passenger
        new_pnr = generate_pnr()
        cursor.execute(
            """INSERT INTO bookings (pnr, user_id, train_id, passenger_name, passenger_age,
               passenger_gender, passenger_phone, seat_number, booking_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_pnr, waiting_passenger['user_id'], train_id, waiting_passenger['passenger_name'],
             waiting_passenger['passenger_age'], waiting_passenger['passenger_gender'], 
             waiting_passenger['passenger_phone'], booking['seat_number'], 'confirmed')
        )
        
        # Cache promoted passenger
        passenger_cache[new_pnr] = {
            'name': waiting_passenger['passenger_name'],
            'age': waiting_passenger['passenger_age'],
            'gender': waiting_passenger['passenger_gender'],
            'phone': waiting_passenger['passenger_phone'],
            'train_id': train_id,
            'seat': booking['seat_number']
        }
        
        # Remove from database waiting list
        cursor.execute(
            "DELETE FROM waiting_list WHERE train_id = ? AND position = 1",
            (train_id,)
        )
        
        # Update positions for remaining passengers
        cursor.execute(
            "UPDATE waiting_list SET position = position - 1 WHERE train_id = ?",
            (train_id,)
        )
        
        message = f"Cancelled. Queue promoted passenger (PNR: {new_pnr})"
    else:
        # No waiting passengers - increase available seats
        cursor.execute(
            "UPDATE trains SET available_seats = available_seats + 1 WHERE id = ?",
            (train_id,)
        )
        
        # Update linked list
        train = trains_linked_list.search(train_id, lambda t, tid: t['id'] == tid)
        if train:
            train['available_seats'] += 1
            trains_linked_list.update(train_id, train, lambda t, tid: t['id'] == tid)
        
        message = "Booking cancelled (LinkedList & Queue updated)"
    
    conn.commit()
    conn.close()
    
    return {"message": message}

# Waiting List Routes
@api_router.get("/waiting-list/{train_id}")
async def get_waiting_list(train_id: int, current_user: dict = Depends(get_current_user)):
    """Get waiting list for a train"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT w.*, u.username FROM waiting_list w
           JOIN users u ON w.user_id = u.id
           WHERE w.train_id = ?
           ORDER BY w.position""",
        (train_id,)
    )
    
    waiting_list = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    
    return waiting_list

# Admin Reports
@api_router.get("/reports/summary")
async def get_summary(current_user: dict = Depends(get_current_user)):
    """Get system summary (Admin only)"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total trains
    cursor.execute("SELECT COUNT(*) as count FROM trains")
    total_trains = cursor.fetchone()[0]
    
    # Total passengers
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'passenger'")
    total_passengers = cursor.fetchone()[0]
    
    # Total bookings
    cursor.execute("SELECT COUNT(*) as count FROM bookings WHERE booking_status = 'confirmed'")
    total_bookings = cursor.fetchone()[0]
    
    # Total seats
    cursor.execute("SELECT SUM(total_seats) as total, SUM(available_seats) as available FROM trains")
    seats_data = cursor.fetchone()
    total_seats = seats_data[0] or 0
    available_seats = seats_data[1] or 0
    booked_seats = total_seats - available_seats
    
    # Waiting list count
    cursor.execute("SELECT COUNT(*) as count FROM waiting_list")
    waiting_count = cursor.fetchone()[0]
    
    # Recent bookings
    cursor.execute(
        """SELECT b.*, t.train_name, u.username FROM bookings b
           JOIN trains t ON b.train_id = t.id
           JOIN users u ON b.user_id = u.id
           ORDER BY b.booking_date DESC LIMIT 10"""
    )
    recent_bookings = [dict_from_row(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_trains": total_trains,
        "total_passengers": total_passengers,
        "total_bookings": total_bookings,
        "total_seats": total_seats,
        "available_seats": available_seats,
        "booked_seats": booked_seats,
        "waiting_count": waiting_count,
        "recent_bookings": recent_bookings
    }

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
