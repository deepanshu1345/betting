import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from flask import Flask
from pymongo import MongoClient

# Create a Flask server
server = Flask(__name__)
server.secret_key = 'your_secret_key'

# Create a Dash app
app = dash.Dash(__name__, server=server, suppress_callback_exceptions=True)

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client.football_betting

# Define layout of the Dash app
app.layout = html.Div([
    html.H1("Betting Analytics"),
    dcc.Graph(id='win_loss_graph'),
    dcc.Graph(id='earnings_losses_graph')
])

# Callback for win/loss graph
@app.callback(
    dash.dependencies.Output('win_loss_graph', 'figure'),
    []
)
def update_win_loss_graph():
    bets = list(db.bets.find({"username": "test_user"}))  # Replace with actual username logic
    wins = 0
    losses = 0

    for bet in bets:
        if bet['result'] == "Win":
            wins += 1
        elif bet['result'] == "Lose":
            losses += 1

    return {
        'data': [
            go.Bar(
                x=['Wins', 'Losses'],
                y=[wins, losses],
                marker={'color': ['green', 'red']}
            )
        ],
        'layout': go.Layout(
            title='Wins vs Losses',
            xaxis={'title': 'Outcome'},
            yaxis={'title': 'Count'}
        )
    }

# Callback for earnings/losses graph
@app.callback(
    dash.dependencies.Output('earnings_losses_graph', 'figure'),
    []
)
def update_earnings_losses_graph():
    bets = list(db.bets.find({"username": "test_user"}))  # Replace with actual username logic
    earnings = 0
    losses = 0

    for bet in bets:
        if bet['result'] == "Win":
            earnings += bet['amount'] * 2
        elif bet['result'] == "Lose":
            losses += bet['amount']

    return {
        'data': [
            go.Bar(
                x=['Earnings', 'Losses'],
                y=[earnings, losses],
                marker={'color': ['blue', 'orange']}
            )
        ],
        'layout': go.Layout(
            title='Earnings vs Losses',
            xaxis={'title': 'Type'},
            yaxis={'title': 'Amount'}
        )
    }

if __name__ == '__main__':
    app.run_server(debug=True)
