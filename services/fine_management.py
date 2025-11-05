# services/fine_management.py
from models.database_model import DatabaseModel
from datetime import datetime, timedelta

class FineManagementService:
    def __init__(self):
        self.db_model = DatabaseModel()
    
    def authenticate_user(self, badge_number, password):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, badge_number, full_name, email, role, department, password_hash
            FROM users WHERE badge_number = ? AND is_active = 1
        ''', (badge_number,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user and self.db_model.verify_password(password, user[6]):
            return {
                'id': user[0],
                'badge_number': user[1],
                'full_name': user[2],
                'email': user[3],
                'role': user[4],
                'department': user[5]
            }
        return None
    
    def record_traffic_offence(self, offence_data):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        fine_number = self.db_model.generate_fine_number()
        offence_date = datetime.strptime(offence_data['offence_date'], '%Y-%m-%d %H:%M:%S')
        due_date = offence_date + timedelta(days=30)
        
        cursor.execute('''
            INSERT INTO traffic_fines 
            (fine_number, offence_date, offence_location, officer_id, offender_id, 
             vehicle_id, offence_type_id, fine_amount, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            fine_number,
            offence_data['offence_date'],
            offence_data['offence_location'],
            offence_data['officer_id'],
            offence_data['offender_id'],
            offence_data['vehicle_id'],
            offence_data['offence_type_id'],
            offence_data['fine_amount'],
            due_date.strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        fine_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.send_offence_notification(fine_id)
        return fine_number
    
    def send_offence_notification(self, fine_id):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT tf.fine_number, tf.offence_date, tf.offence_location, 
                   tf.fine_amount, tf.due_date,
                   ot.offence_description,
                   o.full_name, o.email, o.phone_number,
                   v.registration_number
            FROM traffic_fines tf
            JOIN offence_types ot ON tf.offence_type_id = ot.id
            JOIN offenders o ON tf.offender_id = o.id
            JOIN vehicles v ON tf.vehicle_id = v.id
            WHERE tf.id = ?
        ''', (fine_id,))
        
        fine_details = cursor.fetchone()
        conn.close()
        
        if not fine_details:
            return False
        
        message = f"""
        ZIMBABWE REPUBLIC POLICE - TRAFFIC FINE NOTIFICATION
        
        Fine Number: {fine_details[0]}
        Date: {fine_details[1]}
        Location: {fine_details[2]}
        Vehicle: {fine_details[9]}
        Offence: {fine_details[5]}
        Amount Due: USD {fine_details[3]:.2f}
        Due Date: {fine_details[4]}
        
        Please pay your fine at any ZRP station.
        """
        
        if fine_details[7]:
            self.send_email_notification(fine_details[7], "Traffic Fine Notification", message, fine_id)
        
        if fine_details[8]:
            self.send_sms_notification(fine_details[8], message, fine_id)
        
        return True
    
    def send_email_notification(self, recipient, subject, message, fine_id):
        try:
            print(f"EMAIL SENT TO: {recipient}")
            print(f"SUBJECT: {subject}")
            print(f"CONTENT: {message}")
            self.log_notification(fine_id, 'email', recipient, message, 'sent')
            return True
        except Exception as e:
            print(f"Email sending failed: {e}")
            self.log_notification(fine_id, 'email', recipient, message, 'failed')
            return False
    
    def send_sms_notification(self, phone_number, message, fine_id):
        try:
            print(f"SMS SENT TO: {phone_number}")
            print(f"CONTENT: {message}")
            self.log_notification(fine_id, 'sms', phone_number, message, 'sent')
            return True
        except Exception as e:
            print(f"SMS sending failed: {e}")
            self.log_notification(fine_id, 'sms', phone_number, message, 'failed')
            return False
    
    def log_notification(self, fine_id, notification_type, recipient, message, status):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO notifications 
            (fine_id, notification_type, recipient, message_content, sent_status)
            VALUES (?, ?, ?, ?, ?)
        ''', (fine_id, notification_type, recipient, message, status))
        
        conn.commit()
        conn.close()
    
    def generate_reports(self, report_type, start_date=None, end_date=None, officer_id=None):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        base_query = '''
            SELECT tf.fine_number, tf.offence_date, tf.offence_location, 
                   tf.fine_amount, tf.status, tf.due_date,
                   o.full_name as offender_name, o.national_id,
                   v.registration_number,
                   u.full_name as officer_name,
                   ot.offence_description
            FROM traffic_fines tf
            JOIN offenders o ON tf.offender_id = o.id
            JOIN vehicles v ON tf.vehicle_id = v.id
            JOIN users u ON tf.officer_id = u.id
            JOIN offence_types ot ON tf.offence_type_id = ot.id
        '''
        
        conditions = []
        params = []
        
        if start_date and end_date:
            conditions.append("tf.offence_date BETWEEN ? AND ?")
            params.extend([start_date, end_date])
        
        if officer_id:
            conditions.append("tf.officer_id = ?")
            params.append(officer_id)
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        if report_type == "statistics":
            cursor.execute(f'''
                SELECT 
                    COUNT(*) as total_fines,
                    SUM(tf.fine_amount) as total_amount,
                    AVG(tf.fine_amount) as average_fine,
                    COUNT(CASE WHEN tf.status = 'paid' THEN 1 END) as paid_fines,
                    COUNT(CASE WHEN tf.status = 'issued' THEN 1 END) as pending_fines,
                    COUNT(CASE WHEN tf.status = 'overdue' THEN 1 END) as overdue_fines,
                    ot.offence_description,
                    COUNT(*) as offence_count
                FROM traffic_fines tf
                JOIN offence_types ot ON tf.offence_type_id = ot.id
                { "WHERE " + " AND ".join(conditions) if conditions else "" }
                GROUP BY ot.offence_description
                ORDER BY offence_count DESC
            ''', params)
            
            results = cursor.fetchall()
            conn.close()
            return self.format_statistics_report(results)
        
        else:
            cursor.execute(base_query + " ORDER BY tf.offence_date DESC", params)
            results = cursor.fetchall()
            conn.close()
            return self.format_detailed_report(results)
    
    def format_statistics_report(self, data):
        if not data:
            return "No data available for the selected period."
        
        report = "ZRP TRAFFIC FINE STATISTICS REPORT\n"
        report += "=" * 50 + "\n\n"
        
        total_fines = sum(row[0] for row in data)
        total_amount = sum(row[1] for row in data)
        
        report += f"Total Fines Issued: {total_fines}\n"
        report += f"Total Amount: USD {total_amount:.2f}\n"
        report += f"Average Fine: USD {data[0][2] if data[0][2] else 0:.2f}\n"
        report += f"Paid Fines: {data[0][3]}\n"
        report += f"Pending Fines: {data[0][4]}\n"
        report += f"Overdue Fines: {data[0][5]}\n\n"
        
        report += "Offence Breakdown:\n"
        report += "-" * 30 + "\n"
        
        for row in data:
            report += f"{row[6]}: {row[7]} offences\n"
        
        return report
    
    def format_detailed_report(self, data):
        if not data:
            return "No fines found for the selected criteria."
        
        report = "ZRP TRAFFIC FINES DETAILED REPORT\n"
        report += "=" * 60 + "\n\n"
        
        for row in data:
            report += f"Fine No: {row[0]}\n"
            report += f"Date: {row[1]}\n"
            report += f"Location: {row[2]}\n"
            report += f"Amount: USD {row[3]:.2f}\n"
            report += f"Status: {row[4]}\n"
            report += f"Due Date: {row[5]}\n"
            report += f"Offender: {row[6]} (ID: {row[7]})\n"
            report += f"Vehicle: {row[8]}\n"
            report += f"Officer: {row[9]}\n"
            report += f"Offence: {row[10]}\n"
            report += "-" * 40 + "\n\n"
        
        return report
    
    def get_offence_types(self):
        conn = self.db_model.get_connection()
        offence_types = conn.execute(
            'SELECT id, offence_code, offence_description, fine_amount FROM offence_types WHERE is_active = 1'
        ).fetchall()
        conn.close()
        return offence_types
    
    def save_offender(self, national_id, full_name, email, phone_number):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO offenders (national_id, full_name, email, phone_number)
            VALUES (?, ?, ?, ?)
        ''', (national_id, full_name, email, phone_number))
        
        offender_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return offender_id
    
    def save_vehicle(self, registration_number, make, model, color, owner_id):
        conn = self.db_model.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO vehicles (registration_number, make, model, color, owner_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (registration_number, make, model, color, owner_id))
        
        vehicle_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return vehicle_id
    
    def get_all_officers(self):
        conn = self.db_model.get_connection()
        officers = conn.execute(
            'SELECT id, badge_number, full_name FROM users WHERE role = "officer"'
        ).fetchall()
        conn.close()
        return officers