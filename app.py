from flask import Flask,render_template,request,session,url_for,flash,redirect
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import os
import random
import bcrypt
import mysql.connector
import config

app=Flask(__name__)
app.secret_key=config.SECRET_KEY

def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

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
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
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
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
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

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        return render_template("admin/admin_login.html")
    email = request.form['email']
    password = request.form['password']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')
    stored_hashed_password = admin['password'].encode('utf-8')

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')
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
        return redirect('/admin-login')
    return render_template("admin/dashboard.html", admin_name=session['admin_name'])

UPLOAD_FOLDER='static/uploads/product_images'
app.config['UPLOAD_FOLDER']=UPLOAD_FOLDER

#Route 6:Display add item page

@app.route('/admin/add-item', methods=['GET'])
def add_item_page():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

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
        "INSERT INTO products (name, description, category, price, image) VALUES (%s, %s, %s, %s, %s)",
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
    cursor = conn.cursor(dictionary=True)

    #  Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    #  Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
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
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
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
    cursor=conn.cursor(dictionary=True)
    cursor.execute('select * from products where product_id=%s',(item_id,))
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
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
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
            SET name=%s, description=%s, category=%s, price=%s, image=%s
            WHERE product_id=%s""", 
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
    cursor=conn.cursor(dictionary=True)
    cursor.execute('select image from products where product_id=%s',(item_id,)) 
    product=cursor.fetchone()
    if not product:
        flash('Product not found')
        return redirect('/admin/item-list')
    image_name=product['image']
    image_path=os.path.join(app.config['UPLOAD_FOLDER'],image_name) 
    if os.path.exists(image_path):
        os.remove(image_path)  
    cursor.execute('delete from products where product_id=%s',(item_id,))
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
    cursor=conn.cursor(dictionary=True)
    cursor.execute('select * from admin where admin_id=%s',(admin_id,))
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
    cursor=conn.cursor(dictionary=True)
    # fetch old details
    cursor.execute('select * from admin where admin_id=%s',(admin_id,))
    admin=cursor.fetchone()
    old_image_name=admin['profile_image']
    
    # new password
    if new_password:
        hashed_password=bcrypt.hashpw(new_password.encode('utf-8'),bcrypt.gensalt())
    else:
        hashed_password=admin['password']
    
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
        SET name=%s, email=%s, password=%s, profile_image=%s
        WHERE admin_id=%s""", (name, email, hashed_password, final_image_name, admin_id))
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
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        flash("Email already registered! Please login.", "danger")
        return redirect('/user-register')

    # Hash password
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Insert new user
    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
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
    cursor=conn.cursor(dictionary=True)
    cursor.execute('select * from users where email=%s',(email,))
    existing_user=cursor.fetchone()
    if not existing_user:
        flash('user not exist please register')
        return redirect('/user-register')
    stored_hashed_password=existing_user['password'].encode('utf-8')
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/user-login')
    session['user_id'] = existing_user['user_id']
    session['user_name'] = existing_user['name']
    session['user_email'] = existing_user['email']
    flash('Login successfull!,success')
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
    cursor=conn.cursor(dictionary=True)
    cursor.execute('select distinct category from products')
    categories= cursor.fetchall()

    # Build dynamic SQL
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
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
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)
    
#Route6: user layout
@app.route('/user-logout')
def user_logout():
    session.pop('user_id',None)
    session.pop('user_name',None)
    session.pop('user_email',None)
    flash('Logged out successfully!','success')
    return redirect('/user-login')


if __name__ == '__main__':
    app.run(debug=True)