from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import os
from werkzeug.utils import secure_filename



app = Flask(__name__)
app.secret_key = "secret123"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Model
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    price = db.Column(db.Integer)
    description = db.Column(db.Text)
    image = db.Column(db.String(300))
    is_hot = db.Column(db.Boolean, default=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # customer info
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text)

    # money
    total_price = db.Column(db.Integer)

    # 🚚 delivery system
    status = db.Column(db.String(50), default="Pending")
    courier_name = db.Column(db.String(100))
    courier_contact = db.Column(db.String(100))
    tracking_id = db.Column(db.String(100))

    # 💰 COD tracking
    payment_status = db.Column(db.String(50), default="Pending")
    cash_status = db.Column(db.String(50), default="Not Received")

    created_at = db.Column(db.DateTime, server_default=db.func.now())

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))

    quantity = db.Column(db.Integer)

class User(db.Model):
   id = db.Column(db.Integer, primary_key=True)
   username = db.Column(db.String(100), unique=True)
   email = db.Column(db.String(100), unique=True)
   password = db.Column(db.String(200))




with app.app_context():
    db.create_all()

@app.route("/")
def home():

    products = Product.query.filter_by(is_hot=True).all()

    return render_template("index.html", products=products)


def is_admin():
    if "user_id" not in session:
        return False

    user = db.session.get(User, session["user_id"])

    if not user:
        return False

    # 🔥 ONLY ONE ADMIN ACCOUNT
    return user.email == "admin@gmail.com"



@app.route("/admin")
def admin_dashboard():

    if not is_admin():
        return redirect(url_for("login"))

    total_orders = Order.query.count()

    cod_received = db.session.query(db.func.sum(Order.total_price)).filter_by(
        cash_status="Received from Courier"
    ).scalar() or 0

    cod_pending = db.session.query(db.func.sum(Order.total_price)).filter_by(
        cash_status="Not Received"
    ).scalar() or 0

    returned_loss = db.session.query(db.func.sum(Order.total_price)).filter_by(
        status="Returned"
    ).scalar() or 0

    delivered = Order.query.filter_by(status="Delivered").count()
    pending = Order.query.filter_by(status="Pending").count()

    return render_template(
        "admin/dashboard.html",
        total_orders=total_orders,
        cod_received=cod_received,
        cod_pending=cod_pending,
        returned_loss=returned_loss,
        delivered=delivered,
        pending=pending
    )
@app.route("/admin/orders")
def admin_orders():

    if not is_admin():
        return redirect(url_for("login"))

    status_filter = request.args.get("status")

    query = Order.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(Order.id.desc()).all()

    # 📊 SUMMARY DATA
    total_orders = Order.query.count()
    pending = Order.query.filter_by(status="Pending").count()
    delivered = Order.query.filter_by(status="Delivered").count()
    returned = Order.query.filter_by(status="Returned").count()

    cod_received = Order.query.filter_by(cash_status="Received from Courier").count()

    return render_template(
        "admin/orders.html",
        orders=orders,
        total_orders=total_orders,
        pending=pending,
        delivered=delivered,
        returned=returned,
        cod_received=cod_received,
        status_filter=status_filter
    )


@app.route("/admin/order/<int:order_id>")
def order_detail(order_id):

    if not is_admin():
        return redirect(url_for("login"))

    order = Order.query.get_or_404(order_id)

    items = OrderItem.query.filter_by(order_id=order.id).all()

    return render_template("admin/order_detail.html", order=order, items=items)    

