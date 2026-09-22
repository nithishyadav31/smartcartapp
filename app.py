from flask import Flask,render_template,request,session,url_for,flash,redirect,jsonify,make_response
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from utils.pdf_generator import generate_pdf
import os
import random
import bcrypt
import sqlite3
import config
import razorpay
import traceback

app=Flask(__name__)
app.secret_key=config.SECRET_KEY

def get_db_connection():
    conn = sqlite3.connect("smartcart.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS admin (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            profile_image TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            price REAL NOT NULL,
            image TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            amount REAL NOT NULL,
            payment_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()


#Email config
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)

#Route1: Admin signup
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == "GET":
        return render_template("admin/admin_signup.html")
    name = request.form['name']
    email = request.form['email']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admin WHERE email=?", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    session['signup_name'] = name
    session['signup_email'] = email
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')

#Route 2: to get verify otp page
@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():
    return render_template("admin/verify_otp.html")

#Route 3: To get otp 
@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():
    user_otp = request.form['otp']
    password = request.form['password']
    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (?,?,?)",
        (session['signup_name'], session['signup_email'], hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()
    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully!", "success")
    return redirect('/admin-login')

#Route 4:Admin login    

@app.route('/', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        return render_template("admin/admin_login.html")
    email = request.form['email']
    password = request.form['password']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/')
    stored_hashed_password = admin['password']
    if isinstance(stored_hashed_password, str):
        stored_hashed_password = stored_hashed_password.encode('utf-8')

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/')
    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']
    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')

#Route 5:admin dashboard

@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        flash("Please login to access dashboard!", "danger")
        return redirect('/')
    return render_template("admin/dashboard.html", admin_name=session['admin_name'])

UPLOAD_FOLDER='static/uploads/product_images'
app.config['UPLOAD_FOLDER']=UPLOAD_FOLDER

#Route 6:Display add item page

@app.route('/admin/add-item', methods=['GET'])
def add_item_page():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/')

    return render_template("admin/add_item.html")

#Route 7: add item in products table

@app.route('/admin/add-item',methods=['POST'])
def add_item():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']
    
    if image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')
    filename = secure_filename(image_file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, category, price, image) VALUES (?,?,?,?,?)",
        (name, description, category, price, filename)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')

#Route 8:view all items

@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    #  Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    #  Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )

#Route 9:view specific items

@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)


#Route 10: For logout

@app.route('/admin-logout')
def admin_logout():

    # Clear admin session
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')

#Route 11: Display update for specific item

@app.route('/admin/update-item/<int:item_id>',methods=['GET'])
def update_item_page(item_id):
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select * from products where product_id=?',(item_id,))
    product=cursor.fetchone()
    cursor.close()
    conn.close()
    if not product:
        flash('product not found')
        return redirect('/admin/item-list')
    return render_template('/admin/update-item.html',product=product)
    
# ROUTE-12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    new_image = request.files['image']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()
    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']
    if new_image and new_image.filename != "":
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)
        new_image_path=os.path.join(app.config['UPLOAD_FOLDER'],new_filename)
        new_image.save(new_image_path)
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)
        final_image_name=new_filename
    else:
        final_image_name=old_image_name
    cursor.execute(
            """
            UPDATE products
            SET name=?, description=?, category=?, price=?, image=?
            WHERE product_id=?""", 
            (name, description, category, price, final_image_name, item_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')

#Route-13: Delete product based on product id
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select image from products where product_id=?',(item_id,)) 
    product=cursor.fetchone()
    if not product:
        flash('Product not found')
        return redirect('/admin/item-list')
    image_name=product['image']
    image_path=os.path.join(app.config['UPLOAD_FOLDER'],image_name) 
    if os.path.exists(image_path):
        os.remove(image_path)  
    cursor.execute('delete from products where product_id=?',(item_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')

#Route-14: View profile based on id

@app.route('/admin/profile',methods=['GET'])
def admin_profile():
    if 'admin_id' not in session:
        flash('please login again')
        return redirect('/admin-login')
    admin_id=session['admin_id']
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select * from admin where admin_id=?',(admin_id,))
    admin=cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('/admin/admin_profile.html',admin=admin)

#Route 15: update admin profile
# Profile updation
ADMIN_UPLOAD_FOLDER='static/uploads/admin_profile_images'
app.config['ADMIN_UPLOAD_FOLDER']=ADMIN_UPLOAD_FOLDER

@app.route('/admin/profile',methods=['POST'])
def admin_profile_updated():
    if 'admin_id' not in session:
        flash('please login again')
        return redirect('/admin-login')
    admin_id=session['admin_id']
    name=request.form['name']
    new_password=request.form['password']
    email=request.form['email']
    new_image=request.files['profile_image']
    conn=get_db_connection()
    cursor=conn.cursor()
    # fetch old details
    cursor.execute('select * from admin where admin_id=?',(admin_id,))
    admin=cursor.fetchone()
    old_image_name=admin['profile_image']
    
    # new password
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        hashed_password = admin['password']
    
    if new_image and new_image.filename!="":
        
        from werkzeug.utils import secure_filename
        new_filename=secure_filename(new_image.filename)
        image_path=os.path.join(app.config['ADMIN_UPLOAD_FOLDER'],new_filename)
        new_image.save(image_path)
        
        if old_image_name:
            old_image_path=os.path.join(app.config['ADMIN_UPLOAD_FOLDER'],old_image_name)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)
        final_image_name=new_filename
    else:
        final_image_name=old_image_name
    
    cursor.execute("""
        UPDATE admin
        SET name=?, email=?, password=?, profile_image=?
        WHERE admin_id=?""", (name, email, hashed_password, final_image_name, admin_id))
    conn.commit()
    cursor.close()
    conn.close()
    session['admin_name']=name
    session['admin_email']=email
    flash('profile update successfully!')
    return redirect('/admin/profile')

# =================================================================
#  USER Module
# =================================================================

#Route1: user registration

@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    if request.method == 'GET':
        return render_template("user/user_register.html")

    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        flash("Email already registered! Please login.", "danger")
        return redirect('/user-register')

    # Hash password
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Insert new user
    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (?,?,?)",
        (name, email, hashed_password)
    )
    conn.commit()

    cursor.close()
    conn.close()

    flash("Registration successful! Please login.", "success")
    return redirect('/user-login')

#Route2: user login:
@app.route('/user-login',methods=['GET','POST'])

def user_login():
    if request.method=='GET':
        return render_template('user/user_login.html')
    email=request.form['email']
    password=request.form['password']
    #database check
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select * from users where email=?',(email,))
    existing_user=cursor.fetchone()
    if not existing_user:
        flash('user not exist please register')
        return redirect('/user-register')
    stored_hashed_password = existing_user['password']
    if isinstance(stored_hashed_password, str):
        stored_hashed_password = stored_hashed_password.encode('utf-8')
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/user-login')
    session['user_id'] = existing_user['user_id']
    session['user_name'] = existing_user['name']
    session['user_email'] = existing_user['email']
    flash('Login successful!', 'success')
    return redirect('/user-dashboard')

#Route3:user dashboard
@app.route('/user-dashboard',methods=['GET','POST'])
def user_dashboard():
    if 'user_id' not in session:
        flash('please login first!')
        return redirect('/user-login')
    return render_template('user/user_home.html',user_name=session['user_name'])

#Route4: user product listing
@app.route('/user/products')
def user_products():
    
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')
    search=request.args.get('search','')
    category_filter=request.args.get('category','')
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select distinct category from products')
    categories= cursor.fetchall()

    # Build dynamic SQL
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )

#Route5: User product details
@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)

