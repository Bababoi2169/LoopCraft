import razorpay
import json
import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from datetime import datetime
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; use real environment variables

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

db_url = os.environ.get('DATABASE_URL', 'sqlite:///ecommerce.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

csrf = CSRFProtect(app)

# ── Razorpay keys — set these in a .env file, never commit them ──
RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

db            = SQLAlchemy(app)
bcrypt        = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view    = 'login'
login_manager.login_message = 'Please log in to access this page.'


# ─────────────────────────── Models ───────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email    = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    addresses  = db.relationship('Address',  backref='user', lazy=True, cascade='all, delete-orphan')
    cart_items = db.relationship('CartItem', backref='user', lazy=True, cascade='all, delete-orphan')
    orders     = db.relationship('Order',    backref='user', lazy=True)

    def get_id(self):           return str(self.id)
    @property
    def is_authenticated(self): return True
    @property
    def is_active(self):        return True
    @property
    def is_anonymous(self):     return False


class Product(db.Model):
    __tablename__ = 'products'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price       = db.Column(db.Float, nullable=False)
    image       = db.Column(db.String(300))
    category    = db.Column(db.String(100))
    stock       = db.Column(db.Integer, default=10)   
    in_stock    = db.Column(db.Boolean, default=True)

    def __repr__(self): return f'<Product {self.name}>'


class Address(db.Model):
    __tablename__ = 'addresses'
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    label   = db.Column(db.String(50), default='Home')
    street  = db.Column(db.String(200))
    city    = db.Column(db.String(100))
    pincode = db.Column(db.String(10))
    lat     = db.Column(db.Float, nullable=True)
    lng     = db.Column(db.Float, nullable=True)


class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    name       = db.Column(db.String(200))
    price      = db.Column(db.Float)
    image      = db.Column(db.String(300))
    quantity   = db.Column(db.Integer, default=1)


class Order(db.Model):
    __tablename__ = 'orders'
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    razorpay_order_id   = db.Column(db.String(100), unique=True)
    razorpay_payment_id = db.Column(db.String(100))
    amount              = db.Column(db.Float)
    status              = db.Column(db.String(30), default='pending')
    tracking_number     = db.Column(db.String(100), nullable=True)
    items_snapshot      = db.Column(db.Text)
    address_snapshot    = db.Column(db.Text)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)

    def items(self):
        return json.loads(self.items_snapshot) if self.items_snapshot else []

    def address(self):
        return json.loads(self.address_snapshot) if self.address_snapshot else {}


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─────────────────────────── Admin Panel ───────────────────────────

def is_admin_user():
    return current_user.is_authenticated and current_user.is_admin


class SecureAdminIndex(AdminIndexView):
    @expose('/')
    def index(self):
        if not is_admin_user():
            return redirect(url_for('login'))
        stats = {
            'users':           User.query.count(),
            'products':        Product.query.count(),
            'cart_items':      CartItem.query.count(),
            'addresses':       Address.query.count(),
            'low_stock_count': Product.query.filter(Product.in_stock == True, Product.stock <= 5).count(),
            'orders':     Order.query.count(),
            'revenue':    db.session.query(db.func.sum(Order.amount)).filter_by(status='paid').scalar() or 0,
        }
        return self.render('admin/index.html', stats=stats)


class SecureModelView(ModelView):
    def is_accessible(self):
        return is_admin_user()
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


class UserAdmin(SecureModelView):
    column_list            = ['id', 'username', 'email', 'is_admin']
    column_searchable_list = ['username', 'email']
    column_filters         = ['is_admin']
    column_editable_list   = ['is_admin']
    form_excluded_columns  = ['password', 'cart_items', 'addresses', 'orders']
    can_export = True
    page_size  = 25


class ProductAdmin(SecureModelView):
    column_list            = ['id', 'name', 'category', 'price', 'stock', 'in_stock']
    column_searchable_list = ['name', 'category']
    column_filters         = ['category', 'in_stock']
    column_editable_list   = ['price', 'in_stock', 'stock']
    column_sortable_list   = ['name', 'price', 'category']
    can_export = True
    page_size  = 25


class OrderAdmin(SecureModelView):
    column_list          = ['id', 'user_id', 'amount', 'status', 'razorpay_payment_id', 'created_at']
    column_filters       = ['status']
    column_sortable_list = ['amount', 'created_at', 'status']
    column_editable_list = ['status', 'tracking_number'] 
    can_create = False
    can_edit   = True
    can_export = True
    page_size  = 25


