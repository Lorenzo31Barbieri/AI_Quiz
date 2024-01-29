from flask import Flask, render_template, request, session, g, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
import requests
from datetime import datetime
from sqlalchemy import func
import calendar


app = Flask(__name__)
app.secret_key = "txwQJf3kVP0aFJ3wR5QysAL1KJ"
OPENWEATHERMAP_API_KEY = '8450e5b8863aa9828eabbca3aa75132d'

SQLALCHEMY_DATABASE_URI = "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
    username="lbarbieri31",
    password="8Faso+vero",
    hostname="lbarbieri31.mysql.pythonanywhere-services.com",
    databasename="lbarbieri31$quizDb",
)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_POOL_RECYCLE"] = 299
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
db.init_app(app)

class User(db.Model):
    __tablename__ = 'utente'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    punti = db.Column(db.Integer, default=0)

class Domanda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    testo = db.Column(db.Text, nullable=False)

class Risposta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    testo = db.Column(db.Text, nullable=False)
    id_domanda = db.Column(db.Integer, db.ForeignKey('domanda.id'), nullable=False)
    is_correct = db.Column(db.Integer, default=0)
    domanda = db.relationship('Domanda', backref='risposte')

def format_date(value, format='%d %b'):
    return datetime.utcfromtimestamp(value).strftime(format)

app.jinja_env.filters['format_date'] = format_date

def get_current_date():
    current_date = datetime.now()
    day_of_week = calendar.day_name[current_date.weekday()]
    formatted_date = f"{day_of_week} {current_date.day} {current_date.strftime('%b')}"
    return formatted_date

@app.route("/")
def index():
    default_city = "Milan"  # Default city if location not available

    # Fetch weather data for the default city
    weather_data = fetch_weather(default_city)

    return render_template("index.html", weather_data=weather_data, city=default_city, current_date=get_current_date())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        punti = 0

        if password != confirm_password:
            flash("Password and confirm password do not match.", "danger")
        else:
            try:
                user = User(username=username, password=password, punti=punti)
                db.session.add(user)
                db.session.commit()

                flash('Account created successfully', 'success')
                return redirect(url_for("login"))
            except Exception as e:
                flash(f'Error creating account: {str(e)}', 'danger')
                db.session.rollback()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Retrieve the form data (e.g., username and password)
        username = request.form.get("username")
        password = request.form.get("password")

        if validate_login(username, password):
            # Successful login
            session['logged_in'] = True
            session['username'] = username
            flash("Login successful", "success")
            return redirect(url_for("index"))
        else:
            # Failed login
            flash("Incorrect username or password. Please try again.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout successful", "success")
    return redirect(url_for("index"))


def fetch_user_by_id(user_id):
    user = User.query.filter_by(id=user_id).first()
    return user


@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    user = User.query.get(user_id)

    if user:
        try:
            db.session.delete(user)
            db.session.commit()
            flash(f'User with ID {user_id} deleted successfully', 'success')
        except Exception as e:
            flash(f'Error deleting user: {str(e)}', 'error')
            db.session.rollback()

    return redirect(url_for("index"))


@app.route("/quiz")
def quiz():
    if 'logged_in' not in session:
        flash("You need to log in to play the quiz.", "warning")
        return redirect(url_for("login"))

    # Retrieve user points from the database based on the username
    user = User.query.filter_by(username=session['username']).first()
    user_points = user.punti if user else 0

    # Fetch all users and their points, ordered by points in descending order
    ranking_data = db.session.query(User.username, User.punti).order_by(User.punti.desc()).all()

    # Check if a user is logged in
    user_rank = None
    if 'logged_in' in session:
        # Fetch the user's rank
        user_rank = db.session.query(func.count().label('count')).filter(User.punti > user.punti).scalar() + 1

    # Fetch a random question and its choices from the database
    question = Domanda.query.order_by(func.random()).first()

    if question:
        choices = Risposta.query.filter_by(id_domanda=question.id).all()

        return render_template("quiz.html", user_points=user_points, question_id=question.id, question_text=question.testo, choices=choices, ranking_data=ranking_data, user_rank=user_rank)
    else:
        flash("No questions available for the quiz.", "info")
        return redirect(url_for("index"))


@app.route("/ranking")
def ranking():

    # Check if a user is logged in
    user_points = None
    user_rank = None
    if 'logged_in' in session:
        # Retrieve user points from the database based on the username
        user_points = get_user_points(session['username'])
        # Fetch the user's rank
        user_rank = User.query.filter(User.punti > user_points).count() + 1
    # Fetch all users and their points, ordered by points in descending order
    ranking_data = User.query.order_by(User.punti.desc()).all()

    return render_template("ranking.html", ranking_data=ranking_data, user_rank=user_rank)


@app.route("/submit_answer/<int:question_id>", methods=["POST"])
def submit_answer(question_id):
    if 'logged_in' not in session:
        flash("You need to log in to play the quiz.", "warning")
        return redirect(url_for("login"))

    user_answer = request.form.get("choice")

    # Validate user's answer and check if it's correct
    answer = Risposta.query.filter_by(id=user_answer).first()

    if answer and answer.is_correct:
        flash("Correct! Well done!", "success")

        # Award one point to the user
        user = User.query.filter_by(username=session['username']).first()
        user.punti += 1
        db.session.commit()
    else:
        flash("Sorry, that's incorrect.", "danger")

    # Redirect to the next question
    return redirect(url_for("quiz"))


@app.route("/weather", methods=["POST"])
def get_weather():
    city = request.form.get("city")

    if not city:
        flash("Please enter a city.", "warning")
        return redirect(url_for("index"))

    weather_data = fetch_weather(city)
    if weather_data is None:
        flash("City not founded")
        return redirect(url_for("index"))
    return render_template("index.html", weather_data=weather_data, city=city, current_date=get_current_date())

def fetch_weather(city):
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric",
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        weather_data = response.json()

        # Aggiungi le previsioni del tempo giornaliere
        daily_forecast = fetch_daily_forecast(weather_data['coord']['lat'], weather_data['coord']['lon'])
        weather_data['daily_forecast'] = daily_forecast

        return weather_data
    except requests.RequestException as e:
        return None

def fetch_daily_forecast(lat, lon):
    base_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "current,minutely,hourly",  # Escludi le previsioni attuali, ogni minuto e orarie
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric",
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        daily_forecast = response.json()
        return daily_forecast
    except requests.RequestException as e:
        return None


@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')

def get_db():
    if 'db' not in g:
        g.db = db.create_engine(app.config['SQLALCHEMY_DATABASE_URI'], {})
    return g.db

def validate_login(username, password):
    # Query the database to check if the username and password match any user
    user = User.query.filter_by(username=username, password=password).first()

    # If a user with the provided credentials is found, return True; otherwise, return False
    return user is not None

def get_user_points(username):
    # Query the database to get the user's points based on the username
    user = User.query.filter_by(username=username).first()

    # If user data is found, return the points; otherwise, return 0
    return user.punti if user else 0

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.session.close()

if __name__ == '__main__':
    app.run(debug=True)