#Route 6: Address details
@app.route('/user/address', methods=['GET', 'POST'])
def user_address():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    if request.method == 'POST':

        session['address'] = {
            'fullname': request.form.get('fullname', '').strip(),
            'mobile': request.form.get('mobile', '').strip(),
            'address': request.form.get('address', '').strip(),
            'city': request.form.get('city', '').strip(),
            'state': request.form.get('state', '').strip(),
            'pincode': request.form.get('pincode', '').strip(),
            'landmark': request.form.get('landmark', '').strip()
        }

        flash("Address saved successfully!", "success")
        return redirect('/user/pay')

    address = session.get('address', {})
    return render_template('user/address.html', address=address)

@app.route('/user/checkout')
def user_checkout():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')
    return redirect('/user/address')

#Route7: user layout
@app.route('/user-logout')
def user_logout():
    session.pop('user_id',None)
    session.pop('user_name',None)
    session.pop('user_email',None)
    flash('Logged out successfully!','success')
    return redirect('/user-login')

# =================================================================
# Cart module
# =================================================================

# Route 1: Add to cart
@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Please login!')
        return redirect('/user-login')
    if 'cart' not in session:
        session['cart']={}
    cart=session['cart']
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select * from products where product_id=?',(product_id,))
    product=cursor.fetchone()
    cursor.close()
    conn.close()
    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer or url_for('user_products'))
    pid=str(product_id)
    
    # If exists → increase quantity
    if pid in cart:
        cart[pid]['quantity']+=1
    else:
        cart[pid]={
            'name':product['name'],
            'price':float(product['price']),
            'image':product['image'],
            'quantity':1
        }
    session['cart']=cart
    flash('Item added to cart','success')
    return redirect(request.referrer or url_for('user_products')) #Return to same page

