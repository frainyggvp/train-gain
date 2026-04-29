import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename

from .extensions import db
from .models import MuscleGroup, Workout, Exercise
from .decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ALLOWED_VIDEO_EXTENSIONS = {"mp4"}


def is_valid_difficulty(value):
    return value in {"easy", "medium", "hard"}


def is_valid_location(value):
    return value in {"home", "gym"}


def allowed_video_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS


def save_video_file(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_video_file(file_storage.filename):
        raise ValueError("Разрешены только mp4-файлы")

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"

    videos_dir = os.path.join(current_app.static_folder, "videos")
    os.makedirs(videos_dir, exist_ok=True)

    file_path = os.path.join(videos_dir, unique_name)
    file_storage.save(file_path)

    return f"videos/{unique_name}"


def delete_video_file(video_path):
    if not video_path:
        return

    full_path = os.path.join(current_app.static_folder, video_path)
    if os.path.exists(full_path):
        os.remove(full_path)


@admin_bp.route("/", methods=["GET", "POST"])
@login_required
@admin_required
def admin_index():
    if request.method == "POST":
        if "add_exercise" in request.form:
            name = request.form.get("exercise_name", "").strip()
            desc = request.form.get("exercise_desc", "").strip()
            workout_id = request.form.get("workout_id")

            reps_beginner = request.form.get("reps_beginner", "").strip() or None
            reps_intermediate = request.form.get("reps_intermediate", "").strip() or None
            reps_advanced = request.form.get("reps_advanced", "").strip() or None

            if not name or not desc or not workout_id:
                flash("Заполните все обязательные поля упражнения", "danger")
                return redirect(url_for("admin.admin_index"))

            workout = Workout.query.get(workout_id)
            if not workout:
                flash("Выбранная тренировка не найдена", "danger")
                return redirect(url_for("admin.admin_index"))

            video_file = request.files.get("exercise_video_file")
            video_path = None

            try:
                if video_file and video_file.filename:
                    video_path = save_video_file(video_file)
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("admin.admin_index"))

            db.session.add(
                Exercise(
                    name=name,
                    description=desc,
                    video_url=video_path,
                    reps_beginner=reps_beginner,
                    reps_intermediate=reps_intermediate,
                    reps_advanced=reps_advanced,
                    workout_id=workout.id
                )
            )
            db.session.commit()
            flash(f"Упражнение '{name}' добавлено", "success")
            return redirect(url_for("admin.admin_index"))

    muscles = MuscleGroup.query.order_by(MuscleGroup.name).all()

    selected_muscle_id = request.args.get("muscle_group_id", "").strip()
    selected_difficulty = request.args.get("difficulty", "").strip()
    selected_location = request.args.get("location", "").strip()

    workouts_query = Workout.query.join(MuscleGroup)

    if selected_muscle_id.isdigit():
        workouts_query = workouts_query.filter(Workout.muscle_group_id == int(selected_muscle_id))

    if is_valid_difficulty(selected_difficulty):
        workouts_query = workouts_query.filter(Workout.difficulty == selected_difficulty)

    if is_valid_location(selected_location):
        workouts_query = workouts_query.filter(Workout.location == selected_location)

    workouts = workouts_query.order_by(MuscleGroup.name.asc(), Workout.title.asc()).all()

    exercise_sort = request.args.get("exercise_sort", "id").strip()

    exercises_query = Exercise.query.join(Workout)

    if exercise_sort == "name":
        exercises = exercises_query.order_by(Exercise.name.asc(), Exercise.id.asc()).all()
    else:
        exercise_sort = "id"
        exercises = exercises_query.order_by(Exercise.id.asc()).all()

    return render_template(
        "admin.html",
        muscles=muscles,
        workouts=workouts,
        exercises=exercises,
        selected_muscle_id=selected_muscle_id,
        selected_difficulty=selected_difficulty,
        selected_location=selected_location,
        exercise_sort=exercise_sort
    )


