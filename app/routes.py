from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from .extensions import db, limiter
from .utils import send_email_message, generate_verification_code
from .models import MuscleGroup, Workout, Exercise, User, NutritionPlan, UserSubscription, EmailChangeRequest
from .nutrition_utils import NutritionInput, calculate_nutrition_plan, save_nutrition_plan_for_user

main = Blueprint("main", __name__)


@main.route("/")
def welcome():
    return render_template("welcome.html")


@main.route("/privacy")
def privacy():
    return render_template("privacy.html")


@main.route("/terms")
def terms():
    return render_template("terms.html")


@main.route("/dashboard")
@login_required
def dashboard():
    muscles = MuscleGroup.query.order_by(MuscleGroup.name).all()
    return render_template("index.html", muscles=muscles)


@main.route("/muscle/<int:id>")
@login_required
def muscle_page(id):
    muscle = MuscleGroup.query.get_or_404(id)

    selected_difficulty = request.args.get("difficulty", "").strip()
    selected_location = request.args.get("location", "").strip()

    workouts_query = Workout.query.filter_by(muscle_group_id=id)

    if selected_difficulty in {"easy", "medium", "hard"}:
        workouts_query = workouts_query.filter_by(difficulty=selected_difficulty)

    if selected_location in {"home", "gym"}:
        workouts_query = workouts_query.filter_by(location=selected_location)

    workouts = workouts_query.order_by(Workout.title).all()

    return render_template(
        "muscle.html",
        muscle=muscle,
        workouts=workouts,
        selected_difficulty=selected_difficulty,
        selected_location=selected_location,
    )


@main.route("/workout/<int:id>")
@login_required
def workout_page(id):
    workout = Workout.query.get_or_404(id)
    exercises = Exercise.query.filter_by(workout_id=workout.id).order_by(Exercise.id).all()

    return render_template(
        "workout.html",
        workout=workout,
        exercises=exercises,
    )


@main.route("/profile", methods=["GET"])
@login_required
def profile():
    nutrition_plan = NutritionPlan.query.filter_by(
        user_id=current_user.id,
        is_current=True
    ).first()

    subscription = current_user.current_subscription
    email_change_request = EmailChangeRequest.query.filter_by(
        user_id=current_user.id,
        is_used=False
    ).order_by(EmailChangeRequest.created_at.desc()).first()

    if email_change_request and email_change_request.is_expired():
        email_change_request = None

    return render_template(
        "profile.html",
        nutrition_plan=nutrition_plan,
        subscription=subscription,
        email_change_request=email_change_request
    )


@main.route("/profile/change_email/start", methods=["POST"])
@login_required
@limiter.limit("3 per 5 minutes")
def start_email_change():
    new_email = request.form.get("new_email", "").strip().lower()

    if not new_email:
        flash("Введите новый email", "danger")
        return redirect(url_for("main.profile"))

    if current_user.email and new_email == current_user.email:
        flash("Новый email должен отличаться от текущего", "danger")
        return redirect(url_for("main.profile"))

    existing_user = User.query.filter_by(email=new_email).first()
    if existing_user and existing_user.id != current_user.id:
        flash("Этот email уже используется", "danger")
        return redirect(url_for("main.profile"))

    EmailChangeRequest.query.filter_by(user_id=current_user.id, is_used=False).delete(synchronize_session=False)

    old_code = generate_verification_code() if current_user.email else None
    new_code = generate_verification_code()

    req = EmailChangeRequest(
        user_id=current_user.id,
        old_email=current_user.email,
        new_email=new_email,
        old_email_code=old_code,
        new_email_code=new_code,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        is_used=False
    )

    if current_user.email:
        try:
            send_email_message(
                current_user.email,
                "TrainGain | Подтверждение старой почты",
                f"Ваш код подтверждения старой почты: {old_code}\n\nКод действует 15 минут."
            )
        except Exception as e:
            flash(f"Ошибка отправки email на старую почту: {e}", "danger")
            print(e)
            return redirect(url_for("main.profile"))

    try:
        send_email_message(
            new_email,
            "TrainGain | Подтверждение новой почты",
            f"Ваш код подтверждения новой почты: {new_code}\n\nКод действует 15 минут."
        )
    except Exception as e:
        flash(f"Ошибка отправки email на новую почту: {e}", "danger")
        return redirect(url_for("main.profile"))

    db.session.add(req)
    db.session.commit()

    flash("Коды подтверждения отправлены на почту", "success")
    return redirect(url_for("main.profile"))