@app.route("/admin/add_product", methods=["GET", "POST"])
def add_product():

    if not is_admin():
        return redirect(url_for("login"))

    categories = Category.query.all()

    if request.method == "POST":

        name = request.form.get("name")
        price = int(request.form.get("price", 0))
        description = request.form.get("description")
        category_id = request.form.get("category_id")

        is_hot = True if request.form.get("is_hot") == "on" else False

        # ✅ HANDLE IMAGE FILE
        image_file = request.files.get("image")
        filename = None

        if image_file and image_file.filename != "":
            filename = secure_filename(image_file.filename)

            upload_folder = os.path.join("static", "uploads")

            # create folder if not exists
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            image_path = os.path.join(upload_folder, filename)
            image_file.save(image_path)

        # ✅ SAVE PRODUCT
        product = Product(
            name=name,
            price=price,
            description=description,
            image=filename,
            is_hot=is_hot,
            category_id=category_id
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully!", "success")

        return redirect(url_for("admin_products"))

    return render_template("admin/add_product.html", categories=categories)



@app.route("/admin/categories", methods=["GET", "POST"])
def admin_categories():

    if not is_admin():
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")

        if name:
            # prevent duplicate
            existing = Category.query.filter_by(name=name).first()

            if existing:
                flash("Category already exists!", "danger")
            else:
                new_cat = Category(name=name)
                db.session.add(new_cat)
                db.session.commit()
                flash("Category added!", "success")

        return redirect(url_for("admin_categories"))

    categories = Category.query.all()
    return render_template("admin/categories.html", categories=categories)


@app.route("/admin/delete_category/<int:id>")
def delete_category(id):

    if not is_admin():
        return redirect(url_for("login"))

    cat = Category.query.get(id)

    if cat:
        db.session.delete(cat)
        db.session.commit()
        flash("Category deleted", "info")

    return redirect(url_for("admin_categories"))
    

@app.route("/category/<int:id>")
def category_products(id):

    products = Product.query.filter_by(category_id=id).all()
    

    return render_template("category.html", products=products)


@app.route("/product/<int:id>")
def product_detail(id):

    product = Product.query.get(id)

    if not product:
        return "Product not found"

    return render_template("product_detail.html", product=product)


@app.route("/admin/edit_product/<int:id>", methods=["GET","POST"])
def edit_product(id):

    product = Product.query.get_or_404(id)

    if request.method == "POST":

        product.name = request.form["name"]
        product.price = request.form["price"]
        product.description = request.form["description"]
        product.image = request.form["image"]
        product.is_hot = True if request.form.get("is_hot") else False

        db.session.commit()

        flash("Product updated!", "success")
        return redirect(url_for("admin_products"))

    return render_template("admin/edit_product.html", product=product)


@app.route("/admin/order/update/<int:order_id>", methods=["GET", "POST"])
def update_order(order_id):

    if not is_admin():
        return redirect(url_for("login"))

    order = Order.query.get_or_404(order_id)

    if request.method == "POST":

        order.status = request.form["status"]
        order.courier_name = request.form["courier_name"]
        order.courier_contact = request.form["courier_contact"]
        order.cash_status = request.form["cash_status"]
        db.session.commit()

        flash("Order updated successfully!", "success")
        return redirect(url_for("admin_orders"))

    return render_template("admin/update_order.html", order=order)

@app.route("/admin/delete_product/<int:id>")
def delete_product(id):

    if not is_admin():
        return redirect(url_for("login"))

    product = Product.query.get_or_404(id)

    db.session.delete(product)
    db.session.commit()

    flash("Product deleted!", "info")

    return redirect(url_for("admin_products"))


@app.route("/admin/products")
def admin_products():

   if not is_admin():
       return redirect(url_for("login"))

   products = Product.query.all()

   return render_template("admin/products.html", products=products)



   return redirect(url_for("admin_products"))
    





@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        # check duplicates
        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

    return render_template("register.html")
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):

            session["user_id"] = user.id
            session["username"] = user.username

            flash("Login successful!", "success")

            if user.email == "admin@gmail.com":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("home"))

        else:
            flash("Invalid email or password", "danger")

            # 🔥 IMPORTANT: return login page again
            return render_template("login.html")

    # ✅ ALWAYS return for GET request
    return render_template("login.html")
@app.route("/logout")
def logout():

    session.pop("user_id", None)
    session.pop("username", None)

    flash("Logged out successfully", "info")

    return redirect(url_for("login"))


@app.route("/buy_now/<int:product_id>")
def buy_now(product_id):

    product = Product.query.get(product_id)

    if not product:
        return "Product not found"

    return render_template("order_form.html", product=product)


@app.route("/place_order/<int:product_id>", methods=["POST"])
def place_order(product_id):

    product = Product.query.get_or_404(product_id)

    name = request.form["name"]
    phone = request.form["phone"]
    email = request.form.get("email")
    address = request.form["address"]

    # 🧾 STEP 1: CREATE ORDER
    order = Order(
        name=name,
        phone=phone,
        email=email,
        address=address,
        total_price=product.price
    )

    db.session.add(order)
    db.session.commit()   # 🔥 IMPORTANT (get order.id)

    # 🛒 STEP 2: ADD ORDER ITEM
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=1
    )

    db.session.add(item)
    db.session.commit()


    flash("Your order has been received! Thank you 😊", "success")

    return redirect(url_for("home"))