class CartItemAdmin(SecureModelView):
    column_list    = ['id', 'user_id', 'name', 'price', 'quantity']
    column_filters = ['user_id']
    can_create     = False
    can_export     = True
    page_size      = 25


class AddressAdmin(SecureModelView):
    column_list    = ['id', 'user_id', 'label', 'street', 'city', 'pincode']
    column_filters = ['city', 'label']
    can_export     = True
    page_size      = 25


admin = Admin(app, name='ShopNest Admin', index_view=SecureAdminIndex())
admin.add_view(ProductAdmin(Product,   db.session, name='Products',   endpoint='admin_products'))
admin.add_view(OrderAdmin(Order,       db.session, name='Orders',     endpoint='admin_orders'))
admin.add_view(UserAdmin(User,         db.session, name='Users',      endpoint='admin_users'))
admin.add_view(CartItemAdmin(CartItem, db.session, name='Cart Items', endpoint='admin_cart'))
admin.add_view(AddressAdmin(Address,   db.session, name='Addresses',  endpoint='admin_addresses'))


# ─────────────────────────── Auth Routes ───────────────────────────

@app.route('/')
def index():
    featured_products = Product.query.filter_by(in_stock=True).limit(4).all()
    return render_template('index.html', featured_products=featured_products)


@app.route('/custom-order')
def custom_order():
    return render_template('custom_order.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if not username or not email or not password:
            flash('All fields are required.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'error')
        else:
            hashed   = bcrypt.generate_password_hash(password).decode('utf-8')
            is_first = User.query.count() == 0
            user = User(username=username, email=email, password=hashed, is_admin=is_first)
            db.session.add(user)
            db.session.commit()
            flash('Admin account created! You have full admin access.' if is_first else 'Account created! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.username}!', 'success')

            # ── Safe redirect: only allow relative paths on this host ──
        next_page = request.args.get('next', '')
        parsed    = urlparse(next_page.replace('\\', ''))
        if next_page.startswith('/') and not parsed.netloc and not parsed.scheme:
            return redirect(next_page)
        return redirect(url_for('dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ─────────────────────────── Dashboard ───────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    addresses  = Address.query.filter_by(user_id=current_user.id).all()
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    cart_total = sum(i.price * i.quantity for i in cart_items)
    orders     = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('dashboard.html',
                           addresses=addresses,
                           cart_items=cart_items,
                           cart_total=cart_total,
                           orders=orders)


# ─────────────────────────── Shop ───────────────────────────

PER_PAGE = 12

@app.route('/shop')
def shop():
    category = request.args.get('category', '')
    search   = request.args.get('q', '').strip()
    page     = request.args.get('page', 1, type=int)

    query = Product.query.filter_by(in_stock=True)
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)
    products   = pagination.items
    categories = [c[0] for c in db.session.query(Product.category).distinct().all() if c[0]]

    return render_template('shop.html',
                           products=products,
                           categories=categories,
                           active_category=category,
                           search=search,
                           pagination=pagination)


# ─────────────────────────── Cart ───────────────────────────

@app.route('/cart')
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(i.price * i.quantity for i in items)
    return render_template('cart.html', items=items, total=total)


@app.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    product_id = int(request.form['product_id'])
    product = db.session.get(Product, product_id)
    if not product or not product.in_stock:
        flash('Product not available.', 'error')
        return redirect(url_for('shop'))

    existing = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if existing:
        existing.quantity += 1
    else:
        db.session.add(CartItem(user_id=current_user.id, product_id=product_id,
                                name=product.name, price=product.price, image=product.image))
    db.session.commit()
    flash(f'{product.name} added to cart!', 'success')
    return redirect(url_for('shop'))


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Item removed.', 'info')
    return redirect(url_for('cart'))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    qty  = int(request.form.get('quantity', 1))
    if qty < 1:
        db.session.delete(item)
    else:
        item.quantity = qty
    db.session.commit()
    return redirect(url_for('cart'))


# ─────────────────────────── Addresses ───────────────────────────

@app.route('/address/add', methods=['POST'])
@login_required
def add_address():
    db.session.add(Address(
        user_id=current_user.id,
        label=request.form.get('label', 'Home'),
        street=request.form.get('street', ''),
        city=request.form.get('city', ''),
        pincode=request.form.get('pincode', ''),
        lat=request.form.get('lat') or None,
        lng=request.form.get('lng') or None,
    ))
    db.session.commit()
    flash('Address saved!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/address/delete/<int:addr_id>', methods=['POST'])
@login_required
def delete_address(addr_id):
    addr = Address.query.filter_by(id=addr_id, user_id=current_user.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash('Address removed.', 'info')
    return redirect(url_for('dashboard'))


# ─────────────────────────── Checkout & Payment ───────────────────────────

@app.route('/checkout')
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('cart'))

    addresses = Address.query.filter_by(user_id=current_user.id).all()
    subtotal  = sum(i.price * i.quantity for i in items)
    tax       = 0 
    total     = round(subtotal + tax, 2)

    return render_template('checkout.html',
                           items=items,
                           addresses=addresses,
                           subtotal=subtotal,
                           tax=tax,
                           total=total,
                           razorpay_key=RAZORPAY_KEY_ID)


@app.route('/payment/create', methods=['POST'])
@login_required
def create_payment():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        return jsonify({'error': 'Cart is empty'}), 400

    subtotal     = sum(i.price * i.quantity for i in items)
    total_inr    = round(subtotal, 2)
    amount_paise = int(total_inr * 100)

    address_id = request.form.get('address_id')
    address    = Address.query.filter_by(id=address_id, user_id=current_user.id).first()

    rz_order = razorpay_client.order.create({
        'amount':          amount_paise,
        'currency':        'INR',
        'payment_capture': 1
    })

    items_data = [{'name': i.name, 'price': i.price, 'qty': i.quantity, 'image': i.image} for i in items]
    addr_data  = {'street': address.street, 'city': address.city, 'pincode': address.pincode, 'label': address.label} if address else {}

    order = Order(
        user_id=current_user.id,
        razorpay_order_id=rz_order['id'],
        amount=total_inr,
        status='pending',
        items_snapshot=json.dumps(items_data),
        address_snapshot=json.dumps(addr_data),
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        'razorpay_order_id': rz_order['id'],
        'amount':            amount_paise,
        'currency':          'INR',
        'name':              current_user.username,
        'email':             current_user.email,
    })


@app.route('/payment/success', methods=['POST'])
@login_required
def payment_success():
    payment_id = request.form.get('razorpay_payment_id')
    order_id   = request.form.get('razorpay_order_id')
    signature  = request.form.get('razorpay_signature')

    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id':   order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature':  signature,
        })
        order = Order.query.filter_by(razorpay_order_id=order_id).first_or_404()
        order.status              = 'paid'
        order.razorpay_payment_id = payment_id
        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash('Payment successful! Your order has been placed. 🎉', 'success')
        if order.status == 'paid':
            return redirect(url_for('order_detail', order_id=order.id))

    except razorpay.errors.SignatureVerificationError:
        order = Order.query.filter_by(razorpay_order_id=order_id).first()
        if order.status == 'pending':
            order.status = 'failed'
            db.session.commit()
        flash('Payment verification failed. Please contact support.', 'error')
        return redirect(url_for('cart'))


