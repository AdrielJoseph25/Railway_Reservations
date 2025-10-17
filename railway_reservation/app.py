from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'railway_reservation_key_2025'  # Secret key for session management

# MySQL configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'cse@123',  # Update with your MySQL password
    'database': 'railway_reservation'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)",
                         (username, password, email))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.Error:
            flash('Username already exists', 'error')
        finally:
            cursor.close()
            conn.close()
    return render_template('register.html')

@app.route('/schedule')
def schedule():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.schedule_id, t.train_name, t.source, t.destination, s.departure_time, s.arrival_time, s.available_seats
        FROM schedules s JOIN trains t ON s.train_id = t.train_id
    """)
    schedules = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('schedule.html', schedules=schedules)

@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'user_id' not in session:
        flash('Please log in to book a ticket', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        schedule_id = request.form['schedule_id']
        num_passengers = int(request.form['num_passengers'])
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT available_seats FROM schedules WHERE schedule_id = %s", (schedule_id,))
            available = cursor.fetchone()
            if available and available[0] >= num_passengers:
                cursor.execute("INSERT INTO bookings (user_id, schedule_id) VALUES (%s, %s)",
                              (session['user_id'], schedule_id))
                booking_id = cursor.lastrowid
                for i in range(num_passengers):
                    first_name = request.form[f'first_name_{i}']
                    last_name = request.form[f'last_name_{i}']
                    if first_name.strip() and last_name.strip():
                        cursor.execute("INSERT INTO passengers (booking_id, first_name, last_name) VALUES (%s, %s, %s)",
                                      (booking_id, first_name, last_name))
                    else:
                        conn.rollback()
                        flash('Passenger names cannot be empty', 'error')
                        return redirect(url_for('book'))
                cursor.execute("UPDATE schedules SET available_seats = available_seats - %s WHERE schedule_id = %s",
                              (num_passengers, schedule_id))
                conn.commit()
                flash('Ticket booked successfully!', 'success')
            else:
                flash(f'Not enough seats available (only {available[0]} left)', 'error')
        except mysql.connector.Error as e:
            conn.rollback()
            flash(f'Error booking ticket: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('user_dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.schedule_id, t.train_name, t.source, t.destination, s.departure_time
        FROM schedules s JOIN trains t ON s.train_id = t.train_id
        WHERE s.available_seats > 0
    """)
    schedules = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('booking.html', schedules=schedules)

