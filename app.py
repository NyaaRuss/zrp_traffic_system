# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from services.fine_management import FineManagementService
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'zrp_traffic_system_secret_key_2024'

fine_service = FineManagementService()

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        badge_number = request.form.get('badge_number')
        password = request.form.get('password')
        
        user = fine_service.authenticate_user(badge_number, password)
        if user:
            session['user'] = user
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid badge number or password', 'error')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = fine_service.db_model.get_connection()
    
    total_fines = conn.execute('SELECT COUNT(*) FROM traffic_fines').fetchone()[0]
    total_paid = conn.execute('SELECT COUNT(*) FROM traffic_fines WHERE status = "paid"').fetchone()[0]
    revenue = conn.execute('SELECT SUM(fine_amount) FROM traffic_fines WHERE status = "paid"').fetchone()[0] or 0
    today_fines = conn.execute(
        'SELECT COUNT(*) FROM traffic_fines WHERE DATE(offence_date) = DATE("now")'
    ).fetchone()[0]
    
    recent_fines = conn.execute('''
        SELECT tf.fine_number, tf.offence_date, tf.offence_location, 
               tf.fine_amount, tf.status, tf.due_date,
               o.full_name, o.national_id,
               v.registration_number,
               ot.offence_description
        FROM traffic_fines tf
        JOIN offenders o ON tf.offender_id = o.id
        JOIN vehicles v ON tf.vehicle_id = v.id
        JOIN offence_types ot ON tf.offence_type_id = ot.id
        ORDER BY tf.offence_date DESC LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         current_user=session['user'],
                         total_fines=total_fines,
                         total_paid=total_paid,
                         revenue=revenue,
                         today_fines=today_fines,
                         recent_fines=recent_fines)

@app.route('/record_offence', methods=['GET', 'POST'])
def record_offence():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            national_id = request.form.get('national_id')
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone_number = request.form.get('phone_number')
            
            registration_number = request.form.get('registration_number')
            vehicle_make = request.form.get('vehicle_make')
            vehicle_model = request.form.get('vehicle_model')
            vehicle_color = request.form.get('vehicle_color')
            
            offence_location = request.form.get('offence_location')
            offence_date = request.form.get('offence_date')
            offence_type_id = request.form.get('offence_type_id')
            
            offence_datetime = datetime.strptime(offence_date, '%Y-%m-%dT%H:%M')
            offence_date_str = offence_datetime.strftime('%Y-%m-%d %H:%M:%S')
            
            offender_id = fine_service.save_offender(national_id, full_name, email, phone_number)
            vehicle_id = fine_service.save_vehicle(registration_number, vehicle_make, vehicle_model, vehicle_color, offender_id)
            
            conn = fine_service.db_model.get_connection()
            fine_amount = conn.execute(
                'SELECT fine_amount FROM offence_types WHERE id = ?', 
                (offence_type_id,)
            ).fetchone()[0]
            conn.close()
            
            offence_data = {
                'offence_date': offence_date_str,
                'offence_location': offence_location,
                'officer_id': session['user']['id'],
                'offender_id': offender_id,
                'vehicle_id': vehicle_id,
                'offence_type_id': offence_type_id,
                'fine_amount': fine_amount
            }
            
            fine_number = fine_service.record_traffic_offence(offence_data)
            
            flash(f'Fine issued successfully! Fine Number: {fine_number}', 'success')
            return redirect(url_for('record_offence'))
            
        except Exception as e:
            flash(f'Error issuing fine: {str(e)}', 'error')
    
    offence_types = fine_service.get_offence_types()
    return render_template('record_offence.html', 
                         current_user=session['user'],
                         offence_types=offence_types)

@app.route('/view_fines')
def view_fines():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    search_type = request.args.get('search_type', 'fine_number')
    search_value = request.args.get('search_value', '')
    status_filter = request.args.get('status_filter', 'all')
    
    conn = fine_service.db_model.get_connection()
    
    query = '''
        SELECT tf.fine_number, tf.offence_date, tf.offence_location, 
               tf.fine_amount, tf.status, tf.due_date,
               o.full_name, o.national_id,
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
    
    if search_value:
        if search_type == 'fine_number':
            conditions.append("tf.fine_number LIKE ?")
            params.append(f"%{search_value}%")
        elif search_type == 'national_id':
            conditions.append("o.national_id LIKE ?")
            params.append(f"%{search_value}%")
        elif search_type == 'vehicle_reg':
            conditions.append("v.registration_number LIKE ?")
            params.append(f"%{search_value}%")
    
    if status_filter != 'all':
        conditions.append("tf.status = ?")
        params.append(status_filter)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY tf.offence_date DESC"
    
    fines = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('view_fines.html', 
                         current_user=session['user'],
                         fines=fines,
                         search_type=search_type,
                         search_value=search_value,
                         status_filter=status_filter)

@app.route('/reports')
def reports():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    report_type = request.args.get('report_type', 'detailed')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    officer_id = None
    if session['user']['role'] in ['admin', 'super_admin']:
        officer_id = request.args.get('officer_id', '')
        if officer_id == 'all' or not officer_id:
            officer_id = None
    
    report_content = ""
    if start_date and end_date:
        report_content = fine_service.generate_reports(
            report_type="statistics" if report_type == "statistics" else "detailed",
            start_date=start_date + " 00:00:00",
            end_date=end_date + " 23:59:59",
            officer_id=officer_id
        )
    
    officers = fine_service.get_all_officers()
    
    return render_template('reports.html',
                         current_user=session['user'],
                         report_content=report_content,
                         officers=officers,
                         report_type=report_type,
                         start_date=start_date,
                         end_date=end_date)

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)