import sqlite3

con = sqlite3.connect("database.db")

# Very scary code, resets your database
# with open("schema.sql") as f:
#     con.executescript(f.read())

#cur = con.cursor()

#cur.execute("""CREATE TABLE Users (
#    user_id TEXT NOT NULL,
#    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
#    email TEXT NOT NULL UNIQUE,
#    password TEXT NOT NULL,
#    profile_pic TEXT,
#    is_admin INTEGER NOT NULL,
#    twoFA_secret_token TEXT,
#    PRIMARY KEY (user_id)
#);""")
# con.commit()

# x = cur.execute("SELECT * FROM Customers;").fetchall()
# for i in x:
#     print(i)
# q = "DELETE FROM Customers WHERE user_id = 'one' or user_id = 'two';"
# cur.execute(q)
# x = cur.execute("SELECT * FROM Customers;").fetchall()
# for i in x:
#     print(i)

# Generate data if we need to fill in
# INSERT into Books VALUES ('19a4cc17-117a-4a20-8ad6-cc3c243e68a7', 'English', 'Classic', "Jabriel's Python Manifesto", 30, 25, 'Jabriel Seah', 'This 3rd edition features decorators, TimSorts, awesome stacks and queues, and async/await. Definitely, one of the python books of all time. Ultra Poggers.', '19a4cc17-117a-4a20-8ad6-cc3c243e68a7_python2.jpg');

con.commit()
con.close()
