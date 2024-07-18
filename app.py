from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
import os
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config["MONGO_URI"] = "mongodb://localhost:27017/football_bets"
mongo = PyMongo(app)

API_KEY = '6797e7998467b84988ad54227831de19'
BASE_URL = "https://v3.football.api-sports.io/"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/standings')
def standings():
    league_id = request.args.get('league', '39')  # Default to Premier League (ID: 39)
    season = request.args.get('season', '2024')

    url = f"{BASE_URL}standings?league={league_id}&season={season}"
    headers = {
        'x-apisports-key': API_KEY
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code == 200:
        standings = data['response'][0]['league']['standings'][0]
        return render_template('standings.html', standings=standings)
    else:
        return f"Error: {data['message']}", response.status_code


@app.route('/place_bet', methods=['GET', 'POST'])
def place_bet():
    if request.method == 'POST':
        username = request.form['username']
        team = request.form['team']
        amount = int(request.form['amount'])

        user = mongo.db.users.find_one({"username": username})
        if not user:
            flash('User not found, please sign up first!', 'danger')
            return redirect(url_for('index'))

        if user['balance'] < amount:
            flash('Insufficient balance!', 'danger')
            return redirect(url_for('index'))

        bet = {"username": username, "team": team, "amount": amount}
        mongo.db.bets.insert_one(bet)
        mongo.db.users.update_one({"username": username}, {"$inc": {"balance": -amount}})

        flash('Bet placed successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('bet.html')


@app.route('/sign_up', methods=['POST'])
def sign_up():
    username = request.form['username']
    user = mongo.db.users.find_one({"username": username})

    if user:
        flash('Username already exists!', 'danger')
    else:
        new_user = {"username": username, "balance": 1000}  # New users start with 1000 fake money
        mongo.db.users.insert_one(new_user)
        flash('Sign up successful! You have been credited with 1000 fake money.', 'success')

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
