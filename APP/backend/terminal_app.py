#!/usr/bin/env python3
"""Terminal-based Railway Reservation System"""

import sys
import os
from datetime import datetime
from getpass import getpass

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from data_structures import LinkedList, Queue
from database import init_database, get_db_connection, dict_from_row
from auth import hash_password, verify_password
import random
import string

class RailwayTerminal:
    def __init__(self):
        init_database()
        self.current_user = None
        self.trains_list = LinkedList()
        self.waiting_queues = {}  # {train_id: Queue()}
        self.load_data()
    
    def load_data(self):
        """Load trains into linked list"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trains")
        trains = cursor.fetchall()
        
        for train in trains:
            train_dict = dict_from_row(train)
            self.trains_list.insert_at_end(train_dict)
            self.waiting_queues[train_dict['id']] = Queue()
        
        # Load waiting lists
        cursor.execute("SELECT * FROM waiting_list ORDER BY train_id, position")
        waiting = cursor.fetchall()
        for w in waiting:
            w_dict = dict_from_row(w)
            if w_dict['train_id'] in self.waiting_queues:
                self.waiting_queues[w_dict['train_id']].enqueue(w_dict)
        
        conn.close()
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name != 'nt' else 'cls')
    
    def print_header(self, title):
        """Print formatted header"""
        print("\n" + "="*60)
        print(f"  {title}")
        print("="*60)
    
    def generate_pnr(self):
        """Generate unique PNR"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    
    # Authentication
    def login(self):
        """User login"""
        self.print_header("LOGIN")
        username = input("Username: ").strip()
        password = getpass("Password: ")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            user_dict = dict_from_row(user)
            if verify_password(password, user_dict['password']):
                self.current_user = user_dict
                print(f"\n✓ Welcome {user_dict['full_name']}!")
                input("\nPress Enter to continue...")
                return True
        
        print("\n✗ Invalid username or password")
        input("\nPress Enter to continue...")
        return False
    
    def register(self):
        """User registration"""
        self.print_header("REGISTER")
        
        username = input("Username: ").strip()
        password = getpass("Password: ")
        confirm_password = getpass("Confirm Password: ")
        
        if password != confirm_password:
            print("\n✗ Passwords don't match")
            input("\nPress Enter to continue...")
            return False
        
        full_name = input("Full Name: ").strip()
        email = input("Email (optional): ").strip()
        phone = input("Phone (optional): ").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            hashed_pwd = hash_password(password)
            cursor.execute(
                """INSERT INTO users (username, password, role, full_name, email, phone)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, hashed_pwd, 'passenger', full_name, email, phone)
            )
            conn.commit()
            print("\n✓ Registration successful! Please login.")
            input("\nPress Enter to continue...")
            return True
        except:
            print("\n✗ Username already exists")
            input("\nPress Enter to continue...")
            return False
        finally:
            conn.close()
    
    # Train Management (Admin)
    def add_train(self):
        """Add new train"""
        self.print_header("ADD NEW TRAIN")
        
        train_number = input("Train Number: ").strip()
        train_name = input("Train Name: ").strip()
        source = input("Source: ").strip()
        destination = input("Destination: ").strip()
        
        try:
            total_seats = int(input("Total Seats: "))
            fare = float(input("Fare (₹): "))
        except ValueError:
            print("\n✗ Invalid input for seats or fare")
            input("\nPress Enter to continue...")
            return
        
        departure = input("Departure Time (HH:MM, optional): ").strip()
        arrival = input("Arrival Time (HH:MM, optional): ").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO trains (train_number, train_name, source, destination,
                   total_seats, available_seats, fare, departure_time, arrival_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (train_number, train_name, source, destination, total_seats, 
                 total_seats, fare, departure or None, arrival or None)
            )
            conn.commit()
            train_id = cursor.lastrowid
            
            # Add to linked list
            train_data = {
                'id': train_id,
                'train_number': train_number,
                'train_name': train_name,
                'source': source,
                'destination': destination,
                'total_seats': total_seats,
                'available_seats': total_seats,
                'fare': fare,
                'departure_time': departure,
                'arrival_time': arrival
            }
            self.trains_list.insert_at_end(train_data)
            self.waiting_queues[train_id] = Queue()
            
            print(f"\n✓ Train {train_number} added successfully!")
        except:
            print("\n✗ Train number already exists")
        finally:
            conn.close()
            input("\nPress Enter to continue...")
    
    def view_all_trains(self):
        """Display all trains"""
        self.print_header("ALL TRAINS")
        
        trains = self.trains_list.get_all()
        
        if not trains:
            print("\nNo trains available")
        else:
            print(f"\n{'No.':<4} {'Train#':<10} {'Name':<20} {'Route':<30} {'Seats':<10} {'Fare':<10}")
            print("-" * 90)
            
            for idx, train in enumerate(trains, 1):
                route = f"{train['source']} → {train['destination']}"
                seats = f"{train['available_seats']}/{train['total_seats']}"
                print(f"{idx:<4} {train['train_number']:<10} {train['train_name']:<20} {route:<30} {seats:<10} ₹{train['fare']:<10.2f}")
        
        input("\nPress Enter to continue...")
    
    def search_trains(self):
        """Search trains"""
        self.print_header("SEARCH TRAINS")
        
        print("\n1. Search by Train Number")
        print("2. Search by Source")
        print("3. Search by Destination")
        print("4. Search by Route (Source & Destination)")
        
        choice = input("\nEnter choice: ").strip()
        
        trains = self.trains_list.get_all()
        results = []
        
        if choice == '1':
            train_num = input("Enter train number: ").strip().lower()
            results = [t for t in trains if train_num in t['train_number'].lower()]
        elif choice == '2':
            source = input("Enter source: ").strip().lower()
            results = [t for t in trains if source in t['source'].lower()]
        elif choice == '3':
            dest = input("Enter destination: ").strip().lower()
            results = [t for t in trains if dest in t['destination'].lower()]
        elif choice == '4':
            source = input("Enter source: ").strip().lower()
            dest = input("Enter destination: ").strip().lower()
            results = [t for t in trains if source in t['source'].lower() 
                      and dest in t['destination'].lower()]
        else:
            print("\n✗ Invalid choice")
            input("\nPress Enter to continue...")
            return
        
        if not results:
            print("\n✗ No trains found")
        else:
            print(f"\n{'No.':<4} {'Train#':<10} {'Name':<20} {'Route':<30} {'Seats':<10} {'Fare':<10}")
            print("-" * 90)
            
            for idx, train in enumerate(results, 1):
                route = f"{train['source']} → {train['destination']}"
                seats = f"{train['available_seats']}/{train['total_seats']}"
                print(f"{idx:<4} {train['train_number']:<10} {train['train_name']:<20} {route:<30} {seats:<10} ₹{train['fare']:<10.2f}")
        
        input("\nPress Enter to continue...")
    
    def delete_train(self):
        """Delete train"""
        self.print_header("DELETE TRAIN")
        
        train_number = input("Enter train number to delete: ").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM trains WHERE train_number = ?", (train_number,))
        
        if cursor.rowcount > 0:
            conn.commit()
            # Remove from linked list
            self.trains_list.delete_by_value(
                train_number, 
                lambda t, num: t['train_number'] == num
            )
            print(f"\n✓ Train {train_number} deleted successfully")
        else:
            print(f"\n✗ Train {train_number} not found")
        
        conn.close()
        input("\nPress Enter to continue...")
    
    # Booking (Passenger)
    def book_ticket(self):
        """Book a ticket"""
        self.print_header("BOOK TICKET")
        
        # Show available trains
        trains = self.trains_list.get_all()
        if not trains:
            print("\nNo trains available")
            input("\nPress Enter to continue...")
            return
        
        print(f"\n{'No.':<4} {'Train#':<10} {'Name':<20} {'Route':<30} {'Seats':<10} {'Fare':<10}")
        print("-" * 90)
        
        for idx, train in enumerate(trains, 1):
            route = f"{train['source']} → {train['destination']}"
            seats = f"{train['available_seats']}/{train['total_seats']}"
            print(f"{idx:<4} {train['train_number']:<10} {train['train_name']:<20} {route:<30} {seats:<10} ₹{train['fare']:<10.2f}")
        
        try:
            choice = int(input("\nSelect train number (1-{}): ".format(len(trains))))
            if choice < 1 or choice > len(trains):
                raise ValueError
            
            train = trains[choice - 1]
        except:
            print("\n✗ Invalid selection")
            input("\nPress Enter to continue...")
            return
        
        # Get passenger details
        print("\n--- Passenger Details ---")
        name = input("Passenger Name: ").strip()
        
        try:
            age = int(input("Age: "))
        except ValueError:
            print("\n✗ Invalid age")
            input("\nPress Enter to continue...")
            return
        
        gender = input("Gender (M/F/Other): ").strip()
        phone = input("Phone: ").strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check availability
        cursor.execute("SELECT * FROM trains WHERE id = ?", (train['id'],))
        current_train = dict_from_row(cursor.fetchone())
        
        if current_train['available_seats'] > 0:
            # Book ticket
            pnr = self.generate_pnr()
            seat_number = current_train['total_seats'] - current_train['available_seats'] + 1
            
            cursor.execute(
                """INSERT INTO bookings (pnr, user_id, train_id, passenger_name, passenger_age,
                   passenger_gender, passenger_phone, seat_number, booking_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pnr, self.current_user['id'], train['id'], name, age, gender, phone,
                 seat_number, 'confirmed')
            )
            
            cursor.execute(
                "UPDATE trains SET available_seats = available_seats - 1 WHERE id = ?",
                (train['id'],)
            )
            
            # Update linked list
            train['available_seats'] -= 1
            self.trains_list.update(
                train['id'],
                train,
                lambda t, tid: t['id'] == tid
            )
            
            conn.commit()
            
            print("\n" + "*" * 50)
            print("  TICKET CONFIRMED")
            print("*" * 50)
            print(f"  PNR: {pnr}")
            print(f"  Train: {train['train_name']} ({train['train_number']})")
            print(f"  Passenger: {name}, {age} years, {gender}")
            print(f"  Seat: {seat_number}")
            print(f"  Route: {train['source']} → {train['destination']}")
            print(f"  Fare: ₹{train['fare']:.2f}")
            print("*" * 50)
        else:
            # Add to waiting list
            position = self.waiting_queues[train['id']].size() + 1
            
            cursor.execute(
                """INSERT INTO waiting_list (train_id, user_id, passenger_name, passenger_age,
                   passenger_gender, passenger_phone, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (train['id'], self.current_user['id'], name, age, gender, phone, position)
            )
            
            waiting_data = {
                'train_id': train['id'],
                'passenger_name': name,
                'passenger_age': age,
                'passenger_gender': gender,
                'passenger_phone': phone,
                'position': position
            }
            self.waiting_queues[train['id']].enqueue(waiting_data)
            
            conn.commit()
            
            print("\n" + "*" * 50)
            print("  ADDED TO WAITING LIST")
            print("*" * 50)
            print(f"  Train: {train['train_name']} ({train['train_number']})")
            print(f"  Passenger: {name}")
            print(f"  Position: {position}")
            print("*" * 50)
        
        conn.close()
        input("\nPress Enter to continue...")
    
    def view_my_bookings(self):
        """View user's bookings"""
        self.print_header("MY BOOKINGS")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT b.*, t.train_number, t.train_name, t.source, t.destination, t.fare
               FROM bookings b
               JOIN trains t ON b.train_id = t.id
               WHERE b.user_id = ?
               ORDER BY b.booking_date DESC""",
            (self.current_user['id'],)
        )
        
        bookings = [dict_from_row(row) for row in cursor.fetchall()]
        conn.close()
        
        if not bookings:
            print("\nNo bookings found")
        else:
            for booking in bookings:
                status_symbol = "✓" if booking['booking_status'] == 'confirmed' else "✗"
                print("\n" + "-" * 60)
                print(f"  {status_symbol} PNR: {booking['pnr']} [{booking['booking_status'].upper()}]")
                print("-" * 60)
                print(f"  Train: {booking['train_name']} ({booking['train_number']})")
                print(f"  Passenger: {booking['passenger_name']}, {booking['passenger_age']} years")
                print(f"  Seat: {booking['seat_number']}")
                print(f"  Route: {booking['source']} → {booking['destination']}")
                print(f"  Fare: ₹{booking['fare']:.2f}")
                print(f"  Booking Date: {booking['booking_date']}")
        
        input("\nPress Enter to continue...")
    
    def cancel_ticket(self):
        """Cancel a ticket"""
        self.print_header("CANCEL TICKET")
        
        pnr = input("Enter PNR to cancel: ").strip().upper()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM bookings WHERE pnr = ? AND user_id = ?", 
                      (pnr, self.current_user['id']))
        booking = cursor.fetchone()
        
        if not booking:
            print("\n✗ Booking not found or not authorized")
            conn.close()
            input("\nPress Enter to continue...")
            return
        
        booking = dict_from_row(booking)
        
        if booking['booking_status'] == 'cancelled':
            print("\n✗ Booking already cancelled")
            conn.close()
            input("\nPress Enter to continue...")
            return
        
        # Cancel booking
        cursor.execute("UPDATE bookings SET booking_status = 'cancelled' WHERE pnr = ?", (pnr,))
        
        # Check waiting list (Queue)
        if booking['train_id'] in self.waiting_queues:
            waiting_passenger = self.waiting_queues[booking['train_id']].dequeue()
            
            if waiting_passenger:
                # Promote waiting passenger
                new_pnr = self.generate_pnr()
                cursor.execute(
                    """INSERT INTO bookings (pnr, user_id, train_id, passenger_name, passenger_age,
                       passenger_gender, passenger_phone, seat_number, booking_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_pnr, self.current_user['id'], booking['train_id'], 
                     waiting_passenger['passenger_name'], waiting_passenger['passenger_age'],
                     waiting_passenger['passenger_gender'], waiting_passenger['passenger_phone'],
                     booking['seat_number'], 'confirmed')
                )
                
                cursor.execute("DELETE FROM waiting_list WHERE train_id = ? AND position = 1",
                             (booking['train_id'],))
                cursor.execute("UPDATE waiting_list SET position = position - 1 WHERE train_id = ?",
                             (booking['train_id'],))
                
                print(f"\n✓ Ticket cancelled. Waiting passenger promoted (PNR: {new_pnr})")
            else:
                cursor.execute(
                    "UPDATE trains SET available_seats = available_seats + 1 WHERE id = ?",
                    (booking['train_id'],)
                )
                print("\n✓ Ticket cancelled successfully")
        
        conn.commit()
        conn.close()
        input("\nPress Enter to continue...")
    
    # Admin Reports
    def view_all_bookings(self):
        """View all bookings (Admin)"""
        self.print_header("ALL BOOKINGS")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT b.*, t.train_number, t.train_name, u.username
               FROM bookings b
               JOIN trains t ON b.train_id = t.id
               JOIN users u ON b.user_id = u.id
               ORDER BY b.booking_date DESC"""
        )
        
        bookings = [dict_from_row(row) for row in cursor.fetchall()]
        conn.close()
        
        if not bookings:
            print("\nNo bookings found")
        else:
            print(f"\nTotal Bookings: {len(bookings)}\n")
            print(f"{'PNR':<12} {'User':<15} {'Train':<12} {'Passenger':<20} {'Status':<12}")
            print("-" * 80)
            
            for booking in bookings:
                print(f"{booking['pnr']:<12} {booking['username']:<15} {booking['train_number']:<12} {booking['passenger_name']:<20} {booking['booking_status']:<12}")
        
        input("\nPress Enter to continue...")
    
    def view_waiting_list(self):
        """View waiting lists (Admin)"""
        self.print_header("WAITING LISTS")
        
        trains = self.trains_list.get_all()
        
        has_waiting = False
        for train in trains:
            if train['id'] in self.waiting_queues:
                waiting = self.waiting_queues[train['id']].get_all()
                if waiting:
                    has_waiting = True
                    print(f"\nTrain: {train['train_name']} ({train['train_number']})")
                    print("-" * 60)
                    print(f"{'Pos':<5} {'Passenger':<20} {'Age':<5} {'Phone':<15}")
                    print("-" * 60)
                    
                    for w in waiting:
                        print(f"{w['position']:<5} {w['passenger_name']:<20} {w['passenger_age']:<5} {w['passenger_phone']:<15}")
        
        if not has_waiting:
            print("\nNo passengers in waiting list")
        
        input("\nPress Enter to continue...")
    
    def system_summary(self):
        """Display system summary (Admin)"""
        self.print_header("SYSTEM SUMMARY")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM trains")
        total_trains = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'passenger'")
        total_passengers = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM bookings WHERE booking_status = 'confirmed'")
        total_bookings = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(total_seats), SUM(available_seats) FROM trains")
        seats_data = cursor.fetchone()
        total_seats = seats_data[0] or 0
        available_seats = seats_data[1] or 0
        
        cursor.execute("SELECT COUNT(*) FROM waiting_list")
        waiting_count = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"\n  Total Trains: {total_trains}")
        print(f"  Total Passengers (Users): {total_passengers}")
        print(f"  Total Confirmed Bookings: {total_bookings}")
        print(f"  Total Seats: {total_seats}")
        print(f"  Available Seats: {available_seats}")
        print(f"  Booked Seats: {total_seats - available_seats}")
        print(f"  Waiting List Count: {waiting_count}")
        
        input("\nPress Enter to continue...")
    
    # Menus
    def admin_menu(self):
        """Admin dashboard menu"""
        while True:
            self.clear_screen()
            self.print_header(f"ADMIN DASHBOARD - {self.current_user['username']}")
            
            print("\n--- Train Management ---")
            print("1. Add New Train")
            print("2. View All Trains")
            print("3. Search Trains")
            print("4. Delete Train")
            print("\n--- Booking Management ---")
            print("5. View All Bookings")
            print("6. View Waiting Lists")
            print("\n--- Reports ---")
            print("7. System Summary")
            print("\n8. Logout")
            
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                self.add_train()
            elif choice == '2':
                self.view_all_trains()
            elif choice == '3':
                self.search_trains()
            elif choice == '4':
                self.delete_train()
            elif choice == '5':
                self.view_all_bookings()
            elif choice == '6':
                self.view_waiting_list()
            elif choice == '7':
                self.system_summary()
            elif choice == '8':
                self.current_user = None
                break
            else:
                print("\n✗ Invalid choice")
                input("\nPress Enter to continue...")
    
    def passenger_menu(self):
        """Passenger dashboard menu"""
        while True:
            self.clear_screen()
            self.print_header(f"PASSENGER DASHBOARD - {self.current_user['full_name']}")
            
            print("\n1. Search Trains")
            print("2. View All Trains")
            print("3. Book Ticket")
            print("4. View My Bookings")
            print("5. Cancel Ticket")
            print("6. Logout")
            
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                self.search_trains()
            elif choice == '2':
                self.view_all_trains()
            elif choice == '3':
                self.book_ticket()
            elif choice == '4':
                self.view_my_bookings()
            elif choice == '5':
                self.cancel_ticket()
            elif choice == '6':
                self.current_user = None
                break
            else:
                print("\n✗ Invalid choice")
                input("\nPress Enter to continue...")
    
    def main_menu(self):
        """Main entry menu"""
        while True:
            self.clear_screen()
            self.print_header("RAILWAY RESERVATION SYSTEM")
            
            print("\n1. Login")
            print("2. Register")
            print("3. Exit")
            
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                if self.login():
                    if self.current_user['role'] == 'admin':
                        self.admin_menu()
                    else:
                        self.passenger_menu()
            elif choice == '2':
                self.register()
            elif choice == '3':
                print("\nThank you for using Railway Reservation System!")
                break
            else:
                print("\n✗ Invalid choice")
                input("\nPress Enter to continue...")

if __name__ == "__main__":
    app = RailwayTerminal()
    app.main_menu()
