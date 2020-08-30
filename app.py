import os
from flask import request

from flask import Flask, session, render_template, flash, redirect, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import requests

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/")
def index():
    return render_template("index.html");

@app.route("/registration")
def registration():
    return render_template("registration.html", header="")

@app.route("/login")
def login():
    return render_template("login.html", header="")

@app.route("/registration_process", methods=["POST"])
def registration_process():
    username = request.form.get("username")
    password = request.form.get("password")
    if not len(db.execute("SELECT * FROM users WHERE username=:username", {"username": username}).fetchall()) is 0:
        return render_template("registration.html", header="user already exists")
    db.execute("INSERT INTO users (username, password) VALUES (:username, :password)",
                {"username": username, "password": password})
    db.commit()
    return render_template("search.html")

@app.route("/login_check",  methods=["POST"])
def login_check():
    username = request.form.get("username")
    password = request.form.get("password")
    if username is None or password is None or len(username) is 0 or len(password) is 0:
        return render_template("login.html", header = "")
    user = db.execute("SELECT * FROM users WHERE username=:username",
            { "username": username} ).fetchone()
    if user is None:
        return render_template("login.html", header = "Account with that User does not exist")
    if password == password:
        session["user_id"] = username
        return render_template("search.html")
    return render_template("login.html", header = "Incorrect Password")

@app.route("/welcome", methods=["POST"])
def welcome():
    key = request.form.get("search_val")
    if key is None or len(key) is 0:
        return render_template("search.html")
    key = "%" + key + "%"

    books = db.execute("SELECT isbn, title, author, year FROM books WHERE isbn LIKE :key \
                        OR title LIKE :key OR author LIKE :key OR year LIKE :key LIMIT 20",
                        {"key": key}).fetchall()
    return render_template("results.html", books=books)

@app.route("/book/<isbn>", methods=['GET','POST'])
def bookpage(isbn):
    if request.method == "POST":
        currentUser = session["user_id"]
        user_id = db.execute("SELECT id FROM users WHERE username=:username", {"username":currentUser}).fetchone()
        user_id = user_id[0]

        # Fetch form data
        rating = request.form.get("rating")
        comment = request.form.get("comment")

        # Search book_id by ISBN
        row = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                        {"isbn": isbn})

        # Save id into variable
        bookId = row.fetchone() # (id,)
        bookId = bookId[0]

        # Check for user submission (ONLY 1 review/user allowed per book)
        row2 = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
                    {"user_id": user_id,
                     "book_id": bookId})

        # A review already exists
        if row2.rowcount == 1:

            flash('You already submitted a review for this book', 'warning')
            return redirect("/book/" + isbn)

        # Convert to save into DB
        rating = int(rating)

        db.execute("INSERT INTO reviews (user_id, book_id, comment, rating) VALUES \
                    (:user_id, :book_id, :comment, :rating)",
                    {"user_id": user_id,
                    "book_id": bookId,
                    "comment": comment,
                    "rating": rating})

        # Commit transactions to DB and close the connection
        db.commit()

        flash('Review submitted!', 'info')

        return redirect("/book/" + isbn)

    book_info = db.execute("SELECT isbn, title, author, year FROM books WHERE isbn=:isbn", {"isbn":isbn}).fetchall()
    key = os.getenv("API_KEY")
    query = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":key, "isbns":isbn})

    response = query.json()
    response = response['books'][0]

    book_info.append(response)

    book = db.execute("SELECT id FROM books WHERE isbn=:isbn", {"isbn":isbn}).fetchone()
    book = book[0]

    reviews = db.execute("SELECT users.username, comment, rating FROM users INNER JOIN reviews ON \
                            users.id = reviews.user_id WHERE book_id = :book",{"book":book}).fetchall()
    if reviews is None:
        reviews = []

    return render_template("bookpage.html", book_info=book_info, reviews=reviews)

@app.route("/api/<isbn>")
def api(isbn):
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn":isbn}).fetchall()
    book = book[0]

    if book is None:
        return jsonify({"Error": "Invalid book ISBN"}), 422

    book = dict(book.items())

    key = os.getenv("API_KEY")
    query = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":key, "isbns":isbn})

    response = query.json()
    response = response['books'][0]

    book['average_score'] = response['average_rating']
    book['review_count'] = response['work_ratings_count']

    return jsonify(book)
