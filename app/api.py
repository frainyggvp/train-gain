from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from .extensions import db
from .models import MuscleGroup, Workout, Exercise, NutritionPlan
from .nutrition_utils import (
    NutritionInput,
    calculate_nutrition_plan,
    save_nutrition_plan_for_user,
)

api = Blueprint("api", __name__, url_prefix="/api")


def muscle_to_dict(muscle):
    return {
        "id": muscle.id,
        "name": muscle.name,
    }


def workout_to_dict(workout, include_exercises=False):
    data = {
        "id": workout.id,
        "title": workout.title,
        "muscle_group_id": workout.muscle_group_id,
        "muscle_group_name": workout.muscle_group.name if workout.muscle_group else None,
        "preview": workout.preview,
        "difficulty": workout.difficulty,
        "location": workout.location,
    }

    if include_exercises:
        data["exercises"] = [
            exercise_to_dict(exercise)
            for exercise in workout.exercises
        ]

    return data


def exercise_to_dict(exercise):
    return {
        "id": exercise.id,
        "name": exercise.name,
        "description": exercise.description,
        "video_url": exercise.video_url,
        "reps_beginner": exercise.reps_beginner,
        "reps_intermediate": exercise.reps_intermediate,
        "reps_advanced": exercise.reps_advanced,
        "workout_id": exercise.workout_id,
    }


def validate_nutrition_json(data):
    if not isinstance(data, dict):
        raise ValueError("Тело запроса должно быть JSON-объектом")

    gender = str(data.get("gender", "")).strip()
    goal = str(data.get("goal", "")).strip()
    activity_level = str(data.get("activity_level", "")).strip()

    try:
        weight = float(data.get("weight", 0))
        height = float(data.get("height", 0))
        trainings_per_week = int(data.get("trainings_per_week", 0))
        meals_per_day = int(data.get("meals_per_day", 0))
    except (TypeError, ValueError):
        raise ValueError("Проверьте числовые поля: weight, height, trainings_per_week, meals_per_day")

    if gender not in {"male", "female"}:
        raise ValueError("Пол должен быть male или female")

    if goal not in {"bulk", "cut"}:
        raise ValueError("Цель должна быть bulk или cut")

    if activity_level not in {"low", "medium", "high"}:
        raise ValueError("Уровень активности должен быть low, medium или high")

    if weight <= 0 or height <= 0:
        raise ValueError("Рост и вес должны быть больше нуля")

    if trainings_per_week < 0 or trainings_per_week > 14:
        raise ValueError("Количество тренировок должно быть от 0 до 14")

    if meals_per_day not in {3, 4, 5}:
        raise ValueError("Количество приёмов пищи должно быть 3, 4 или 5")

    return NutritionInput(
        gender=gender,
        weight=weight,
        height=height,
        goal=goal,
        activity_level=activity_level,
        trainings_per_week=trainings_per_week,
        meals_per_day=meals_per_day,
    )


@api.route("/health", methods=["GET"])
def health():
    """
    Проверка работоспособности API
    ---
    tags:
      - System
    responses:
      200:
        description: API работает
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
            app:
              type: string
              example: TrainGain
    """
    return jsonify({
        "status": "ok",
        "app": "TrainGain",
    })


@api.route("/muscles", methods=["GET"])
@login_required
def get_muscles():
    """
    Получить список мышечных групп
    ---
    tags:
      - Muscles
    responses:
      200:
        description: Список мышечных групп
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                example: 1
              name:
                type: string
                example: Грудь
    """
    muscles = MuscleGroup.query.order_by(MuscleGroup.name).all()
    return jsonify([muscle_to_dict(muscle) for muscle in muscles])


