from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

db = SQLAlchemy()
migrate = Migrate()

def create_app():

    app = Flask(__name__)
    app.config.from_object(Config) # load configuration from config class

    db.init_app(app) # initialize the database with the app
    migrate.init_app(app, db) 

    from app.routes import bp # import the blueprint from routes.py
    app.register_blueprint(bp)

    return app