@main.route("/profile/change_email/confirm", methods=["POST"])
@login_required
@limiter.limit("3 per 5 minutes")
def confirm_email_change():
    old_email_code = request.form.get("old_email_code", "").strip()
    new_email_code = request.form.get("new_email_code", "").strip()

    req = EmailChangeRequest.query.filter_by(
        user_id=current_user.id,
        is_used=False
    ).order_by(EmailChangeRequest.created_at.desc()).first()

    if not req:
        flash("Запрос на смену email не найден", "danger")
        return redirect(url_for("main.profile"))

    if req.is_expired():
        flash("Срок действия кодов истёк", "danger")
        return redirect(url_for("main.profile"))

    if req.old_email:
        if not old_email_code:
            flash("Введите код со старой почты", "danger")
            return redirect(url_for("main.profile"))

        if old_email_code != req.old_email_code:
            flash("Неверный код со старой почты", "danger")
            return redirect(url_for("main.profile"))

    if not new_email_code:
        flash("Введите код с новой почты", "danger")
        return redirect(url_for("main.profile"))

    if new_email_code != req.new_email_code:
        flash("Неверный код с новой почты", "danger")
        return redirect(url_for("main.profile"))

    existing_user = User.query.filter_by(email=req.new_email).first()
    if existing_user and existing_user.id != current_user.id:
        flash("Этот email уже используется", "danger")
        return redirect(url_for("main.profile"))

    current_user.email = req.new_email
    current_user.email_verified_at = datetime.utcnow()
    req.is_used = True

    db.session.commit()

    flash("Email успешно изменён", "success")
    return redirect(url_for("main.profile"))


@main.route("/nutrition", methods=["GET", "POST"])
@login_required
def nutrition():
    result = None
    form_data = {}
    saved_plan = NutritionPlan.query.filter_by(
        user_id=current_user.id,
        is_current=True
    ).first()

    if request.method == "POST":
        if not current_user.has_active_subscription:
            flash("Для доступа к подбору питания нужна активная подписка.", "danger")
            return redirect(url_for("main.profile"))

        try:
            action = request.form.get("action", "calculate").strip()

            gender = request.form.get("gender", "").strip()
            weight = float(request.form.get("weight", 0))
            height = float(request.form.get("height", 0))
            goal = request.form.get("goal", "").strip()
            activity_level = request.form.get("activity_level", "").strip()
            trainings_per_week = int(request.form.get("trainings_per_week", 0))
            meals_per_day = int(request.form.get("meals_per_day", 0))

            form_data = {
                "gender": gender,
                "weight": request.form.get("weight", ""),
                "height": request.form.get("height", ""),
                "goal": goal,
                "activity_level": activity_level,
                "trainings_per_week": request.form.get("trainings_per_week", ""),
                "meals_per_day": request.form.get("meals_per_day", ""),
            }

            if gender not in {"male", "female"}:
                raise ValueError("Выберите пол")

            if goal not in {"bulk", "cut"}:
                raise ValueError("Выберите цель")

            if activity_level not in {"low", "medium", "high"}:
                raise ValueError("Выберите уровень активности")

            if weight <= 0 or height <= 0:
                raise ValueError("Рост и вес должны быть больше нуля")

            if trainings_per_week < 0 or trainings_per_week > 14:
                raise ValueError("Количество тренировок должно быть от 0 до 14")

            if meals_per_day not in {3, 4, 5}:
                raise ValueError("Выберите количество приёмов пищи")

            nutrition_input = NutritionInput(
                gender=gender,
                weight=weight,
                height=height,
                goal=goal,
                activity_level=activity_level,
                trainings_per_week=trainings_per_week,
                meals_per_day=meals_per_day,
            )

            result = calculate_nutrition_plan(nutrition_input)

            if action == "save":
                saved_plan = save_nutrition_plan_for_user(current_user, nutrition_input, result)
                flash("План питания сохранён в профиль.", "success")
                result = saved_plan.to_result_dict()

        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            flash("Не удалось обработать план питания. Проверьте введённые данные.", "danger")

    elif saved_plan and current_user.has_active_subscription:
        result = saved_plan.to_result_dict()
        form_data = {
            "gender": saved_plan.gender,
            "weight": str(saved_plan.weight),
            "height": str(saved_plan.height),
            "goal": saved_plan.goal,
            "activity_level": saved_plan.activity_level,
            "trainings_per_week": str(saved_plan.trainings_per_week),
            "meals_per_day": str(saved_plan.meals_per_day),
        }

    return render_template(
        "nutrition.html",
        result=result,
        form_data=form_data,
        saved_plan=saved_plan,
        has_active_subscription=current_user.has_active_subscription,
    )


@main.route("/subscription/activate", methods=["POST"])
@login_required
def activate_subscription():
    current_sub = current_user.current_subscription

    if current_sub:
        current_sub.expires_at = max(current_sub.expires_at, datetime.utcnow()) + timedelta(days=30)
        current_sub.status = "active"
        db.session.commit()
        flash("Подписка продлена на 30 дней.", "success")
        return redirect(url_for("main.profile"))

    sub = UserSubscription(
        user_id=current_user.id,
        plan_code="premium_monthly",
        status="active",
        starts_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
        auto_renew=False,
    )
    db.session.add(sub)
    db.session.commit()

    flash("Подписка оформлена на 30 дней.", "success")
    return redirect(url_for("main.profile"))