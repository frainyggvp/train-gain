from app import create_app
from app.db_utils import seed_data, seed_admin

app = create_app()

with app.app_context():
    seed_data(app)
    seed_admin(app)

print("Начальные данные успешно добавлены")