@app.route('/payment/failed', methods=['POST'])
@login_required
def payment_failed():
    order_id = request.form.get('razorpay_order_id')
    if order_id:
        order = Order.query.filter_by(razorpay_order_id=order_id).first()
        if order and order.status == 'pending':
            order.status = 'failed'
            db.session.commit()
    flash('Payment was cancelled or failed. Your cart is still saved.', 'error')
    return redirect(url_for('cart'))


@app.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('order_detail.html', order=order)


# ─────────────────────────── Seed ───────────────────────────

def seed_products():
    if Product.query.count() == 0:
        demo = [
            Product(name='Wireless Headphones', price=2999, category='Electronics', stock=15,
                    description='Premium sound quality with active noise cancellation and 30-hour battery life.',
                    image='https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400'),
            Product(name='Smart Watch',         price=4999, category='Electronics', stock=8,
                    description='Track fitness, notifications, and more. Water-resistant up to 50m.',
                    image='https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400'),
            Product(name='Running Shoes',       price=1999, category='Footwear',    stock=20,
                    description='Lightweight and breathable design built for long-distance comfort.',
                    image='https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400'),
            Product(name='Backpack',            price=1499, category='Accessories', stock=12,
                    description='Durable 30L backpack with laptop compartment and ergonomic straps.',
                    image='https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400'),
            Product(name='Sunglasses',          price=899,  category='Accessories', stock=25,
                    description='UV400 polarised lenses with lightweight titanium frame.',
                    image='https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=400'),
            Product(name='Laptop Stand',        price=1299, category='Electronics', stock=18,
                    description='Adjustable aluminium stand compatible with all laptops up to 17".',
                    image='https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400'),
        ]
        db.session.add_all(demo)
        db.session.commit()
        print('Demo products seeded.')


with app.app_context():
    db.create_all()
    seed_products()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)