#Route 2:view cart page
@app.route('/user/cart')
def view_cart():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')
    cart=session.get('cart',{})
    grand_total=sum(item['price']*item['quantity'] for item in cart.values())
    return render_template('/user/cart.html',cart=cart,grand_total=grand_total)


#Route 3: Increase quantity
@app.route("/user/cart/increase/<pid>")
def increase_quantity(pid):
    cart=session.get('cart',{})
    if pid in cart:
        cart[pid]['quantity']+=1
    session['cart']=cart
    return redirect('/user/cart')

#Route 4: Decrease quantity
@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):
    cart=session.get('cart',{})
    if pid in cart:
        cart[pid]['quantity']-=1
        if cart[pid]['quantity']<=0:
            cart.pop(pid)
    session['cart']=cart
    return redirect('/user/cart')

#Route 5: Remove item from cart
@app.route('/user/cart/remove/<pid>')
def remove_item_cart(pid):
    cart=session.get('cart',{})
    if pid in cart:
        cart.pop(pid)
    session['cart']=cart
    return redirect('/user/cart')

# =================================================================
# Payment gateway module
# =================================================================

razorpay_client=razorpay.Client(auth=(config.RAZORPAY_KEY_ID,config.RAZORPAY_KEY_SECRET))

#Route 1:create razorpay order
@app.route('/user/pay')
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    address = session.get('address')

    if not address:
        flash("Please enter your delivery address first.", "info")
        return redirect('/user/address')

    total_amount = sum(
        item['price'] * item['quantity']
        for item in cart.values()
    )

    razorpay_amount = int(total_amount * 100)

    razorpay_order = razorpay_client.order.create({
        'amount': razorpay_amount,
        'currency': 'INR',
        'payment_capture': '1'
    })

    session['razorpay_order_id'] = razorpay_order['id']

    return render_template(
        "user/payment.html",
        amount=total_amount,
        address=address,
        cart=cart,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id']
    )
#Route 2:payment-success page
@app.route('/payment-success')
def payment_success():

    payment_id = request.args.get('payment_id')
    order_id = request.args.get('order_id')

    if not payment_id:
        flash("Payment failed!", "danger")
        return redirect('/user/cart')

    return render_template(
        "user/payment_success.html",
        payment_id=payment_id,
        order_id=order_id
    )