@admin_bp.route("/add_workout", methods=["POST"])
@login_required
@admin_required
def add_workout():
    title = request.form.get("title", "").strip()
    muscle_group_id = request.form.get("muscle_group_id")
    preview = request.form.get("preview", "").strip() or None
    difficulty = request.form.get("difficulty", "").strip()
    location = request.form.get("location", "").strip()

    if not title or not muscle_group_id:
        flash("Заполните название тренировки и группу мышц", "danger")
        return redirect(url_for("admin.admin_index"))

    if not is_valid_difficulty(difficulty):
        flash("Выберите корректную сложность", "danger")
        return redirect(url_for("admin.admin_index"))

    if not is_valid_location(location):
        flash("Выберите корректный формат тренировки", "danger")
        return redirect(url_for("admin.admin_index"))

    muscle_group = MuscleGroup.query.get(muscle_group_id)
    if not muscle_group:
        flash("Группа мышц не найдена", "danger")
        return redirect(url_for("admin.admin_index"))

    if preview is None:
        if location == "gym":
            preview = "https://atlantkazan.ru/upload/iblock/0fc/j3q05cw5fxrxi6di0cxkvgcr1aiwxt9k/198A8461.jpg"
        else:
            preview = "https://static.tildacdn.com/tild3736-6430-4261-b162-316333623832/photo.png"

    workout = Workout(
        title=title,
        muscle_group_id=muscle_group.id,
        preview=preview,
        difficulty=difficulty,
        location=location,
    )

    db.session.add(workout)
    db.session.commit()

    flash("Тренировка добавлена", "success")
    return redirect(url_for("admin.admin_index"))


@admin_bp.route("/delete_workout/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_workout(id):
    workout = Workout.query.get_or_404(id)
    db.session.delete(workout)
    db.session.commit()
    flash("Тренировка удалена", "success")
    return redirect(url_for("admin.admin_index"))


@admin_bp.route("/delete_exercise/<int:id>", methods=["POST"])
@login_required
@admin_required
def delete_exercise(id):
    exercise = Exercise.query.get_or_404(id)
    delete_video_file(exercise.video_url)
    db.session.delete(exercise)
    db.session.commit()
    flash("Упражнение удалено", "success")
    return redirect(url_for("admin.admin_index"))


@admin_bp.route("/edit_workout/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_workout(id):
    workout = Workout.query.get_or_404(id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        preview = request.form.get("preview", "").strip() or None
        difficulty = request.form.get("difficulty", "").strip()
        location = request.form.get("location", "").strip()

        if not title:
            flash("Название тренировки не может быть пустым", "danger")
            return redirect(url_for("admin.edit_workout", id=id))

        if not is_valid_difficulty(difficulty):
            flash("Выберите корректную сложность", "danger")
            return redirect(url_for("admin.edit_workout", id=id))

        if not is_valid_location(location):
            flash("Выберите корректный формат тренировки", "danger")
            return redirect(url_for("admin.edit_workout", id=id))

        workout.title = title
        workout.preview = preview
        workout.difficulty = difficulty
        workout.location = location

        db.session.commit()
        flash("Тренировка обновлена", "success")
        return redirect(url_for("admin.admin_index"))

    return render_template("edit_workout.html", workout=workout)


@admin_bp.route("/edit_exercise/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_exercise(id):
    exercise = Exercise.query.get_or_404(id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        reps_beginner = request.form.get("reps_beginner", "").strip() or None
        reps_intermediate = request.form.get("reps_intermediate", "").strip() or None
        reps_advanced = request.form.get("reps_advanced", "").strip() or None

        if not name or not description:
            flash("Название и описание обязательны", "danger")
            return redirect(url_for("admin.edit_exercise", id=id))

        video_file = request.files.get("video_file")
        remove_video = request.form.get("remove_video") == "1"

        try:
            if remove_video and exercise.video_url:
                delete_video_file(exercise.video_url)
                exercise.video_url = None

            if video_file and video_file.filename:
                if exercise.video_url:
                    delete_video_file(exercise.video_url)
                exercise.video_url = save_video_file(video_file)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("admin.edit_exercise", id=id))

        exercise.name = name
        exercise.description = description
        exercise.reps_beginner = reps_beginner
        exercise.reps_intermediate = reps_intermediate
        exercise.reps_advanced = reps_advanced

        db.session.commit()
        flash("Упражнение обновлено", "success")
        return redirect(url_for("admin.admin_index"))

    return render_template("edit_exercise.html", exercise=exercise)