@app.route('/cancel_booking/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user_id' not in session:
        flash('Please log in to cancel a booking', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT b.schedule_id, COUNT(p.passenger_id) as passenger_count
            FROM bookings b
            LEFT JOIN passengers p ON b.booking_id = p.booking_id
            WHERE b.booking_id = %s AND b.user_id = %s AND b.status = 'confirmed'
        """, (booking_id, session['user_id']))
        booking = cursor.fetchone()
        if booking:
            cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE booking_id = %s", (booking_id,))
            if booking[1] > 0:
                cursor.execute("UPDATE schedules SET available_seats = available_seats + %s WHERE schedule_id = %s",
                              (booking[1], booking[0]))
            conn.commit()
            flash('Booking cancelled successfully!', 'success')
        else:
            flash('Booking not found or already cancelled', 'error')
    except mysql.connector.Error as e:
        conn.rollback()
        flash(f'Error cancelling booking: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('user_dashboard'))

@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.booking_id, t.train_name, t.source, t.destination, s.departure_time, b.status
        FROM bookings b
        JOIN schedules s ON b.schedule_id = s.schedule_id
        JOIN trains t ON s.train_id = t.train_id
        WHERE b.user_id = %s
    """, (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.execute("SELECT username, email FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()
    cursor.execute("""
        SELECT c.complaint_id, c.complaint_text, c.submitted_at, c.status
        FROM complaints c
        WHERE c.user_id = %s
    """, (session['user_id'],))
    complaints = cursor.fetchall()
    for complaint in complaints:
        cursor.execute("""
            SELECT m.message_id, m.message_text, m.submitted_at, u.username
            FROM complaint_messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.complaint_id = %s
            ORDER BY m.submitted_at
        """, (complaint['complaint_id'],))
        complaint['messages'] = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('user_dashboard.html', bookings=bookings, user=user, complaints=complaints)

@app.route('/view_ticket/<int:booking_id>')
def view_ticket(booking_id):
    if 'user_id' not in session:
        flash('Please log in to view tickets', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.booking_id, t.train_name, t.source, t.destination, s.departure_time, s.arrival_time, b.booking_date, b.status
        FROM bookings b
        JOIN schedules s ON b.schedule_id = s.schedule_id
        JOIN trains t ON s.train_id = t.train_id
        WHERE b.booking_id = %s AND b.user_id = %s
    """, (booking_id, session['user_id']))
    ticket = cursor.fetchone()
    cursor.execute("""
        SELECT first_name, last_name
        FROM passengers
        WHERE booking_id = %s
    """, (booking_id,))
    passengers = cursor.fetchall()
    cursor.close()
    conn.close()
    if not ticket:
        flash('Ticket not found or access denied', 'error')
        return redirect(url_for('user_dashboard'))
    return render_template('view_ticket.html', ticket=ticket, passengers=passengers)

@app.route('/submit_complaint', methods=['POST'])
def submit_complaint():
    if 'user_id' not in session:
        flash('Please log in to submit a complaint', 'error')
        return redirect(url_for('login'))
    complaint_text = request.form['complaint_text']
    if complaint_text.strip():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO complaints (user_id, complaint_text) VALUES (%s, %s)",
                      (session['user_id'], complaint_text))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Complaint submitted successfully!', 'success')
    else:
        flash('Complaint cannot be empty', 'error')
    return redirect(url_for('user_dashboard'))

@app.route('/message_complaint/<int:complaint_id>', methods=['GET', 'POST'])
def message_complaint(complaint_id):
    if 'user_id' not in session:
        flash('Please log in to respond to complaints', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        message_text = request.form['message_text']
        if message_text.strip():
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT user_id FROM complaints WHERE complaint_id = %s", (complaint_id,))
                complaint = cursor.fetchone()
                if complaint and (session['role'] == 'admin' or complaint[0] == session['user_id']):
                    cursor.execute("INSERT INTO complaint_messages (complaint_id, user_id, message_text) VALUES (%s, %s, %s)",
                                  (complaint_id, session['user_id'], message_text))
                    conn.commit()
                    flash('Message sent successfully!', 'success')
                else:
                    flash('Access denied or complaint not found', 'error')
            except mysql.connector.Error as e:
                conn.rollback()
                flash(f'Error sending message: {str(e)}', 'error')
            finally:
                cursor.close()
                conn.close()
        else:
            flash('Message cannot be empty', 'error')
        return redirect(url_for('admin_dashboard' if session['role'] == 'admin' else 'user_dashboard'))
    return render_template('message_complaint.html', complaint_id=complaint_id)

@app.route('/submit_complaint_message/<int:complaint_id>', methods=['POST'])
def submit_complaint_message(complaint_id):
    if 'user_id' not in session:
        flash('Please log in to respond to complaints', 'error')
        return redirect(url_for('login'))
    message_text = request.form['message_text']
    if message_text.strip():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id FROM complaints WHERE complaint_id = %s", (complaint_id,))
            complaint = cursor.fetchone()
            if complaint and (session['role'] == 'admin' or complaint[0] == session['user_id']):
                cursor.execute("INSERT INTO complaint_messages (complaint_id, user_id, message_text) VALUES (%s, %s, %s)",
                              (complaint_id, session['user_id'], message_text))
                conn.commit()
                flash('Message sent successfully!', 'success')
            else:
                flash('Access denied or complaint not found', 'error')
        except mysql.connector.Error as e:
            conn.rollback()
            flash(f'Error sending message: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Message cannot be empty', 'error')
    return redirect(url_for('user_dashboard' if session['role'] == 'user' else 'admin_dashboard'))

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        flash('Please log in to change password', 'error')
        return redirect(url_for('login'))
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT password FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()
    if user and user['password'] == current_password:
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s",
                      (new_password, session['user_id']))
        conn.commit()
        flash('Password changed successfully!', 'success')
    else:
        flash('Current password is incorrect', 'error')
    cursor.close()
    conn.close()
    return redirect(url_for('user_dashboard'))

@app.route('/toggle_complaint_status/<int:complaint_id>')
def toggle_complaint_status(complaint_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM complaints WHERE complaint_id = %s", (complaint_id,))
        current_status = cursor.fetchone()
        if current_status:
            new_status = 'closed' if current_status[0] == 'open' else 'open'
            cursor.execute("UPDATE complaints SET status = %s WHERE complaint_id = %s",
                          (new_status, complaint_id))
            conn.commit()
            flash(f'Complaint status updated to {new_status}', 'success')
        else:
            flash('Complaint not found', 'error')
    except mysql.connector.Error as e:
        flash(f'Error updating complaint status: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_schedule/<int:schedule_id>')
def delete_schedule(schedule_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules WHERE schedule_id = %s", (schedule_id,))
        conn.commit()
        flash('Schedule deleted successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error deleting schedule: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/edit_schedule/<int:schedule_id>', methods=['GET', 'POST'])
def edit_schedule(schedule_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        train_id = request.form['train_id']
        departure_time = request.form['departure_time']
        arrival_time = request.form['arrival_time']
        available_seats = request.form['available_seats']
        try:
            cursor.execute("""
                UPDATE schedules
                SET train_id = %s, departure_time = %s, arrival_time = %s, available_seats = %s
                WHERE schedule_id = %s
            """, (train_id, departure_time, arrival_time, available_seats, schedule_id))
            conn.commit()
            flash('Schedule updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except mysql.connector.Error as e:
            conn.rollback()
            flash(f'Error updating schedule: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    cursor.execute("SELECT * FROM schedules WHERE schedule_id = %s", (schedule_id,))
    schedule = cursor.fetchone()
    cursor.execute("SELECT train_id, train_name FROM trains")
    trains = cursor.fetchall()
    cursor.close()
    conn.close()
    if not schedule:
        flash('Schedule not found', 'error')
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_schedule.html', schedule=schedule, trains=trains)

@app.route('/delete_train/<int:train_id>')
def delete_train(train_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM trains WHERE train_id = %s", (train_id,))
        conn.commit()
        flash('Train deleted successfully!', 'success')
    except mysql.connector.Error as e:
        flash(f'Error deleting train: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/edit_train/<int:train_id>', methods=['GET', 'POST'])
def edit_train(train_id):
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        train_name = request.form['train_name']
        source = request.form['source']
        destination = request.form['destination']
        total_seats = request.form['total_seats']
        try:
            cursor.execute("""
                UPDATE trains
                SET train_name = %s, source = %s, destination = %s, total_seats = %s
                WHERE train_id = %s
            """, (train_name, source, destination, total_seats, train_id))
            conn.commit()
            flash('Train updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except mysql.connector.Error as e:
            conn.rollback()
            flash(f'Error updating train: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    cursor.execute("SELECT * FROM trains WHERE train_id = %s", (train_id,))
    train = cursor.fetchone()
    cursor.close()
    conn.close()
    if not train:
        flash('Train not found', 'error')
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_train.html', train=train)

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        if 'train_name' in request.form:
            train_name = request.form['train_name']
            source = request.form['source']
            destination = request.form['destination']
            total_seats = request.form['total_seats']
            try:
                cursor.execute("INSERT INTO trains (train_name, source, destination, total_seats) VALUES (%s, %s, %s, %s)",
                              (train_name, source, destination, total_seats))
                conn.commit()
                flash('Train added successfully!', 'success')
            except mysql.connector.Error as e:
                conn.rollback()
                flash(f'Error adding train: {str(e)}', 'error')
        elif 'train_id' in request.form:
            train_id = request.form['train_id']
            departure_time = request.form['departure_time']
            arrival_time = request.form['arrival_time']
            available_seats = request.form['available_seats']
            try:
                cursor.execute("INSERT INTO schedules (train_id, departure_time, arrival_time, available_seats) VALUES (%s, %s, %s, %s)",
                              (train_id, departure_time, arrival_time, available_seats))
                conn.commit()
                flash('Schedule added successfully!', 'success')
            except mysql.connector.Error as e:
                conn.rollback()
                flash(f'Error adding schedule: {str(e)}', 'error')
    cursor.execute("SELECT * FROM trains")
    trains = cursor.fetchall()
    cursor.execute("""
        SELECT s.schedule_id, t.train_name, t.source, t.destination, s.departure_time, s.arrival_time, s.available_seats
        FROM schedules s JOIN trains t ON s.train_id = t.train_id
    """)
    schedules = cursor.fetchall()
    cursor.execute("""
        SELECT b.booking_id, u.username, t.train_name, s.departure_time, b.status,
               GROUP_CONCAT(CONCAT(p.first_name, ' ', p.last_name) SEPARATOR ', ') AS passengers
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        JOIN schedules s ON b.schedule_id = s.schedule_id
        JOIN trains t ON s.train_id = t.train_id
        LEFT JOIN passengers p ON b.booking_id = p.booking_id
        GROUP BY b.booking_id
    """)
    bookings = cursor.fetchall()
    cursor.execute("""
        SELECT c.complaint_id, u.username, c.complaint_text, c.submitted_at, c.status
        FROM complaints c
        JOIN users u ON c.user_id = u.user_id
    """)
    complaints = cursor.fetchall()
    for complaint in complaints:
        cursor.execute("""
            SELECT m.message_id, m.message_text, m.submitted_at, u.username
            FROM complaint_messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.complaint_id = %s
            ORDER BY m.submitted_at
        """, (complaint['complaint_id'],))
        complaint['messages'] = cursor.fetchall()
    cursor.execute("SELECT train_id, train_name FROM trains")
    train_options = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_dashboard.html', trains=trains, schedules=schedules, bookings=bookings, complaints=complaints, train_options=train_options)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)