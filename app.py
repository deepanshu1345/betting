from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from pymongo import MongoClient
import requests
import os
from celery import Celery
import redis
import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client.football_betting

# Redis setup
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Celery configuration
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

BASE_URL = "https://v3.football.api-sports.io/"
API_KEY = "6797e7998467b84988ad54227831de19"
HEADERS = {
    'x-rapidapi-host': "v3.football.api-sports.io",
    'x-rapidapi-key': API_KEY
}

# Helper function to check user login
def is_logged_in():
    return 'username' in session

@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/sign_up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if db.users.find_one({"username": username}):
            flash("Username already exists", "danger")
            return redirect(url_for('sign_up'))

        db.users.insert_one({"username": username, "password": password, "balance": 0})
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('sign_up.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = db.users.find_one({"username": username, "password": password})

        if user:
            session['username'] = username
            flash("Logged in successfully", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out successfully", "success")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))

    user = db.users.find_one({"username": session['username']})
    remaining_balance = user['balance'] - get_total_bets(session['username'])
    upcoming_matches = get_upcoming_matches()
    return render_template('dashboard.html', remaining_balance=remaining_balance, upcoming_matches=upcoming_matches)

@app.route('/place_bet', methods=['GET', 'POST'])
def place_bet():
    if not is_logged_in():
        return redirect(url_for('login'))

    team = request.args.get('team')
    if request.method == 'POST':
        amount = int(request.form['amount'])
        user = db.users.find_one({"username": session['username']})

        if user['balance'] < amount:
            flash("Insufficient balance", "danger")
            return redirect(url_for('place_bet', team=team))

        db.bets.insert_one({"username": session['username'], "team": team, "amount": amount, "result": "Pending"})
        db.users.update_one({"username": session['username']}, {"$inc": {"balance": -amount}})
        flash("Bet placed successfully", "success")

        # Trigger the update_bets task
        update_bets.apply_async()

        return redirect(url_for('dashboard'))

    return render_template('place_bet.html', team=team)

@app.route('/check_bets')
def check_bets():
    if not is_logged_in():
        return redirect(url_for('login'))

    bets = list(db.bets.find({"username": session['username']}))
    return render_template('check_bets.html', bets=bets)

@app.route('/add_money', methods=['GET', 'POST'])
def add_money():
    if not is_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        amount = int(request.form['amount'])
        db.users.update_one({"username": session['username']}, {"$inc": {"balance": amount}})
        flash("Money added successfully", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_money.html')

def get_upcoming_matches():
    url = f"{BASE_URL}fixtures?season=2023&next=10"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        raise Exception("Error fetching upcoming matches")

    matches = response.json().get('response', [])
    upcoming_matches = []
    for match in matches:
        date_time = datetime.strptime(match["fixture"]["date"], "%Y-%m-%dT%H:%M:%S%z")
        date = date_time.strftime("%Y-%m-%d")
        time = date_time.strftime("%H:%M")
        upcoming_match = {
            "date": date,
            "time": time,
            "home_team": match["teams"]["home"]["name"],
            "away_team": match["teams"]["away"]["name"],
            "home_logo": match["teams"]["home"]["logo"],
            "away_logo": match["teams"]["away"]["logo"]
        }
        upcoming_matches.append(upcoming_match)
    return upcoming_matches

def get_total_bets(username):
    total_bets = 0
    bets = db.bets.find({"username": username})
    for bet in bets:
        total_bets += bet['amount']
    return total_bets

def get_match_results(league_id, season, team_id=None):
    endpoint = f"{BASE_URL}fixtures?league={league_id}&season={season}"
    if team_id:
        endpoint += f"&team={team_id}"

    response = requests.get(endpoint, headers=HEADERS)
    if response.status_code != 200:
        raise Exception("Error fetching match results")

    matches = response.json().get('response', [])
    results = []
    for match in matches:
        result = {
            "date": match["fixture"]["date"],
            "home_team": match["teams"]["home"]["name"],
            "away_team": match["teams"]["away"]["name"],
            "home_score": match["goals"]["home"],
            "away_score": match["goals"]["away"]
        }
        results.append(result)
    return results

@celery.task
def update_bets():
    bets = db.bets.find({"result": "Pending"})
    for bet in bets:
        match_results = get_match_results(league_id="39", season="2023")  # Replace with appropriate league and season

        for match in match_results:
            if (match['home_team'] == bet['team'] or match['away_team'] == bet['team']):
                if match['home_score'] > match['away_score'] and match['home_team'] == bet['team']:
                    db.bets.update_one({"_id": bet['_id']}, {"$set": {"result": "Win"}})
                    db.users.update_one({"username": bet['username']}, {"$inc": {"balance": bet['amount'] * 2}})
                elif match['away_score'] > match['home_score'] and match['away_team'] == bet['team']:
                    db.bets.update_one({"_id": bet['_id']}, {"$set": {"result": "Win"}})
                    db.users.update_one({"username": bet['username']}, {"$inc": {"balance": bet['amount'] * 2}})
                else:
                    db.bets.update_one({"_id": bet['_id']}, {"$set": {"result": "Lose"}})



@app.route('/analytics')
def analytics():
    if not is_logged_in():
        return redirect(url_for('login'))

    username = session['username']
    bets = db.bets.find({"username": username})

    total_invested = 0
    total_won = 0
    total_lost = 0

    for bet in bets:
        total_invested += bet['amount']
        if bet['result'] == "Win":
            total_won += bet['amount']
        elif bet['result'] == "Lose":
            total_lost += bet['amount']

    return render_template('analytics.html', total_invested=total_invested, total_won=total_won, total_lost=total_lost)

# Initialize Dash app
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash_app/')

dash_app.layout = html.Div([
    html.H1('Betting Analytics'),
    dcc.Graph(id='analytics-graph')
])

@app.route('/dash_app/')
def dash_app_index():
    return redirect('/dash_app/')  # This route can be simplified if needed, or removed if unnecessary.

# Ensure Dash assets are served correctly
@app.route('/dash_app/assets/<path:path>')
def dash_assets(path):
    return send_from_directory(os.path.join(dash_app.config.assets_folder), path)

@dash_app.callback(
    dash.dependencies.Output('analytics-graph', 'figure'),
    [dash.dependencies.Input('interval-component', 'n_intervals')]
)
def update_graph(n):
    username = session.get('username')  # Use session.get() to avoid KeyError if 'username' is not set
    if not username:
        return go.Figure()  # Return an empty figure or handle the case when user is not logged in

    bets = db.bets.find({"username": username})

    total_invested = 0
    total_won = 0
    total_lost = 0

    for bet in bets:
        total_invested += bet['amount']
        if bet['result'] == "Win":
            total_won += bet['amount']
        elif bet['result'] == "Lose":
            total_lost += bet['amount']

    fig = go.Figure(data=[
        go.Bar(name='Invested', x=['Total'], y=[total_invested]),
        go.Bar(name='Won', x=['Total'], y=[total_won]),
        go.Bar(name='Lost', x=['Total'], y=[total_lost])
    ])

    fig.update_layout(barmode='group', title='Betting Analytics')
    return fig

if __name__ == '__main__':
    app.run(debug=True, host='localhost')