@app.route("/increase/<int:product_id>")
def increase(product_id):

    cart = session.get("cart", {})
    product_id = str(product_id)

    if product_id in cart:
        cart[product_id] += 1

    session["cart"] = cart
    session.modified = True

    return redirect(url_for("cart"))



@app.route("/decrease/<int:product_id>")
def decrease(product_id):

    cart = session.get("cart", {})
    product_id = str(product_id)

    if product_id in cart:

        cart[product_id] -= 1

        if cart[product_id] <= 0:
            cart.pop(product_id)

    session["cart"] = cart
    session.modified = True

    return redirect(url_for("cart"))


@app.route("/check_admin")
def check_admin():

    if "user_id" not in session:
        return "Not logged in"

    user = db.session.get(User, session["user_id"])

    return f"User: {user.username}, Admin: {user.is_admin}"



@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):

    cart = session.get("cart", {})

    product_id = str(product_id)

    if product_id in cart:
        cart[product_id] += 1
    else:
        cart[product_id] = 1

    session["cart"] = cart

    print("CART:", session["cart"]) 
    flash("Product added to cart!", "success")

    return redirect(url_for("home"))


@app.route("/cart")
def cart():

    cart = session.get("cart", {})

    cart_items = []
    total = 0

    for product_id, qty in cart.items():
        product = db.session.get(Product, int(product_id))

        if product:
            item_total = product.price * qty
            total += item_total

            cart_items.append({
                "product": product,
                "quantity": qty,
                "total": item_total
            })

    return render_template("cart.html", cart_items=cart_items, total=total)

@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):

    cart = session.get("cart", {})

    product_id = str(product_id)

    if product_id in cart:
        cart.pop(product_id)

    session["cart"] = cart

    flash("Item removed", "info")

    return redirect(url_for("cart"))


@app.route("/checkout")
def checkout():

    cart = session.get("cart", {})

    cart_items = []
    total = 0

    for product_id, qty in cart.items():
        product = db.session.get(Product, int(product_id))

        if product:
            item_total = product.price * qty
            total += item_total

            cart_items.append({
                "product": product,
                "quantity": qty,
                "total": item_total
            })

    return render_template("checkout.html", cart_items=cart_items, total=total)


@app.route("/place_order_cart", methods=["POST"])
def place_order_cart():

    cart = session.get("cart", {})

    if not cart:
        flash("Cart is empty!", "danger")
        return redirect(url_for("home"))

    name = request.form["name"]
    phone = request.form["phone"]
    email = request.form.get("email")
    address = request.form["address"]

    total_price = 0

    # calculate total
    for product_id, qty in cart.items():
        product = Product.query.get(int(product_id))
        total_price += product.price * qty

    # create order
    order = Order(
        name=name,
        phone=phone,
        email=email,
        address=address,
        total_price=total_price
    )

    db.session.add(order)
    db.session.commit()

    # save items
    for product_id, qty in cart.items():
        item = OrderItem(
            order_id=order.id,
            product_id=int(product_id),
            quantity=qty
        )
        db.session.add(item)

    db.session.commit()

    # clear cart
    session.pop("cart", None)

    flash("Order placed successfully!", "success")

    return redirect(url_for("home"))



@app.route("/admin/analytics")
def admin_analytics():

    if not is_admin():
        return redirect(url_for("login"))

    orders = Order.query.all()

    total_orders = len(orders)

    pending = Order.query.filter_by(status="Pending").count()
    on_way = Order.query.filter_by(status="On Way").count()
    delivered = Order.query.filter_by(status="Delivered").count()
    returned = Order.query.filter_by(status="Returned").count()

    total_revenue = sum(o.total_price for o in orders if o.status == "Delivered")
    cod_received = sum(o.total_price for o in orders if o.cash_status == "Received")
    cod_pending = sum(o.total_price for o in orders if o.cash_status == "Not Received")

    return render_template(
        "admin/analytics.html",
        total_orders=total_orders,
        pending=pending,
        on_way=on_way,
        delivered=delivered,
        returned=returned,
        total_revenue=total_revenue,
        cod_received=cod_received,
        cod_pending=cod_pending
    )        

@app.context_processor
def inject_categories():
    return dict(nav_categories=Category.query.all())

if __name__ == "__main__":
    app.run(debug=True)