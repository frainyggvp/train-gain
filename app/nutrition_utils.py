from dataclasses import dataclass
from . import db
from .models import NutritionPlan
from .meal_plans import MEAL_PLANS


@dataclass
class NutritionInput:
    gender: str
    weight: float
    height: float
    goal: str
    activity_level: str
    trainings_per_week: int
    meals_per_day: int


def get_base_kcal_per_kg(gender: str) -> int:
    if gender == "male":
        return 32
    return 29


def get_activity_multiplier(activity_level: str) -> float:
    multipliers = {
        "low": 0.95,
        "medium": 1.0,
        "high": 1.08,
    }
    return multipliers.get(activity_level, 1.0)


def get_training_bonus(trainings_per_week: int) -> float:
    if trainings_per_week <= 1:
        return 0.0
    if trainings_per_week <= 3:
        return 0.04
    if trainings_per_week <= 5:
        return 0.08
    return 0.12


def calculate_maintenance_calories(data: NutritionInput) -> int:
    base_kcal_per_kg = get_base_kcal_per_kg(data.gender)
    maintenance = data.weight * base_kcal_per_kg
    maintenance *= get_activity_multiplier(data.activity_level)
    maintenance *= (1 + get_training_bonus(data.trainings_per_week))
    return round(maintenance)


def calculate_target_calories(maintenance_calories: int, goal: str) -> int:
    if goal == "cut":
        return round(maintenance_calories * 0.85)
    if goal == "bulk":
        return round(maintenance_calories * 1.10)
    return maintenance_calories


def calculate_protein(weight: float, goal: str) -> int:
    if goal == "cut":
        return round(weight * 2.0)
    return round(weight * 1.8)


def calculate_fat(weight: float, goal: str) -> int:
    if goal == "cut":
        return round(weight * 0.8)
    return round(weight * 0.9)


def calculate_carbs(target_calories: int, protein_g: int, fat_g: int) -> int:
    protein_calories = protein_g * 4
    fat_calories = fat_g * 9
    remaining_calories = target_calories - protein_calories - fat_calories
    return max(0, round(remaining_calories / 4))


def calculate_water(weight: float) -> float:
    return round(weight * 0.03, 1)


def get_calorie_range_key(calories: int) -> str:
    if calories < 1800:
        return "under_1800"
    if calories < 2200:
        return "1800_2199"
    if calories < 2600:
        return "2200_2599"
    return "2600_plus"


def get_meal_plan_options(goal: str, calories: int, meals_per_day: int) -> list:
    calorie_range_key = get_calorie_range_key(calories)

    goal_plans = MEAL_PLANS.get(goal, {})
    meal_count_plans = goal_plans.get(meals_per_day, {})
    plans = meal_count_plans.get(calorie_range_key, [])

    if plans:
        return plans

    fallback_meal_count_plans = goal_plans.get(4, {})
    fallback_plans = fallback_meal_count_plans.get(calorie_range_key, [])
    return fallback_plans or []


def get_goal_recommendations(goal: str) -> list:
    if goal == "bulk":
        return [
            "Старайтесь есть достаточно белка в каждом приёме пищи.",
            "Если вес не растёт 2 недели подряд, добавьте примерно 150–200 ккал в день.",
            "Основную часть углеводов удобно есть до и после тренировки.",
            "Не пытайтесь набирать массу слишком резко — умеренный профицит работает лучше.",
        ]

    return [
        "Старайтесь сохранять высокий уровень белка в течение дня.",
        "Если вес не снижается 2 недели подряд, уменьшите рацион примерно на 100–150 ккал.",
        "Овощи и продукты с высоким насыщением помогут легче держать дефицит.",
        "Не снижайте калории слишком сильно, чтобы не терять мышцы и энергию.",
    ]


def get_product_substitutions() -> dict:
    return {
        "Белковые продукты": [
            "Куриная грудка ↔ индейка ↔ нежирная говядина ↔ рыба ↔ яйца",
            "Творог ↔ греческий йогурт ↔ мягкий творог без сахара",
        ],
        "Углеводы": [
            "Рис ↔ гречка ↔ булгур ↔ макароны из твёрдых сортов ↔ картофель",
            "Овсянка ↔ мюсли без сахара ↔ цельнозерновой хлеб",
        ],
        "Жиры": [
            "Орехи ↔ арахисовая паста ↔ авокадо ↔ оливковое масло",
        ],
        "Овощи и фрукты": [
            "Овощи можно менять почти свободно: огурцы, помидоры, брокколи, морковь, салат, кабачки",
            "Фрукты тоже можно чередовать: яблоки, бананы, ягоды, груши, апельсины",
        ],
    }


def calculate_nutrition_plan(data: NutritionInput) -> dict:
    maintenance_calories = calculate_maintenance_calories(data)
    target_calories = calculate_target_calories(maintenance_calories, data.goal)

    protein_g = calculate_protein(data.weight, data.goal)
    fat_g = calculate_fat(data.weight, data.goal)
    carbs_g = calculate_carbs(target_calories, protein_g, fat_g)
    water_l = calculate_water(data.weight)
    meal_plan_options = get_meal_plan_options(
        goal=data.goal,
        calories=target_calories,
        meals_per_day=data.meals_per_day,
    )

    return {
        "maintenance_calories": maintenance_calories,
        "target_calories": target_calories,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "water_l": water_l,
        "goal": data.goal,
        "meals_per_day": data.meals_per_day,
        "calorie_range_key": get_calorie_range_key(target_calories),
        "meal_plan_options": meal_plan_options,
        "recommendations": get_goal_recommendations(data.goal),
        "substitutions": get_product_substitutions(),
    }


def save_nutrition_plan_for_user(user, nutrition_input: NutritionInput, result: dict):
    NutritionPlan.query.filter_by(user_id=user.id, is_current=True).update({"is_current": False})

    plan = NutritionPlan(
        user_id=user.id,
        is_current=True,

        gender=nutrition_input.gender,
        weight=nutrition_input.weight,
        height=nutrition_input.height,
        goal=nutrition_input.goal,
        activity_level=nutrition_input.activity_level,
        trainings_per_week=nutrition_input.trainings_per_week,
        meals_per_day=nutrition_input.meals_per_day,

        maintenance_calories=result["maintenance_calories"],
        target_calories=result["target_calories"],
        protein_g=result["protein_g"],
        fat_g=result["fat_g"],
        carbs_g=result["carbs_g"],
        water_l=result["water_l"],
        calorie_range_key=result["calorie_range_key"],
    )

    plan.meal_plan_options = result.get("meal_plan_options", [])
    plan.recommendations = result.get("recommendations", [])
    plan.substitutions = result.get("substitutions", {})

    db.session.add(plan)
    db.session.commit()
    return plan