@api.route("/workouts", methods=["GET"])
@login_required
def get_workouts():
    """
    Получить список тренировок с фильтрацией
    ---
    tags:
      - Workouts
    parameters:
      - name: muscle_group_id
        in: query
        type: integer
        required: false
        description: ID мышечной группы
      - name: difficulty
        in: query
        type: string
        required: false
        enum: [easy, medium, hard]
        description: Сложность тренировки
      - name: location
        in: query
        type: string
        required: false
        enum: [home, gym]
        description: Место тренировки
    responses:
      200:
        description: Список тренировок
        schema:
          type: array
          items:
            type: object
    """
    muscle_group_id = request.args.get("muscle_group_id", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    location = request.args.get("location", "").strip()

    query = Workout.query.join(MuscleGroup)

    if muscle_group_id.isdigit():
        query = query.filter(Workout.muscle_group_id == int(muscle_group_id))

    if difficulty in {"easy", "medium", "hard"}:
        query = query.filter(Workout.difficulty == difficulty)

    if location in {"home", "gym"}:
        query = query.filter(Workout.location == location)

    workouts = query.order_by(MuscleGroup.name.asc(), Workout.title.asc()).all()

    return jsonify([
        workout_to_dict(workout)
        for workout in workouts
    ])


@api.route("/workouts/<int:workout_id>", methods=["GET"])
@login_required
def get_workout(workout_id):
    """
    Получить тренировку по ID вместе с упражнениями
    ---
    tags:
      - Workouts
    parameters:
      - name: workout_id
        in: path
        type: integer
        required: true
        description: ID тренировки
    responses:
      200:
        description: Информация о тренировке
        schema:
          type: object
      404:
        description: Тренировка не найдена
    """
    workout = Workout.query.get_or_404(workout_id)
    return jsonify(workout_to_dict(workout, include_exercises=True))


@api.route("/exercises", methods=["GET"])
@login_required
def get_exercises():
    """
    Получить список упражнений
    ---
    tags:
      - Exercises
    parameters:
      - name: workout_id
        in: query
        type: integer
        required: false
        description: ID тренировки
      - name: q
        in: query
        type: string
        required: false
        description: Поиск по названию упражнения
    responses:
      200:
        description: Список упражнений
        schema:
          type: array
          items:
            type: object
    """
    workout_id = request.args.get("workout_id", "").strip()
    search_query = request.args.get("q", "").strip()

    query = Exercise.query

    if workout_id.isdigit():
        query = query.filter(Exercise.workout_id == int(workout_id))

    if search_query:
        query = query.filter(Exercise.name.ilike(f"%{search_query}%"))

    exercises = query.order_by(Exercise.name.asc(), Exercise.id.asc()).all()

    return jsonify([
        exercise_to_dict(exercise)
        for exercise in exercises
    ])


@api.route("/nutrition/calculate", methods=["POST"])
@login_required
def api_calculate_nutrition():
    """
    Рассчитать план питания
    ---
    tags:
      - Nutrition
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - gender
            - weight
            - height
            - goal
            - activity_level
            - trainings_per_week
            - meals_per_day
          properties:
            gender:
              type: string
              enum: [male, female]
              example: male
            weight:
              type: number
              example: 80
            height:
              type: number
              example: 180
            goal:
              type: string
              enum: [bulk, cut]
              example: bulk
            activity_level:
              type: string
              enum: [low, medium, high]
              example: medium
            trainings_per_week:
              type: integer
              example: 3
            meals_per_day:
              type: integer
              enum: [3, 4, 5]
              example: 4
    responses:
      200:
        description: Рассчитанный план питания
        schema:
          type: object
      400:
        description: Ошибка валидации
    """
    try:
        nutrition_input = validate_nutrition_json(request.get_json(silent=True))
        result = calculate_nutrition_plan(nutrition_input)
        return jsonify(result)

    except ValueError as e:
        return jsonify({
            "error": str(e)
        }), 400


@api.route("/nutrition/save", methods=["POST"])
@login_required
def api_save_nutrition():
    """
    Рассчитать и сохранить план питания текущего пользователя
    ---
    tags:
      - Nutrition
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            gender:
              type: string
              example: male
            weight:
              type: number
              example: 80
            height:
              type: number
              example: 180
            goal:
              type: string
              example: bulk
            activity_level:
              type: string
              example: medium
            trainings_per_week:
              type: integer
              example: 3
            meals_per_day:
              type: integer
              example: 4
    responses:
      200:
        description: План питания сохранён
      400:
        description: Ошибка валидации
      403:
        description: Нет активной подписки
    """
    if not current_user.has_active_subscription:
        return jsonify({
            "error": "Для сохранения плана питания нужна активная подписка"
        }), 403

    try:
        nutrition_input = validate_nutrition_json(request.get_json(silent=True))
        result = calculate_nutrition_plan(nutrition_input)
        saved_plan = save_nutrition_plan_for_user(current_user, nutrition_input, result)

        return jsonify({
            "message": "План питания сохранён",
            "plan": saved_plan.to_result_dict(),
        })

    except ValueError as e:
        return jsonify({
            "error": str(e)
        }), 400


@api.route("/profile/nutrition", methods=["GET"])
@login_required
def get_current_nutrition_plan():
    """
    Получить текущий сохранённый план питания пользователя
    ---
    tags:
      - Nutrition
    responses:
      200:
        description: Текущий план питания
      404:
        description: План не найден
    """
    plan = NutritionPlan.query.filter_by(
        user_id=current_user.id,
        is_current=True
    ).first()

    if not plan:
        return jsonify({
            "error": "Сохранённый план питания не найден"
        }), 404

    return jsonify(plan.to_result_dict())