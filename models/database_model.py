# models/database_model.py
import sqlite3
from datetime import datetime, timedelta
import hashlib
import secrets
import os

class DatabaseModel:
    def __init__(self, db_path=None):
        if db_path is None:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(current_dir, 'database', 'traffic_fine_system.db')
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        else:
            self.db_path = db_path
        
        self.init_database()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                badge_number TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('officer', 'admin', 'super_admin')),
                department TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Offenders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offenders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                national_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                phone_number TEXT,
                address TEXT,
                date_of_birth DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Vehicles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_number TEXT UNIQUE NOT NULL,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                color TEXT,
                year INTEGER,
                owner_id INTEGER,
                FOREIGN KEY (owner_id) REFERENCES offenders (id)
            )
        ''')
        
        # Offence types table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offence_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offence_code TEXT UNIQUE NOT NULL,
                offence_description TEXT NOT NULL,
                fine_amount REAL NOT NULL,
                demerit_points INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Traffic fines table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traffic_fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fine_number TEXT UNIQUE NOT NULL,
                offence_date TIMESTAMP NOT NULL,
                offence_location TEXT NOT NULL,
                officer_id INTEGER NOT NULL,
                offender_id INTEGER NOT NULL,
                vehicle_id INTEGER NOT NULL,
                offence_type_id INTEGER NOT NULL,
                fine_amount REAL NOT NULL,
                status TEXT DEFAULT 'issued' CHECK(status IN ('issued', 'paid', 'cancelled', 'overdue')),
                due_date TIMESTAMP NOT NULL,
                paid_date TIMESTAMP,
                payment_reference TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (officer_id) REFERENCES users (id),
                FOREIGN KEY (offender_id) REFERENCES offenders (id),
                FOREIGN KEY (vehicle_id) REFERENCES vehicles (id),
                FOREIGN KEY (offence_type_id) REFERENCES offence_types (id)
            )
        ''')
        
        # Notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fine_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL CHECK(notification_type IN ('sms', 'email')),
                recipient TEXT NOT NULL,
                message_content TEXT NOT NULL,
                sent_status TEXT DEFAULT 'sent' CHECK(sent_status IN ('sent', 'failed', 'pending')),
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fine_id) REFERENCES traffic_fines (id)
            )
        ''')
        
        # Default admin user
        default_password = self.hash_password("admin123")
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (badge_number, full_name, email, password_hash, role, department)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('ZRP001', 'System Administrator', 'admin@zrp.gov.zw', default_password, 'super_admin', 'Headquarters'))
        
        # Sample officer
        officer_password = self.hash_password("officer123")
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (badge_number, full_name, email, password_hash, role, department)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('ZRP002', 'John Moyo', 'john.moyo@zrp.gov.zw', officer_password, 'officer', 'Traffic Section'))
        
        # Sample offence types
        sample_offences = [
            ('SPD001', 'Speeding - Exceeding limit by 1-15 km/h', 50.00, 2),
            ('SPD002', 'Speeding - Exceeding limit by 16-30 km/h', 100.00, 4),
            ('RLC001', 'Running red light', 150.00, 6),
            ('DUI001', 'Driving under influence', 500.00, 10),
            ('NLI001', 'Driving without valid license', 100.00, 4),
            ('NIN001', 'No insurance', 200.00, 6),
            ('SBT001', 'Seatbelt violation', 30.00, 2),
            ('PKE001', 'Illegal parking', 25.00, 1),
            ('VTL001', 'Vehicle without valid license disc', 75.00, 3),
            ('DWN001', 'Driving without number plates', 150.00, 5)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO offence_types 
            (offence_code, offence_description, fine_amount, demerit_points)
            VALUES (?, ?, ?, ?)
        ''', sample_offences)
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password, password_hash):
        return self.hash_password(password) == password_hash
    
    def generate_fine_number(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = secrets.token_hex(3).upper()
        return f"ZRPF{timestamp}{random_part}"