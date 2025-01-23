from fastapi import FastAPI, HTTPException, status, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sqlite3
import jwt
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional

# FastAPI instance
app = FastAPI()


oauth_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ========================
# Database Setup
# ========================
DATABASE = 'orders_and_categories.db'

def get_db():
    db_connection = sqlite3.connect(DATABASE, check_same_thread=False)
    db_connection.row_factory = sqlite3.Row  # Enable access by column name
    return db_connection

# ========================
# Pydantic Models
# ========================
class OrderItem(BaseModel):
    dish_id: int
    quantity: int

class CreateOrder(BaseModel):
    user_id: int
    items: List[OrderItem]

class OrderResponse(BaseModel):
    order_id: int
    user_id: int
    items: List[OrderItem]
    status: str

class UpdateOrderStatus(BaseModel):
    status: str

class CategoryResponse(BaseModel):
    category_id: int
    name: str

class CreateCategory(BaseModel):
    name: str

class UpdateCategory(BaseModel):
    name: str

# ========================
# Feedback Models
# ========================
class Feedback(BaseModel):
    user_id: int
    order_id: int
    dish_id: int
    comments: str
    rating: int  # Rating can be between 1 and 5

class FeedbackResponse(BaseModel):
    message: str

# ========================
# Order Management Routes
# ========================
@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED, tags=["Order Management"])
async def create_order(order: CreateOrder):
    try:
        db = get_db()
        cursor = db.cursor()

        # Insert order into orders table
        cursor.execute('INSERT INTO orders (user_id, status) VALUES (?, ?)', (order.user_id, 'Booked Successfully'))
        db.commit()
        order_id = cursor.lastrowid  # Get the last inserted order ID

        # Insert order items into order_items table
        for item in order.items:
            cursor.execute('INSERT INTO order_items (order_id, dish_id, quantity) VALUES (?, ?, ?)', 
                           (order_id, item.dish_id, item.quantity))
        db.commit()

        return {
            "order_id": order_id,
            "user_id": order.user_id,
            "items": order.items,
            "status": "Booked Successfully"
        }
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error creating order: {str(e)}")

@app.get("/users/{user_id}/orders", response_model=List[OrderResponse], tags=["Order Management"])
async def get_user_orders(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM orders WHERE user_id = ?', (user_id,))
    orders = cursor.fetchall()

    if not orders:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orders found for user")

    response_orders = []
    for order in orders:
        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order["order_id"],))
        items = cursor.fetchall()
        order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]
        response_orders.append({
            "order_id": order["order_id"],
            "user_id": order["user_id"],
            "items": order_items,
            "status": order["status"]
        })
    
    return response_orders

@app.patch("/orders/{order_id}/status", response_model=OrderResponse, tags=["Order Management"])
async def update_order_status(order_id: int, status_update: UpdateOrderStatus,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    order = cursor.fetchone()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    
    cursor.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status_update.status, order_id))
    db.commit()

    cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,))
    items = cursor.fetchall()
    order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]

    return {
        "order_id": order["order_id"],
        "user_id": order["user_id"],
        "items": order_items,
        "status": status_update.status
    }

@app.get("/orders", response_model=List[OrderResponse], tags=["Order Management"])
async def get_all_orders():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM orders')
    orders = cursor.fetchall()

    if not orders:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orders found")

    response_orders = []
    for order in orders:
        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order["order_id"],))
        items = cursor.fetchall()
        order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]
        response_orders.append({
            "order_id": order["order_id"],
            "user_id": order["user_id"],
            "items": order_items,
            "status": order["status"]
        })
    
    return response_orders




@app.post("/token")
async def token_generate(form_data: OAuth2PasswordRequestForm = Depends()):
    # Example: We return the username as the access token (in a real-world scenario, JWT tokens are recommended)
    return {"access_token": form_data.username, "token_type": "bearer"}