#Route 3: Verify Payment and Store Order
@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    if 'user_id' not in session:
        flash("Please login to complete the payment.", "danger")
        return redirect('/user-login')
    #read values from frontend (payment.html(script))
    razorpay_payment_id=request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')
    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        flash("Payment verification failed (missing data).", "danger")
        return redirect('/user/cart')
    payload = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        # This will raise an error if signature invalid
        razorpay_client.utility.verify_payment_signature(payload)

    except Exception as e:
        # Verification failed
        app.logger.error("Razorpay signature verification failed: %s", str(e))
        flash("Payment verification failed. Please contact support.", "danger")
        return redirect('/user/cart')

    # Signature verified — now store order and items into DB
    user_id = session['user_id']
    cart = session.get('cart', {})

    if not cart:
        flash("Cart is empty. Cannot create order.", "danger")
        return redirect('/user/products')

    total_amount = sum(item['price'] * item['quantity'] for item in cart.values())

    # DB insert: orders and order_items
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Insert into orders table
        cursor.execute("""
            INSERT INTO orders (user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status)
            VALUES (?,?,?,?,?)
        """, (user_id, razorpay_order_id, razorpay_payment_id, total_amount, 'paid'))

        order_db_id = cursor.lastrowid  # newly created order's primary key

        # Insert all items
        for pid_str, item in cart.items():
            product_id = int(pid_str)
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, quantity, price)
                VALUES (?,?,?,?,?)
            """, (order_db_id, product_id, item['name'], item['quantity'], item['price']))

        # Commit transaction
        conn.commit()

        # Save address snapshot keyed by order_db_id for invoice access
        address = session.get('address')
        if address:
            if 'order_addresses' not in session:
                session['order_addresses'] = {}
            session['order_addresses'][str(order_db_id)] = address

        # Clear cart and temporary razorpay order id
        session.pop('cart', None)
        session.pop('razorpay_order_id', None)

        flash("Payment successful and order placed!", "success")
        return redirect(f"/user/order-success/{order_db_id}")

    except Exception as e:
        # Rollback and log error
        conn.rollback()
        app.logger.error("Order storage failed: %s\n%s", str(e), traceback.format_exc())
        flash("There was an error saving your order. Contact support.", "danger")
        return redirect('/user/cart')

    finally:
        cursor.close()
        conn.close()

#Route 4: Order Success Page
@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id=? AND user_id=?", (order_db_id, session['user_id']))
    order=cursor.fetchone()
    cursor.execute('select * from order_items where order_id=?',(order_db_id,))
    items=cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/products')

    # Retrieve the saved address for this order
    address = session.get('order_addresses', {}).get(str(order_db_id))

    return render_template("user/order_success.html", order=order, items=items, address=address)

#Rouute 5:list of my orders page route
@app.route('/user/my-orders')
def my_orders():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (session['user_id'],))
    orders = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("user/my_orders.html", orders=orders)

#Route 6: Generate invoice pdf
@app.route('/user/download-invoice/<int:order_id>')
def download_invoice(order_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('select * from orders where order_id=? and user_id=?',(order_id,session['user_id']))
    order=cursor.fetchone()
    cursor.execute('select * from order_items where order_id=? ',(order_id,))
    items=cursor.fetchall()
    cursor.close()
    conn.close()
    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/my-orders')

    # Retrieve saved delivery address for this order
    address = session.get('order_addresses', {}).get(str(order_id))

    html=render_template("user/invoice.html", order=order, items=items, address=address)
    pdf=generate_pdf(html)
    if not pdf:
        flash("Error generating PDF", "danger")
        return redirect('/user/my-orders')
    
    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"attachment; filename=invoice_{order_id}.pdf"

    return response

if __name__ == '__main__':
    app.run(debug=True)