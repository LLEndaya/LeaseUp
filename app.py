from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

db = SQLAlchemy()

def create_app(test_config=None):
    """Initialize and configure the Flask application with database and authentication."""
    app = Flask(__name__, instance_relative_config=True)
    # Determine database path: prefer existing database/leaseup.db, otherwise use instance/leaseup.db
    instance_db = os.path.join(app.instance_path, 'leaseup.db')
    alt_db = os.path.join(BASE_DIR, 'database', 'leaseup.db')
    if os.path.exists(alt_db):
        db_file = alt_db
    else:
        db_file = instance_db

    app.config.from_mapping(
        SECRET_KEY='dev',
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_file}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    def is_admin_user(user=None):
        from flask_login import current_user as _current
        u = user or _current
        try:
            gid = u.get_id()
            return isinstance(gid, str) and gid.startswith('user_')
        except Exception:
            return False

    def is_tenant_user(user=None):
        from flask_login import current_user as _current
        u = user or _current
        try:
            gid = u.get_id()
            return isinstance(gid, str) and gid.startswith('tenant_')
        except Exception:
            return False

    @app.context_processor
    def inject_user_flags():
        return dict(is_admin=is_admin_user(), is_tenant=is_tenant_user())

    @login_manager.user_loader
    def load_user(user_id):
        """Load user from session. Handles both admin (User) and tenant (TenantUser) accounts.
        Uses prefixed IDs (user_<id>, tenant_<id>) to avoid collisions between tables."""
        try:
            if isinstance(user_id, str) and '_' in user_id:
                prefix, uid = user_id.split('_', 1)
                uid = int(uid)
                if prefix == 'user':
                    return User.query.get(uid)
                if prefix == 'tenant':
                    return TenantUser.query.get(uid)
        except Exception:
            pass
        try:
            uid = int(user_id)
        except Exception:
            return None
        user = User.query.get(uid)
        if user:
            return user
        return TenantUser.query.get(uid)

    class User(db.Model, UserMixin):
        """Admin user account for property management."""
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        password_hash = db.Column(db.String(200), nullable=False)

        def get_id(self):
            """Return prefixed user ID for session storage."""
            return f'user_{self.id}'

        def set_password(self, password):
            self.password_hash = generate_password_hash(password)

        def check_password(self, password):
            return check_password_hash(self.password_hash, password)

    class TenantUser(db.Model, UserMixin):
        """Tenant account for apartment booking and lease management."""
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        email = db.Column(db.String(120), unique=True, nullable=False)
        password_hash = db.Column(db.String(200), nullable=False)
        phone = db.Column(db.String(50))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def get_id(self):
            """Return prefixed tenant ID for session storage."""
            return f'tenant_{self.id}'

        def set_password(self, password):
            self.password_hash = generate_password_hash(password)

        def check_password(self, password):
            return check_password_hash(self.password_hash, password)

    class Property(db.Model):
        """Rental property (complex/building)."""
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), nullable=False)
        address = db.Column(db.String(255))
        units = db.relationship('Unit', backref='property', lazy=True)

    class Unit(db.Model):
        """Individual apartment/room within a property. Status: 'vacant' or 'occupied'."""
        id = db.Column(db.Integer, primary_key=True)
        number = db.Column(db.String(50), nullable=False)
        status = db.Column(db.String(30), default='vacant')
        property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
        leases = db.relationship('Lease', backref='unit', lazy=True)

    class Tenant(db.Model):
        """Tenant record linked to active leases (created from booking approvals)."""
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), nullable=False)
        phone = db.Column(db.String(50))
        email = db.Column(db.String(120))
        leases = db.relationship('Lease', backref='tenant', lazy=True)

    class Lease(db.Model):
        """Active or completed lease agreement between a tenant and unit."""
        id = db.Column(db.Integer, primary_key=True)
        unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
        tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
        start_date = db.Column(db.Date)
        end_date = db.Column(db.Date)
        monthly_rent = db.Column(db.Float)
        payments = db.relationship('Payment', backref='lease', lazy=True)

    class Payment(db.Model):
        """Payment record for a lease (rent payment tracking)."""
        id = db.Column(db.Integer, primary_key=True)
        lease_id = db.Column(db.Integer, db.ForeignKey('lease.id'))
        amount = db.Column(db.Float, nullable=False)
        date = db.Column(db.DateTime, default=datetime.utcnow)

    class MaintenanceRequest(db.Model):
        """Maintenance issue report for a unit. Status: 'open', 'in_progress', 'completed'."""
        id = db.Column(db.Integer, primary_key=True)
        unit_id = db.Column(db.Integer)
        description = db.Column(db.Text)
        status = db.Column(db.String(50), default='open')
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class LeaseRequest(db.Model):
        """Booking request from a tenant. Status: 'pending', 'approved', 'rejected'."""
        id = db.Column(db.Integer, primary_key=True)
        unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
        tenant_user_id = db.Column(db.Integer, db.ForeignKey('tenant_user.id'))
        start_date = db.Column(db.Date)
        end_date = db.Column(db.Date)
        notes = db.Column(db.Text)
        status = db.Column(db.String(50), default='pending')
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        unit = db.relationship('Unit', backref='lease_requests')
        tenant_user = db.relationship('TenantUser', backref='lease_requests')

    class EmergencyContact(db.Model):
        """Emergency contact information per unit for public lookup."""
        id = db.Column(db.Integer, primary_key=True)
        unit_identifier = db.Column(db.String(100))
        name = db.Column(db.String(120))
        phone = db.Column(db.String(50))
    

    @app.cli.command('init-db')
    def init_db():
        """Initialize database schema and seed default data (properties, units, users)."""
        print(f"Using database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
        db.create_all()
        if not Property.query.first():
            props = [
                Property(name='Greenfield Heights', address='123 Main St'),
                Property(name='Sunrise Residences', address='456 Oak Ave'),
                Property(name='Urban Plaza Apts', address='789 Pine Blvd'),
                Property(name='Riverside Towers', address='321 Elm Way')
            ]
            for p in props:
                db.session.add(p)
            db.session.commit()
            
            units = []
            for i, p in enumerate(props, 1):
                u = Unit(number=f'Room {i}', status='vacant', property_id=p.id)
                db.session.add(u)
                units.append(u)
            db.session.commit()
            
            tenants = [
                Tenant(name='Juan Dela Cruz', phone='09171234567', email='juan@example.com'),
                Tenant(name='Maria Santos', phone='09187654321', email='maria@example.com')
            ]
            for t in tenants:
                db.session.add(t)
            db.session.commit()
            
            units[0].status = 'occupied'
            lease1 = Lease(
                unit_id=units[0].id,
                tenant_id=tenants[0].id,
                start_date=datetime.utcnow().date(),
                end_date=(datetime.utcnow() + timedelta(days=365)).date(),
                monthly_rent=5000
            )
            db.session.add(lease1)
            
            units[3].status = 'occupied'
            lease2 = Lease(
                unit_id=units[3].id,
                tenant_id=tenants[1].id,
                start_date=datetime.utcnow().date(),
                end_date=(datetime.utcnow() + timedelta(days=365)).date(),
                monthly_rent=6500
            )
            db.session.add(lease2)
            db.session.commit()
            
            for i, u in enumerate(units, 1):
                if i == 1 and tenants:
                    ec = EmergencyContact(
                        unit_identifier=f'Room {i}',
                        name=tenants[0].name,
                        phone=tenants[0].phone
                    )
                else:
                    ec = EmergencyContact(
                        unit_identifier=f'Room {i}',
                        name=f'Property Manager {i}',
                        phone=f'0917123456{i}'
                    )
                db.session.add(ec)
            db.session.commit()

            try:
                if len(units) >= 4:
                    mr = MaintenanceRequest(
                        unit_id=units[3].id,
                        description='Leaky faucet reported in Room 4. Needs plumbing attention.',
                        status='open'
                    )
                    db.session.add(mr)
                    db.session.commit()
            except Exception:
                db.session.rollback()
        
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('admin1234')
            db.session.add(admin)
            db.session.commit()
        
        if not TenantUser.query.filter_by(username='tenant').first():
            tenant_user = TenantUser(username='tenant', email='tenant@example.com')
            tenant_user.set_password('tenant123')
            db.session.add(tenant_user)
            db.session.commit()
        
        print('Initialized the database.')

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/manage')
    @login_required
    def manage():
        if not is_admin_user():
            flash('Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        return render_template('manage.html')

    @app.route('/booking-requests')
    @login_required
    def booking_requests():
        if not is_admin_user():
            flash('Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        requests_data = LeaseRequest.query.filter(LeaseRequest.status != 'rejected').order_by(LeaseRequest.created_at.desc()).all()
        return render_template('booking_requests.html', requests_data=requests_data)

    @app.route('/booking-request/<int:request_id>/approve', methods=['POST'])
    @login_required
    def approve_booking_request(request_id):
        if not is_admin_user():
            return jsonify({'ok': False, 'message': 'Admin access only'}), 403
        
        lease_req = LeaseRequest.query.get(request_id)
        if not lease_req:
            flash('Booking request not found.')
            return redirect(url_for('booking_requests'))
        

        lease_req.status = 'approved'
        
        # Get or create tenant record for this booking
        tenant_user = lease_req.tenant_user
        tenant = Tenant.query.filter_by(email=tenant_user.email).first()
        if not tenant:
            tenant = Tenant(name=tenant_user.username, email=tenant_user.email, phone=tenant_user.phone)
            db.session.add(tenant)
            db.session.flush()
        
        # Update unit status
        unit = lease_req.unit
        unit.status = 'occupied'
        
        # Create lease
        lease = Lease(
            unit_id=lease_req.unit_id,
            tenant_id=tenant.id,
            start_date=lease_req.start_date,
            end_date=lease_req.end_date,
            monthly_rent=0  # Will be set separately
        )
        db.session.add(lease)
        db.session.commit()
        
        flash(f'✅ Booking request approved! Lease created for Unit {unit.number}.')
        return redirect(url_for('booking_requests'))

    @app.route('/booking-request/<int:request_id>/reject', methods=['POST'])
    @login_required
    def reject_booking_request(request_id):
        if not is_admin_user():
            return jsonify({'ok': False, 'message': 'Admin access only'}), 403
        
        lease_req = LeaseRequest.query.get(request_id)
        if not lease_req:
            flash('Booking request not found.')
            return redirect(url_for('booking_requests'))
        
        lease_req.status = 'rejected'
        db.session.commit()
        
        flash(f'❌ Booking request rejected.')
        return redirect(url_for('booking_requests'))

    @app.route('/booking-requests/purge-rejected', methods=['POST'])
    @login_required
    def purge_rejected_requests():
        """Admin-only: permanently delete all booking requests with status 'rejected'."""
        if not is_admin_user():
            return jsonify({'ok': False, 'message': 'Admin access only'}), 403
        try:
            deleted = LeaseRequest.query.filter(LeaseRequest.status == 'rejected').delete(synchronize_session=False)
            db.session.commit()
            flash(f'✅ Purged {deleted} rejected booking request(s).')
        except Exception:
            db.session.rollback()
            flash('❌ Error purging rejected requests.', 'error')
        return redirect(url_for('booking_requests'))

    @app.route('/sdg11')
    def sdg11():
        return render_template('sdg11.html')

    @app.route('/features-preview')
    def features_preview():
        """Display available system features and overview."""
        return render_template('features_preview.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        """Main dashboard: displays admin management view or tenant apartment browsing based on user role."""
        is_admin = is_admin_user()
        
        # ADMIN DATA
        units = Unit.query.all()
        leases = Lease.query.all()
        tenants = Tenant.query.all()
        upcoming = [l for l in leases if l.end_date and (l.end_date - datetime.utcnow().date()).days <= 30]
        
        # compute lease balances
        balances = []
        unit_balances = {}
        today = datetime.utcnow().date()
        for l in leases:
            if not l.start_date:
                continue
            months = max(0, (today.year - l.start_date.year) * 12 + (today.month - l.start_date.month))
            expected = months * (l.monthly_rent or 0)
            paid = sum(p.amount for p in (l.payments or []))
            balance = expected - paid
            balances.append({'lease': l, 'expected': expected, 'paid': paid, 'balance': balance})
            unit_balances[l.unit_id] = balance
        
        # map latest tenant per unit
        unit_tenants = {}
        for l in leases:
            try:
                tenant_name = l.tenant.name if l.tenant else None
            except Exception:
                tenant_name = None
            existing = unit_tenants.get(l.unit_id)
            if not existing or (hasattr(l, 'id') and l.id and (not hasattr(existing, 'id') or l.id > existing['lease_id'])):
                unit_tenants[l.unit_id] = {'tenant_name': tenant_name, 'lease_id': getattr(l, 'id', None)}
        
        unit_tenants = {k: v['tenant_name'] for k, v in unit_tenants.items()}
        
        # map latest rent per unit
        unit_latest_rent = {}
        for unit in units:
            latest_lease = Lease.query.filter_by(unit_id=unit.id).order_by(Lease.id.desc()).first()
            unit_latest_rent[unit.id] = latest_lease.monthly_rent if latest_lease else 0
        
        # TENANT DATA
        available_units = []
        for unit in units:
            if unit.status == 'vacant':
                monthly_rent = unit_latest_rent.get(unit.id, 0)
                available_units.append({
                    'unit': unit,
                    'monthly_rent': monthly_rent,
                    'property_name': unit.property.name if unit.property else 'Unknown'
                })
        
        # Return SAME template for both, with conditional rendering inside
        return render_template('dashboard.html', 
                             is_admin=is_admin,
                             units=units, 
                             tenants=tenants, 
                             upcoming=upcoming, 
                             balances=balances, 
                             unit_balances=unit_balances, 
                             unit_tenants=unit_tenants,
                             unit_latest_rent=unit_latest_rent,
                             available_units=available_units)

    @app.route('/emergency')
    def emergency_lookup():
        q = request.args.get('q')
        results = []
        if q:
            results = EmergencyContact.query.filter(
                (EmergencyContact.unit_identifier.contains(q)) |
                (EmergencyContact.name.contains(q)) |
                (EmergencyContact.phone.contains(q))
            ).all()
        return render_template('emergency.html', results=results, q=q)

    # Tenant Authentication
    @app.route('/tenant-signup', methods=['GET', 'POST'])
    def tenant_signup():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm = request.form.get('confirm_password')
            phone = request.form.get('phone')

            if not username or not email or not password:
                flash('Username, email, and password are required.')
                return redirect(url_for('tenant_signup'))
            
            if password != confirm:
                flash('Passwords do not match.')
                return redirect(url_for('tenant_signup'))
            
            if len(password) < 6:
                flash('Password must be at least 6 characters.')
                return redirect(url_for('tenant_signup'))
            
            if TenantUser.query.filter_by(username=username).first():
                flash('Username already exists.')
                return redirect(url_for('tenant_signup'))
            
            if TenantUser.query.filter_by(email=email).first():
                flash('Email already registered.')
                return redirect(url_for('tenant_signup'))
            
            tenant_user = TenantUser(username=username, email=email, phone=phone)
            tenant_user.set_password(password)
            db.session.add(tenant_user)
            db.session.commit()
            flash('Account created! Please log in.')
            return redirect(url_for('tenant_login'))
        
        return render_template('tenant_signup.html')

    @app.route('/tenant-login', methods=['GET', 'POST'])
    def tenant_login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            tenant = TenantUser.query.filter_by(username=username).first()
            
            if tenant and tenant.check_password(password):
                login_user(tenant)
                flash('Logged in as tenant.')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))
            
            flash('Invalid credentials.')
        
        return render_template('tenant_login.html')

    @app.route('/tenant-logout')
    def tenant_logout():
        logout_user()
        flash('Logged out.')
        return redirect(url_for('index'))



    @app.route('/admin-autologin', methods=['POST'])
    def admin_autologin():
        """Quick admin login from home page using password verification."""
        data = None
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        pw = data.get('password') if data else None
        if not pw:
            return jsonify({'ok': False, 'message': 'Password required.'}), 400
        if pw == 'admin1234':
            admin = User.query.filter_by(username='admin').first()
            if admin:
                login_user(admin)
                return jsonify({'ok': True, 'redirect': url_for('dashboard')})
            return jsonify({'ok': False, 'message': 'Admin user not found.'}), 404
        return jsonify({'ok': False, 'message': 'Incorrect password.'}), 401

    @app.route('/book-unit', methods=['POST'])
    @login_required
    def book_unit():
        """Submit apartment booking request. Only accessible by tenants."""
        if not is_tenant_user():
            return jsonify({'ok': False, 'message': 'Only tenants can book units'}), 403
        
        unit_id = request.form.get('unit_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        notes = request.form.get('notes', '')
        # Normalize/validate inputs
        try:
            unit_id = int(unit_id)
        except Exception:
            return jsonify({'ok': False, 'message': 'Invalid unit id'}), 400
        try:
            # expect ISO date YYYY-MM-DD
            start_date_obj = None
            end_date_obj = None
            if start_date:
                start_date_obj = datetime.fromisoformat(start_date).date()
            if end_date:
                end_date_obj = datetime.fromisoformat(end_date).date()
        except Exception:
            return jsonify({'ok': False, 'message': 'Invalid date format'}), 400
        
        if not all([unit_id, start_date, end_date]):
            return jsonify({'ok': False, 'message': 'All fields required'}), 400
        
        # Check if unit exists and is vacant
        unit = Unit.query.get(unit_id)
        if not unit or unit.status != 'vacant':
            return jsonify({'ok': False, 'message': 'Unit is not available'}), 400
        
        # Create lease request (store tenant_user_id as integer)
        try:
            raw_uid = current_user.get_id()
            if isinstance(raw_uid, str) and '_' in raw_uid:
                tenant_uid = int(raw_uid.split('_', 1)[1])
            else:
                tenant_uid = int(current_user.id)
        except Exception:
            return jsonify({'ok': False, 'message': 'Unable to identify tenant user id'}), 400

        lease_req = LeaseRequest(
            unit_id=unit_id,
            tenant_user_id=tenant_uid,
            start_date=start_date_obj,
            end_date=end_date_obj,
            notes=notes,
            status='pending'
        )
        db.session.add(lease_req)
        db.session.commit()
        
        flash('✅ Booking request submitted! An admin will review your request soon.')
        return jsonify({'ok': True, 'message': 'Booking request created successfully', 'redirect': url_for('dashboard')})

    # Authentication
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                flash('Logged in.')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))
            flash('Invalid credentials.')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        logout_user()
        flash('Logged out.')
        return redirect(url_for('index'))

    @app.route('/change-password', methods=['GET', 'POST'])
    def change_password():
        if request.method == 'POST':
            current = request.form.get('current_password')
            new = request.form.get('new_password')
            confirm = request.form.get('confirm_password')
            if not current_user.check_password(current):
                flash('Current password is incorrect.')
                return redirect(url_for('change_password'))
            if new != confirm:
                flash('New passwords do not match.')
                return redirect(url_for('change_password'))
            if len(new) < 6:
                flash('New password must be at least 6 characters.')
                return redirect(url_for('change_password'))
            u = User.query.get(current_user.id)
            u.set_password(new)
            db.session.commit()
            flash('Password changed successfully.')
            return redirect(url_for('dashboard'))
        return render_template('change_password.html')

    # Maintenance
    @app.route('/maintenance')
    @login_required
    def maintenance_list():
        if not is_admin_user():
            flash('❌ Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        reqs = MaintenanceRequest.query.order_by(MaintenanceRequest.created_at.desc()).all()
        # Build a simple map of unit id -> Unit for display purposes
        units = Unit.query.all()
        unit_map = {u.id: u for u in units}
        return render_template('maintenance.html', reqs=reqs, unit_map=unit_map)

    @app.route('/maintenance/new', methods=['GET', 'POST'])
    def maintenance_create():
        if request.method == 'POST':
            unit_id = request.form.get('unit_id')
            desc = request.form.get('description')
            mr = MaintenanceRequest(unit_id=unit_id, description=desc)
            db.session.add(mr)
            db.session.commit()
            flash('Maintenance request created.')
            return redirect(url_for('maintenance_list'))
        return render_template('maintenance_form.html', req=None)

    @app.route('/maintenance/<int:mid>/edit', methods=['GET', 'POST'])
    def maintenance_edit(mid):
        req = MaintenanceRequest.query.get_or_404(mid)
        if request.method == 'POST':
            req.description = request.form.get('description')
            req.status = request.form.get('status')
            db.session.commit()
            flash('Maintenance request updated.')
            return redirect(url_for('maintenance_list'))
        return render_template('maintenance_form.html', req=req)

    @app.route('/maintenance/<int:mid>/delete', methods=['POST'])
    @login_required
    def maintenance_delete(mid):
        if current_user.__class__.__name__ != 'User':
            flash('❌ Admin access only. You cannot delete maintenance requests.', 'error')
            return redirect(url_for('dashboard'))
        req = MaintenanceRequest.query.get_or_404(mid)
        db.session.delete(req)
        db.session.commit()
        flash('✅ Maintenance request deleted successfully.')
        return redirect(url_for('maintenance_list'))


    # Emergency contacts
    @app.route('/emergency-contacts')
    def emergency_contacts_list():
        contacts = EmergencyContact.query.all()
        return render_template('emergency_contacts.html', contacts=contacts)

    @app.route('/emergency-contacts/new', methods=['GET', 'POST'])
    def emergency_contact_create():
        if request.method == 'POST':
            unit_identifier = request.form.get('unit_identifier')
            name = request.form.get('name')
            phone = request.form.get('phone')
            ec = EmergencyContact(unit_identifier=unit_identifier, name=name, phone=phone)
            db.session.add(ec)
            db.session.commit()
            flash('Emergency contact added.')
            return redirect(url_for('emergency_contacts_list'))
        return render_template('emergency_contact_form.html', contact=None)

    @app.route('/emergency-contacts/<int:cid>/edit', methods=['GET', 'POST'])
    def emergency_contact_edit(cid):
        c = EmergencyContact.query.get_or_404(cid)
        if request.method == 'POST':
            c.unit_identifier = request.form.get('unit_identifier')
            c.name = request.form.get('name')
            c.phone = request.form.get('phone')
            db.session.commit()
            flash('Emergency contact updated.')
            return redirect(url_for('emergency_contacts_list'))
        return render_template('emergency_contact_form.html', contact=c)

    @app.route('/emergency-contacts/<int:cid>/delete', methods=['POST'])
    def emergency_contact_delete(cid):
        c = EmergencyContact.query.get_or_404(cid)
        db.session.delete(c)
        db.session.commit()
        flash('Emergency contact deleted.')
        return redirect(url_for('emergency_contacts_list'))

    # Tenants
    @app.route('/tenants')
    @login_required
    def tenants_list():
        if not is_admin_user():
            flash('❌ Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        tenants = Tenant.query.all()
        return render_template('tenants.html', tenants=tenants)

    @app.route('/tenants/new', methods=['GET', 'POST'])
    def tenant_create():
        if request.method == 'POST':
            name = request.form['name']
            phone = request.form.get('phone')
            email = request.form.get('email')
            t = Tenant(name=name, phone=phone, email=email)
            db.session.add(t)
            db.session.commit()
            flash('Tenant created.')
            return redirect(url_for('tenants_list'))
        return render_template('tenant_form.html', tenant=None)

    @app.route('/tenants/<int:tid>/edit', methods=['GET', 'POST'])
    def tenant_edit(tid):
        tenant = Tenant.query.get_or_404(tid)
        if request.method == 'POST':
            tenant.name = request.form['name']
            tenant.phone = request.form.get('phone')
            tenant.email = request.form.get('email')
            db.session.commit()
            flash('Tenant updated.')
            return redirect(url_for('tenants_list'))
        return render_template('tenant_form.html', tenant=tenant)

    @app.route('/tenants/<int:tid>/delete', methods=['POST'])
    @login_required
    def tenant_delete(tid):
        if current_user.__class__.__name__ != 'User':
            flash('❌ Admin access only. You cannot delete tenants.', 'error')
            return redirect(url_for('dashboard'))
        tenant = Tenant.query.get_or_404(tid)
        db.session.delete(tenant)
        db.session.commit()
        flash('✅ Tenant deleted successfully.')
        return redirect(url_for('tenants_list'))

    # Leases
    @app.route('/leases')
    @login_required
    def leases_list():
        if current_user.__class__.__name__ != 'User':
            flash('❌ Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        leases = Lease.query.all()
        return render_template('leases.html', leases=leases)

    @app.route('/leases/new', methods=['GET', 'POST'])
    def lease_create():
        units = Unit.query.all()
        tenants = Tenant.query.all()
        if request.method == 'POST':
            unit_id = request.form['unit_id']
            tenant_id = request.form['tenant_id']
            start_date = request.form.get('start_date') or None
            end_date = request.form.get('end_date') or None
            monthly_rent = request.form.get('monthly_rent') or 0
            lease = Lease(unit_id=unit_id, tenant_id=tenant_id,
                          start_date=start_date, end_date=end_date,
                          monthly_rent=float(monthly_rent))
            db.session.add(lease)
            # mark unit occupied
            u = Unit.query.get(unit_id)
            if u:
                u.status = 'occupied'
            db.session.commit()
            flash('Lease created.')
            return redirect(url_for('leases_list'))
        return render_template('lease_form.html', units=units, tenants=tenants, lease=None)

    @app.route('/leases/<int:lid>/edit', methods=['GET', 'POST'])
    def lease_edit(lid):
        lease = Lease.query.get_or_404(lid)
        units = Unit.query.all()
        tenants = Tenant.query.all()
        if request.method == 'POST':
            lease.unit_id = request.form['unit_id']
            lease.tenant_id = request.form['tenant_id']
            lease.start_date = request.form.get('start_date') or None
            lease.end_date = request.form.get('end_date') or None
            lease.monthly_rent = float(request.form.get('monthly_rent') or 0)
            db.session.commit()
            flash('Lease updated.')
            return redirect(url_for('leases_list'))
        return render_template('lease_form.html', units=units, tenants=tenants, lease=lease)

    @app.route('/leases/<int:lid>/delete', methods=['POST'])
    @login_required
    def lease_delete(lid):
        if current_user.__class__.__name__ != 'User':
            flash('❌ Admin access only. You cannot delete leases.', 'error')
            return redirect(url_for('dashboard'))
        lease = Lease.query.get_or_404(lid)
        # mark unit vacant
        u = Unit.query.get(lease.unit_id)
        if u:
            u.status = 'vacant'
        db.session.delete(lease)
        db.session.commit()
        flash('✅ Lease deleted.')
        return redirect(url_for('leases_list'))

    # Payments
    @app.route('/payments')
    @login_required
    def payments_list():
        if current_user.__class__.__name__ != 'User':
            flash('❌ Admin access only.', 'error')
            return redirect(url_for('dashboard'))
        payments = Payment.query.order_by(Payment.date.desc()).all()
        return render_template('payments.html', payments=payments)

    @app.route('/payments/new', methods=['GET', 'POST'])
    def payment_create():
        leases = Lease.query.all()
        if request.method == 'POST':
            lease_id = request.form['lease_id']
            amount = float(request.form['amount'] or 0)
            p = Payment(lease_id=lease_id, amount=amount)
            db.session.add(p)
            db.session.commit()
            flash('Payment logged.')
            return redirect(url_for('payments_list'))
        return render_template('payment_form.html', leases=leases)


    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
