from flask_login import UserMixin
from datetime import datetime
import json
from .extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    email_verified_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.username}>"

    @property
    def current_subscription(self):
        active_subscriptions = [
            sub for sub in self.subscriptions
            if sub.status == "active" and sub.expires_at > datetime.utcnow()
        ]
        if not active_subscriptions:
            return None
        return sorted(active_subscriptions, key=lambda s: s.expires_at, reverse=True)[0]

    @property
    def has_active_subscription(self):
        return self.current_subscription is not None


    @property
    def is_email_verified(self):
        return self.email_verified_at is not None


class MuscleGroup(db.Model):
    __tablename__ = "muscle_group"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    workouts = db.relationship(
        "Workout",
        back_populates="muscle_group",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<MuscleGroup {self.name}>"


class Workout(db.Model):
    __tablename__ = "workout"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    muscle_group_id = db.Column(
        db.Integer,
        db.ForeignKey("muscle_group.id"),
        nullable=False
    )
    preview = db.Column(db.String(300), nullable=True)
    difficulty = db.Column(db.String(20), nullable=False, default="easy")
    location = db.Column(db.String(20), nullable=False, default="home")

    muscle_group = db.relationship("MuscleGroup", back_populates="workouts")
    exercises = db.relationship(
        "Exercise",
        back_populates="workout",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Workout {self.title}>"


class Exercise(db.Model):
    __tablename__ = "exercise"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    video_url = db.Column(db.String(255), nullable=True)

    reps_beginner = db.Column(db.String(50), nullable=True)
    reps_intermediate = db.Column(db.String(50), nullable=True)
    reps_advanced = db.Column(db.String(50), nullable=True)

    workout_id = db.Column(
        db.Integer,
        db.ForeignKey("workout.id"),
        nullable=False
    )

    workout = db.relationship("Workout", back_populates="exercises")

    def __repr__(self):
        return f"<Exercise {self.name}>"


class NutritionPlan(db.Model):
    __tablename__ = "nutrition_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    is_current = db.Column(db.Boolean, default=True, nullable=False, index=True)

    gender = db.Column(db.String(20), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    goal = db.Column(db.String(20), nullable=False)
    activity_level = db.Column(db.String(20), nullable=False)
    trainings_per_week = db.Column(db.Integer, nullable=False)
    meals_per_day = db.Column(db.Integer, nullable=False)

    maintenance_calories = db.Column(db.Integer, nullable=False)
    target_calories = db.Column(db.Integer, nullable=False)
    protein_g = db.Column(db.Integer, nullable=False)
    fat_g = db.Column(db.Integer, nullable=False)
    carbs_g = db.Column(db.Integer, nullable=False)
    water_l = db.Column(db.Float, nullable=False)
    calorie_range_key = db.Column(db.String(50), nullable=False)

    meal_plan_options_json = db.Column(db.Text, nullable=False, default="[]")
    recommendations_json = db.Column(db.Text, nullable=False, default="[]")
    substitutions_json = db.Column(db.Text, nullable=False, default="{}")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship(
        "User",
        backref=db.backref("nutrition_plans", lazy=True, order_by="desc(NutritionPlan.created_at)")
    )

    @property
    def meal_plan_options(self):
        return json.loads(self.meal_plan_options_json or "[]")

    @meal_plan_options.setter
    def meal_plan_options(self, value):
        self.meal_plan_options_json = json.dumps(value, ensure_ascii=False)

    @property
    def recommendations(self):
        return json.loads(self.recommendations_json or "[]")

    @recommendations.setter
    def recommendations(self, value):
        self.recommendations_json = json.dumps(value, ensure_ascii=False)

    @property
    def substitutions(self):
        return json.loads(self.substitutions_json or "{}")

    @substitutions.setter
    def substitutions(self, value):
        self.substitutions_json = json.dumps(value, ensure_ascii=False)

    def to_result_dict(self):
        return {
            "maintenance_calories": self.maintenance_calories,
            "target_calories": self.target_calories,
            "protein_g": self.protein_g,
            "fat_g": self.fat_g,
            "carbs_g": self.carbs_g,
            "water_l": self.water_l,
            "goal": self.goal,
            "meals_per_day": self.meals_per_day,
            "calorie_range_key": self.calorie_range_key,
            "meal_plan_options": self.meal_plan_options,
            "recommendations": self.recommendations,
            "substitutions": self.substitutions,
        }


class UserSubscription(db.Model):
    __tablename__ = "user_subscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    plan_code = db.Column(db.String(50), nullable=False, default="premium_monthly")
    status = db.Column(db.String(20), nullable=False, default="active")

    starts_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    auto_renew = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "subscriptions",
            lazy=True,
            order_by="desc(UserSubscription.created_at)"
        )
    )

    @property
    def is_active(self):
        return self.status == "active" and self.expires_at > datetime.utcnow()

    def __repr__(self):
        return f"<UserSubscription user_id={self.user_id} status={self.status}>"


class PendingRegistration(db.Model):
    __tablename__ = "pending_registration"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at


class PasswordResetCode(db.Model):
    __tablename__ = "password_reset_code"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")

    def is_expired(self):
        return datetime.utcnow() > self.expires_at


class EmailChangeRequest(db.Model):
    __tablename__ = "email_change_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    old_email = db.Column(db.String(120), nullable=True)
    new_email = db.Column(db.String(120), nullable=False)

    old_email_code = db.Column(db.String(10), nullable=True)
    new_email_code = db.Column(db.String(10), nullable=False)

    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")

    def is_expired(self):
        return datetime.utcnow() > self.expires_at