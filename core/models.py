from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
# Create your models here.


class Goal(models.Model):
    user=models.ForeignKey(User, on_delete=models.CASCADE,related_name='goals')
    title=models.CharField(blank=False,null=False,max_length= 200)
    status = models.CharField(max_length=20,choices=[("active", "Active"),("completed", "Completed"),("paused", "Paused"),],default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=30,choices=[("personal", "Personal"),("career", "Career"),("education", "Education"),("health", "Health & Fitness"),("finance", "Finance"),("projects", "Projects"),("skills", "Skills"),("other", "Other"),],default="other",)
    priority=models.CharField(max_length=20,choices=[("low","Low"),("medium","Medium"),("high","High"),("critical","Critical")],default="medium")
    days_per_week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(7),])
    hours_per_day = models.DecimalField(max_digits=4,decimal_places=1,validators=[MinValueValidator(0.1),MaxValueValidator(24),])
    start_date = models.DateField()
    target_date = models.DateField()

    def clean(self):
        if self.target_date <= self.start_date:
            raise ValidationError("Target date must be after the start date.")
    
    def __str__(self):
        return self.title

        

class Roadmap(models.Model):
    goal= models.OneToOneField(Goal,on_delete=models.CASCADE,related_name="roadmap")
    title = models.CharField(max_length=200)
    description=models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Milestone(models.Model):
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE,related_name="milestones")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20,choices=[("pending", "Pending"),("in_progress", "In Progress"),("completed", "Completed")],default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def total_tasks(self):
        return Task.objects.filter(
            checkpoint__milestone=self
        ).count()


    @property
    def completed_tasks(self):
        return Task.objects.filter(
            checkpoint__milestone=self,
            status="completed"
        ).count()


    @property
    def progress(self):
        if self.total_tasks == 0:
            return 0

        return round(
            (self.completed_tasks / self.total_tasks) * 100
        )


    @property
    def is_completed(self):
        return self.total_tasks > 0 and (
            self.completed_tasks == self.total_tasks
        )


class Checkpoint(models.Model):
    milestone = models.ForeignKey(Milestone,on_delete=models.CASCADE,related_name="checkpoints")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20,choices=[("pending", "Pending"),("in_progress", "In Progress"),("completed", "Completed"),],default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Task(models.Model):
    checkpoint = models.ForeignKey(Checkpoint,on_delete=models.CASCADE,related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    estimated_minutes = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20,choices=[("pending", "Pending"),("in_progress", "In Progress"),("completed", "Completed")],default="pending")
    completed_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title


class Schedule(models.Model):
    task = models.ForeignKey(Task,on_delete=models.CASCADE,related_name="schedules")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20,choices=[("scheduled", "Scheduled"),("completed", "Completed"),("skipped", "Skipped")],default="scheduled")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration_minutes(self):
        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)
        return int((end - start).total_seconds() / 60)
    
    def __str__(self):
        return f"{self.task.title} - {self.date}"