# ========================
# Category Management Routes
# ========================
@app.get("/categories", response_model=List[CategoryResponse], tags=["Category Management"])
async def get_categories(token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM categories')
    categories = cursor.fetchall()

    if not categories:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No categories found")

    return [{"category_id": category["category_id"], "name": category["name"]} for category in categories]

@app.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED, tags=["Category Management"])
async def add_category(category: CreateCategory,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category already exists
    cursor.execute('SELECT * FROM categories WHERE name = ?', (category.name,))
    existing_category = cursor.fetchone()
    if existing_category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")

    # Insert the new category into the database
    cursor.execute('INSERT INTO categories (name) VALUES (?)', (category.name,))
    db.commit()

    return {
        "category_id": cursor.lastrowid,
        "name": category.name
    }

@app.put("/categories/{category_id}", tags=["Category Management"])
async def update_category(category_id: int, updated_category: UpdateCategory,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category exists
    cursor.execute('SELECT * FROM categories WHERE category_id = ?', (category_id,))
    existing_category = cursor.fetchone()
    if not existing_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Check if the new name already exists in another category
    cursor.execute('SELECT * FROM categories WHERE name = ? AND category_id != ?', (updated_category.name, category_id))
    duplicate_category = cursor.fetchone()
    if duplicate_category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name already exists")

    # Update the category name
    cursor.execute('UPDATE categories SET name = ? WHERE category_id = ?', (updated_category.name, category_id))
    db.commit()

    return {
        "message": f"Category with ID {category_id} updated successfully",
        "category_id": category_id,
        "name": updated_category.name
    }

@app.delete("/categories/{category_id}", tags=["Category Management"])
async def delete_category(category_id: int,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category exists
    cursor.execute('SELECT * FROM categories WHERE category_id = ?', (category_id,))
    existing_category = cursor.fetchone()
    if not existing_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Delete the category
    cursor.execute('DELETE FROM categories WHERE category_id = ?', (category_id,))
    db.commit()

    return {
        "message": f"Category with ID {category_id} deleted successfully"
    }

# ========================
# Feedback Routes
# ========================
@app.post("/feedback", response_model=FeedbackResponse, tags=["Feedback"])
async def submit_feedback(feedback: Feedback):
    db = get_db()
    cursor = db.cursor()

    try:
        # Check if the order exists
        cursor.execute('SELECT * FROM orders WHERE order_id = ?', (feedback.order_id,))
        order = cursor.fetchone()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

        # Insert feedback into feedback table
        cursor.execute('''INSERT INTO feedback (user_id, order_id, dish_id, comments, rating)
                          VALUES (?, ?, ?, ?, ?)''', 
                          (feedback.user_id, feedback.order_id, feedback.dish_id, feedback.comments, feedback.rating))
        db.commit()

        return {"message": "Feedback submitted successfully"}
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error submitting feedback: {str(e)}")

@app.get("/menu/dishes/{dish_id}/feedback", response_model=List[Feedback], tags=["Feedback"])
async def get_feedback_for_dish(dish_id: int):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''SELECT * FROM feedback WHERE dish_id = ?''', (dish_id,))
    feedbacks = cursor.fetchall()

    if not feedbacks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No feedback found for this dish")

    return [
        {"user_id": feedback["user_id"], 
         "order_id": feedback["order_id"], 
         "dish_id": feedback["dish_id"], 
         "comments": feedback["comments"], 
         "rating": feedback["rating"]}
        for feedback in feedbacks
    ]

# ========================
# Database Initialization
# ========================
@app.on_event("startup")
def startup():
    db = get_db()
    cursor = db.cursor()
    
    # Create the orders table
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL
    )''')

    # Create the order_items table
    cursor.execute('''CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        dish_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
    )''')

    # Create the categories table
    cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )''')

    # Create the feedback table
    cursor.execute('''CREATE TABLE IF NOT EXISTS feedback (
        feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        dish_id INTEGER NOT NULL,
        comments TEXT,
        rating INTEGER NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
        FOREIGN KEY (dish_id) REFERENCES order_items (dish_id)
    )''')

    # Predefined categories to insert
    predefined_categories = [
        'Appetizer', 'Veg Curries', 'Pickles', 'Veg Fry', 'Dal',
        'Non Veg Curries', 'Veg Rice', 'Non-Veg Rice', 'Veg Pulusu', 'Breads', 'Desserts'
    ]
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO categories (name) VALUES (?)', [(name,) for name in predefined_categories])
        db.commit()

