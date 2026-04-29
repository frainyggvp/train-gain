from app import create_app
from app.db_utils import init_db, seed_data, seed_admin

app = create_app()

init_db(app)
seed_data(app)
seed_admin(app)

if __name__ == "__main__":
    app.run(debug=True)