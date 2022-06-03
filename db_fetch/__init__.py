from contextlib import closing
import sqlite3

DATABASE = r"database.db"


def execute_db(sql: str, parameters):
    with closing(sqlite3.connect(DATABASE)) as con:
        with con:
            cur = con.cursor()
            data = cur.execute(sql, parameters).fetchall()
            return data


# def create_user(user):
#     execute_db(
#         """INSERT INTO Users VALUES (?, ?, ?, ?, NULL, ?)""",
#         (user.id, user.username, user.email, user.password, user.is_admin)
#     )

def create_customer(user_id, username, email, password):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""INSERT INTO Users VALUES ('{user_id}', '{username}', '{email}', '{password}', NULL, 0);"""
    cur.execute(query)
    cur.execute(f"""INSERT INTO Customers (user_id) VALUES ('{user_id}')""")
    con.commit()
    con.close()


def _exists(table, **kwargs):
    """ Checks if attribute value pair exists in the table """
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()

    # Can't check if exists if there's no attribute
    assert kwargs, "Must check at least 1 attribute"

    # Selection statements
    selection = []

    # Loop through attribute and value pairs and format there
    for attribute, value in kwargs.items():
        selection.append(f"""{attribute} = {repr(value)}""")

    # Join statements with "OR" if more than one
    selection = " OR ".join(selection)

    # Create query
    query = f"""SELECT * FROM {table} WHERE {selection};"""

    # Fetch the results of the query
    result = cur.execute(query).fetchone()

    # Returns True if it exists
    return bool(result)


def email_exists(email):
    return _exists("Users", email=email)


def username_exists(username):
    return _exists("Users", username=username)


def admin_exists():
    return username_exists("admin")


def user_auth(username, password):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""SELECT * FROM Users WHERE username = '{username}' and password = '{password}';"""
    user_data = cur.execute(query).fetchone()
    con.close()
    return user_data


def retrieve_user(user_id):
    """ Returns user_data using user_id """
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""SELECT * FROM Users WHERE user_id = '{user_id}';"""
    user_data = cur.execute(query).fetchone()
    con.close()

    # Returns a tuple if found else None
    return user_data


def create_admin(admin_id, username, email, password):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""INSERT INTO Users VALUES('{admin_id}', '{username}', '{email}', '{password}', NULL, 1);"""
    cur.execute(query)
    con.commit()
    con.close()

""" Start of Order functions"""

def create_order_details(order_id, user_id, shipping_option):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""INSERT INTO OrderDetails VALUES('{order_id}', '{user_id}', '{shipping_option}');"""
    cur.execute(query)
    con.commit()
    con.close()

def get_order_details(user_id):
    """ Returns order details using order_id"""
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""SELECT * FROM OrderDetails WHERE user_id = '{user_id}';"""
    order_data = cur.execute(query).fetchone()
    con.close()

    return order_data

def get_order_items(book_id):
    """ Returns book's order items using book_id"""
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""SELECT quantity FROM OrderItems WHERE book_id = '{book_id}';"""
    order_items = cur.execute(query).fetchone()
    con.close()

    return order_items

""" End of Order functions"""

""" Start of Shopping Cart functions """
def create_shopping_cart(user_id, book_id, quantity):
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""INSERT INTO CartItems VALUES('{user_id}', '{book_id}', '{quantity}');"""
    cur.execute(query)
    con.commit()
    con.close()
    
def get_shopping_cart(user_id):
    """ Returns user's shopping cart info using user_id"""
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    query = f"""SELECT book_id, quantity FROM CartItems WHERE user_id = '{user_id}';"""
    cart_data = cur.execute(query).fetchone()
    con.close()

    return cart_data

""" End of Shopping Cart functions """