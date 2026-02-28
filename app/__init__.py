from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, jwt, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.activation import activation_bp
    from .routes.products import products_bp
    from .routes.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(activation_bp, url_prefix='/api/activation')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    # CLI command: create admin
    @app.cli.command('create-admin')
    def create_admin():
        """Create initial admin account."""
        import click
        from werkzeug.security import generate_password_hash
        from .models.user import User

        email = click.prompt('Admin email')
        password = click.prompt('Admin password', hide_input=True, confirmation_prompt=True)

        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.is_admin = True
            db.session.commit()
            click.echo(f'User {email} promoted to admin.')
        else:
            admin = User(
                email=email,
                password_hash=generate_password_hash(password),
                is_admin=True,
            )
            db.session.add(admin)
            db.session.commit()
            click.echo(f'Admin {email} created.')

    return app
