"""
CAMPUSCORE / CampusCore - Student Academic Management & Campus Portal
Tech Stack: Python, Flask 3.0, MongoDB Atlas (pymongo)

Color Theme Palette:
- Ink Black: #0e131f
- Twilight Indigo: #38405f
- Vintage Grape: #59546c
- Cool Steel: #8b939c
- Strawberry Red: #ff0035

Features:
- Landing Page with custom theme, statistics, and course features
- User Authentication (Student, Teacher, Admin) with academic details
- Admin Faculty Management: Check teachers, register faculty, assign/unassign subjects and courses
- Teacher Course Selection & Attendance Roster: Teachers only see courses assigned to them by Admin
- 75% Attendance Safety & Bunk Calculator for students
- Task & Assignment Manager with priorities (High, Medium, Low) and status toggles
- Subject Study Notes Repository (Rich Markdown, Search, Subject tags, Print to PDF, Download .md)
- Enrolled Curriculum Subjects Management with custom icons
- Campus Circulars & Notice Bulletin Board
- Institutional Student Roster & Course Catalog
"""
import os
import sys
import math
from datetime import datetime, date, timedelta, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, Response, session, url_for)
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

# Load .env from campuscore directory
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

# ---------------------------------------------------------------- Database Connection
MONGO_URI = os.getenv("MONGO_URI", "").strip()
if not MONGO_URI:
    MONGO_URI = "mongodb://localhost:27017"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=6000)
    client.admin.command("ping")
    db_name = os.getenv("DB_NAME", "campuscore")
    db = client[db_name]
    mongo_connected = True
except Exception as exc:
    print(f"Notice: MongoDB Atlas connection notice: {exc}", file=sys.stderr)
    try:
        client = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=1000)
        db = client[os.getenv("DB_NAME", "campuscore")]
    except Exception:
        client = MongoClient("mongodb://127.0.0.1:27017", connect=False)
        db = client[os.getenv("DB_NAME", "campuscore")]
    mongo_connected = False

# Collections
users = db.users
tasks = db.tasks
attendance = db.attendance
notes = db.notes
subjects = db.subjects
courses = db.courses
students = db.students
notices = db.notices
assignments = db.assignments
submissions = db.submissions
teacher_student_assignments = db.teacher_student_assignments

# Setup indexes
try:
    users.create_index("username", unique=True)
    users.create_index("email", unique=True, sparse=True)
    courses.create_index("code", unique=True, sparse=True)
    students.create_index("roll_no", unique=True, sparse=True)
    students.create_index("teacher_id")
    attendance.create_index([("student_id", ASCENDING), ("date", ASCENDING), ("subject", ASCENDING)])
    attendance.create_index([("user_id", ASCENDING), ("date", ASCENDING), ("subject", ASCENDING)])
    attendance.create_index([("teacher_id", ASCENDING), ("date", ASCENDING)])
    tasks.create_index([("user_id", ASCENDING), ("status", ASCENDING)])
    notes.create_index([("user_id", ASCENDING), ("subject", ASCENDING)])
    subjects.create_index([("user_id", ASCENDING), ("name", ASCENDING)])
    assignments.create_index([("teacher_id", ASCENDING), ("created_at", DESCENDING)])
    submissions.create_index([("assignment_id", ASCENDING), ("student_id", ASCENDING)])
    submissions.create_index([("teacher_id", ASCENDING), ("status", ASCENDING)])
    teacher_student_assignments.create_index([("teacher_id", ASCENDING), ("student_id", ASCENDING)], unique=True)
except Exception:
    pass

# ---------------------------------------------------------------- Flask App Initialization
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "campuscore-custom-palette-2026")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

STATUSES = ("Present", "Absent", "Late", "Half Day")
PRIORITIES = ("high", "medium", "low")
TASK_STATUSES = ("pending", "in_progress", "completed")
LEVELS = ("school", "college")
BOARDS = ("CBSE", "ICSE", "State Board", "University / Autonomous")

DEFAULT_SUBJECT_ICONS = {
    "Mathematics": "📐",
    "Science": "🧪",
    "Social Science": "🌍",
    "English": "📚",
    "Computer Science": "💻",
    "Computer Science & Engineering": "💻",
    "Physics": "⚡",
    "Chemistry": "🧪",
    "Biology": "🧬",
    "Hindi": "📖",
    "Economics & Commerce": "📈",
    "General": "📝"
}


# ---------------------------------------------------------------- Database Seeding & Auto-Heal
def seed_demo_data():
    """Seed initial demo accounts and ensure proper RBAC relationships."""
    try:
        # 1. Admin account
        if users.count_documents({"username": "admin"}) == 0:
            users.insert_one({
                "username": "admin",
                "email": "admin@campuscore.io",
                "name": "Academic Administrator",
                "role": "admin",
                "level": "college",
                "program": "Campus Admin",
                "board": "University",
                "avatar_color": "#ff0035",
                "password": generate_password_hash("admin123"),
                "created_at": datetime.now(timezone.utc)
            })

        # 2. Teacher 1: Prof. H. Sharma (Computer Science)
        teacher_doc = users.find_one({"username": "teacher"})
        if not teacher_doc:
            teacher_id = users.insert_one({
                "username": "teacher",
                "email": "teacher@campuscore.io",
                "name": "Prof. H. Sharma",
                "role": "teacher",
                "department": "Computer Science",
                "level": "college",
                "program": "Faculty of Engineering",
                "board": "University",
                "avatar_color": "#38405f",
                "assigned_courses": [],
                "password": generate_password_hash("teacher123"),
                "created_at": datetime.now(timezone.utc)
            }).inserted_id
            teacher_doc = users.find_one({"_id": teacher_id})
        t1_id_str = str(teacher_doc["_id"])

        # 3. Teacher 2: Dr. Priya Mehta (Mathematics)
        teacher2_doc = users.find_one({"username": "teacher2"})
        if not teacher2_doc:
            teacher2_id = users.insert_one({
                "username": "teacher2",
                "email": "priya.mehta@campuscore.io",
                "name": "Dr. Priya Mehta",
                "role": "teacher",
                "department": "Mathematics",
                "level": "college",
                "program": "Faculty of Science & Mathematics",
                "board": "University",
                "avatar_color": "#59546c",
                "assigned_courses": [],
                "password": generate_password_hash("teacher123"),
                "created_at": datetime.now(timezone.utc)
            }).inserted_id
            teacher2_doc = users.find_one({"_id": teacher2_id})
        t2_id_str = str(teacher2_doc["_id"])

        # 4. Student 1: Aarav Sharma (CS2026-001) -> assigned to Teacher 1
        student_doc = users.find_one({"username": "student"})
        if not student_doc:
            s1_id = users.insert_one({
                "username": "student",
                "email": "student@campuscore.io",
                "name": "Aarav Sharma",
                "role": "student",
                "roll_no": "CS2026-001",
                "department": "Computer Science",
                "teacher_id": t1_id_str,
                "teacher_name": teacher_doc["name"],
                "level": "college",
                "program": "B.Tech Computer Science",
                "class_name": "Year 2 - Sec A",
                "board": "University",
                "avatar_color": "#ff0035",
                "password": generate_password_hash("student123"),
                "created_at": datetime.now(timezone.utc)
            }).inserted_id
            student_doc = users.find_one({"_id": s1_id})
        else:
            users.update_one({"_id": student_doc["_id"]}, {"$set": {"teacher_id": t1_id_str, "teacher_name": teacher_doc["name"], "roll_no": "CS2026-001", "department": "Computer Science"}})

        s1_id_str = str(student_doc["_id"])

        # 5. Student 2: Diya Sen (CS2026-002) -> assigned to Teacher 1
        student2_doc = users.find_one({"username": "student2"})
        if not student2_doc:
            s2_id = users.insert_one({
                "username": "student2",
                "email": "diya@campuscore.io",
                "name": "Diya Sen",
                "role": "student",
                "roll_no": "CS2026-002",
                "department": "Computer Science",
                "teacher_id": t1_id_str,
                "teacher_name": teacher_doc["name"],
                "level": "college",
                "program": "B.Tech Computer Science",
                "class_name": "Year 2 - Sec A",
                "board": "University",
                "avatar_color": "#ff0035",
                "password": generate_password_hash("student123"),
                "created_at": datetime.now(timezone.utc)
            }).inserted_id
            student2_doc = users.find_one({"_id": s2_id})
        else:
            users.update_one({"_id": student2_doc["_id"]}, {"$set": {"teacher_id": t1_id_str, "teacher_name": teacher_doc["name"], "roll_no": "CS2026-002", "department": "Computer Science"}})

        s2_id_str = str(student2_doc["_id"])

        # 6. Student 3: Rohan Verma (MA2026-001) -> assigned to Teacher 2
        student3_doc = users.find_one({"username": "student3"})
        if not student3_doc:
            s3_id = users.insert_one({
                "username": "student3",
                "email": "rohan@campuscore.io",
                "name": "Rohan Verma",
                "role": "student",
                "roll_no": "MA2026-001",
                "department": "Mathematics",
                "teacher_id": t2_id_str,
                "teacher_name": teacher2_doc["name"],
                "level": "college",
                "program": "B.Sc Mathematics",
                "class_name": "Year 2 - Sec B",
                "board": "University",
                "avatar_color": "#d6ba73",
                "password": generate_password_hash("student123"),
                "created_at": datetime.now(timezone.utc)
            }).inserted_id
            student3_doc = users.find_one({"_id": s3_id})
        else:
            users.update_one({"_id": student3_doc["_id"]}, {"$set": {"teacher_id": t2_id_str, "teacher_name": teacher2_doc["name"], "roll_no": "MA2026-001", "department": "Mathematics"}})

        s3_id_str = str(student3_doc["_id"])

        # 7. Sync students collection records
        students_data = [
            {"roll_no": "CS2026-001", "name": "Aarav Sharma", "email": "student@campuscore.io", "department": "Computer Science", "year": 2, "teacher_id": t1_id_str, "teacher_name": teacher_doc["name"], "user_id": s1_id_str},
            {"roll_no": "CS2026-002", "name": "Diya Sen", "email": "diya@campuscore.io", "department": "Computer Science", "year": 2, "teacher_id": t1_id_str, "teacher_name": teacher_doc["name"], "user_id": s2_id_str},
            {"roll_no": "MA2026-001", "name": "Rohan Verma", "email": "rohan@campuscore.io", "department": "Mathematics", "year": 2, "teacher_id": t2_id_str, "teacher_name": teacher2_doc["name"], "user_id": s3_id_str},
            {"roll_no": "CS2026-004", "name": "Ananya Patel", "email": "ananya@campuscore.io", "department": "Computer Science", "year": 2, "teacher_id": t1_id_str, "teacher_name": teacher_doc["name"], "user_id": ""},
        ]
        for sdata in students_data:
            exist_s = students.find_one({"roll_no": sdata["roll_no"]})
            if not exist_s:
                sdata["created"] = datetime.now(timezone.utc)
                students.insert_one(sdata)
            else:
                students.update_one({"_id": exist_s["_id"]}, {"$set": {"teacher_id": sdata["teacher_id"], "teacher_name": sdata["teacher_name"], "department": sdata["department"]}})

        # 7b. Seed teacher_student_assignments collection (Many-to-Many Relationship)
        assignments_seed = [
            {"teacher_id": t1_id_str, "student_id": s1_id_str, "student_roll": "CS2026-001", "student_name": "Aarav Sharma", "teacher_name": teacher_doc["name"], "assigned_at": "2026-11-20", "status": "active"},
            {"teacher_id": t2_id_str, "student_id": s1_id_str, "student_roll": "CS2026-001", "student_name": "Aarav Sharma", "teacher_name": teacher2_doc["name"], "assigned_at": "2026-11-20", "status": "active"},
            {"teacher_id": t1_id_str, "student_id": s2_id_str, "student_roll": "CS2026-002", "student_name": "Diya Sen", "teacher_name": teacher_doc["name"], "assigned_at": "2026-11-20", "status": "active"},
            {"teacher_id": t2_id_str, "student_id": s3_id_str, "student_roll": "MA2026-001", "student_name": "Rohan Verma", "teacher_name": teacher2_doc["name"], "assigned_at": "2026-11-20", "status": "active"},
        ]
        for aseed in assignments_seed:
            try:
                teacher_student_assignments.update_one(
                    {"teacher_id": aseed["teacher_id"], "student_id": aseed["student_id"]},
                    {"$set": aseed},
                    upsert=True
                )
            except Exception:
                pass

        # 8. Courses
        if courses.count_documents({}) == 0:
            c1 = courses.insert_one({"code": "CS201", "name": "Data Structures & Algorithms", "department": "Computer Science", "credits": 4, "instructor_id": t1_id_str, "instructor": teacher_doc["name"]}).inserted_id
            c2 = courses.insert_one({"code": "CS301", "name": "Database Management Systems", "department": "Computer Science", "credits": 4, "instructor_id": t1_id_str, "instructor": teacher_doc["name"]}).inserted_id
            c3 = courses.insert_one({"code": "MA201", "name": "Discrete Mathematics & Graph Theory", "department": "Mathematics", "credits": 4, "instructor_id": t2_id_str, "instructor": teacher2_doc["name"]}).inserted_id
            users.update_one({"_id": teacher_doc["_id"]}, {"$set": {"assigned_courses": [str(c1), str(c2)]}})
            users.update_one({"_id": teacher2_doc["_id"]}, {"$set": {"assigned_courses": [str(c3)]}})
        else:
            c1_doc = courses.find_one({"code": "CS201"})
            c2_doc = courses.find_one({"code": "CS301"})
            c3_doc = courses.find_one({"code": "MA201"})
            if c1_doc:
                courses.update_one({"_id": c1_doc["_id"]}, {"$set": {"instructor_id": t1_id_str, "instructor": teacher_doc["name"]}})
            if c2_doc:
                courses.update_one({"_id": c2_doc["_id"]}, {"$set": {"instructor_id": t1_id_str, "instructor": teacher_doc["name"]}})
            if c3_doc:
                courses.update_one({"_id": c3_doc["_id"]}, {"$set": {"instructor_id": t2_id_str, "instructor": teacher2_doc["name"]}})
            if c1_doc and c2_doc:
                users.update_one({"_id": teacher_doc["_id"]}, {"$set": {"assigned_courses": [str(c1_doc["_id"]), str(c2_doc["_id"])]}})
            if c3_doc:
                users.update_one({"_id": teacher2_doc["_id"]}, {"$set": {"assigned_courses": [str(c3_doc["_id"])]}})

        # 9. Seed Assignments
        if assignments.count_documents({}) == 0:
            a1 = assignments.insert_one({
                "teacher_id": t1_id_str,
                "teacher_name": teacher_doc["name"],
                "title": "Data Structures Project: Self-Balancing AVL Trees",
                "description": "Implement an AVL Tree class with rotation mechanisms (LL, RR, LR, RL) and write automated test cases for balanced insertions.",
                "subject": "CS201 - Data Structures & Algorithms",
                "due_date": (date.today() + timedelta(days=7)).isoformat(),
                "total_marks": 100,
                "department": "Computer Science",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }).inserted_id

            a2 = assignments.insert_one({
                "teacher_id": t2_id_str,
                "teacher_name": teacher2_doc["name"],
                "title": "Graph Theory Problem Set: Bipartite Matching",
                "description": "Solve exercise problems 4.1 to 4.8 on maximum flow and bipartite graph matchings with detailed proof steps.",
                "subject": "MA201 - Discrete Mathematics",
                "due_date": (date.today() + timedelta(days=5)).isoformat(),
                "total_marks": 50,
                "department": "Mathematics",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }).inserted_id

            # 10. Seed Submissions
            submissions.insert_one({
                "assignment_id": str(a1),
                "assignment_title": "Data Structures Project: Self-Balancing AVL Trees",
                "student_id": s1_id_str,
                "student_name": "Aarav Sharma",
                "student_roll": "CS2026-001",
                "teacher_id": t1_id_str,
                "content": "Implemented complete AVL Tree class with height calculation and single/double rotation helpers. GitHub repo: https://github.com/aarav/avl-trees",
                "submitted_at": datetime.now(timezone.utc) - timedelta(days=1),
                "status": "graded",
                "marks": 94,
                "feedback": "Outstanding work! Code is clean, modular, and the rotation balancing handles all edge cases nicely.",
                "graded_at": datetime.now(timezone.utc)
            })

            submissions.insert_one({
                "assignment_id": str(a1),
                "assignment_title": "Data Structures Project: Self-Balancing AVL Trees",
                "student_id": s2_id_str,
                "student_name": "Diya Sen",
                "student_roll": "CS2026-002",
                "teacher_id": t1_id_str,
                "content": "Completed AVL Tree implementation with in-order traversal and balance factor verification.",
                "submitted_at": datetime.now(timezone.utc),
                "status": "submitted",
                "marks": None,
                "feedback": None,
                "graded_at": None
            })

            submissions.insert_one({
                "assignment_id": str(a2),
                "assignment_title": "Graph Theory Problem Set: Bipartite Matching",
                "student_id": s3_id_str,
                "student_name": "Rohan Verma",
                "student_roll": "MA2026-001",
                "teacher_id": t2_id_str,
                "content": "Solutions to problems 4.1 through 4.8 with Hall's Marriage Theorem applications.",
                "submitted_at": datetime.now(timezone.utc),
                "status": "submitted",
                "marks": None,
                "feedback": None,
                "graded_at": None
            })

        # 11. Seed Attendance Records
        today_iso = date.today().isoformat()
        yesterday_iso = (date.today() - timedelta(days=1)).isoformat()
        if attendance.count_documents({"teacher_id": t1_id_str}) == 0:
            attendance.insert_many([
                {
                    "student_id": s1_id_str,
                    "user_id": s1_id_str,
                    "teacher_id": t1_id_str,
                    "teacher_name": teacher_doc["name"],
                    "student_name": "Aarav Sharma",
                    "student_roll": "CS2026-001",
                    "subject": "CS201",
                    "date": today_iso,
                    "status": "Present",
                    "timestamp": datetime.now(timezone.utc)
                },
                {
                    "student_id": s1_id_str,
                    "user_id": s1_id_str,
                    "teacher_id": t1_id_str,
                    "teacher_name": teacher_doc["name"],
                    "student_name": "Aarav Sharma",
                    "student_roll": "CS2026-001",
                    "subject": "CS201",
                    "date": yesterday_iso,
                    "status": "Present",
                    "timestamp": datetime.now(timezone.utc) - timedelta(days=1)
                },
                {
                    "student_id": s2_id_str,
                    "user_id": s2_id_str,
                    "teacher_id": t1_id_str,
                    "teacher_name": teacher_doc["name"],
                    "student_name": "Diya Sen",
                    "student_roll": "CS2026-002",
                    "subject": "CS201",
                    "date": today_iso,
                    "status": "Present",
                    "timestamp": datetime.now(timezone.utc)
                },
                {
                    "student_id": s3_id_str,
                    "user_id": s3_id_str,
                    "teacher_id": t2_id_str,
                    "teacher_name": teacher2_doc["name"],
                    "student_name": "Rohan Verma",
                    "student_roll": "MA2026-001",
                    "subject": "MA201",
                    "date": today_iso,
                    "status": "Present",
                    "timestamp": datetime.now(timezone.utc)
                }
            ])

        # 12. Seed demo notices
        if notices.count_documents({}) == 0:
            notices.insert_many([
                {
                    "title": "Welcome to CAMPUSCORE Academic Suite 🎓",
                    "body": "Welcome to the updated academic platform with personalized attendance safety calculation, faculty assignment, and lecture notes management.",
                    "category": "General",
                    "author": "Academic Administrator",
                    "created": datetime.now(timezone.utc)
                },
                {
                    "title": "Faculty Department Allocation Completed",
                    "body": "All professors can now log into their faculty dashboard to select their assigned courses and mark classroom attendance.",
                    "category": "General",
                    "author": "Academic Administrator",
                    "created": datetime.now(timezone.utc) - timedelta(days=1)
                }
            ])

    except Exception as exc:
        print(f"Notice: Seed check deferred: {exc}", file=sys.stderr)


seed_demo_data()


# ---------------------------------------------------------------- Helper Functions
def oid(value):
    """Convert string to ObjectId safely or abort 404."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        abort(404)


def get_student_candidate_ids(student_id_or_doc):
    """Return all possible identifier strings for a student (user_id, student_id, roll_no, email)."""
    if not student_id_or_doc:
        return []
    ids = set()
    if isinstance(student_id_or_doc, dict):
        for k in ("_id", "user_id", "student_id", "roll_no", "email", "username"):
            v = student_id_or_doc.get(k)
            if v:
                ids.add(str(v).strip())
        val_str = str(student_id_or_doc.get("_id") or student_id_or_doc.get("user_id") or "").strip()
    else:
        val_str = str(student_id_or_doc).strip()
        ids.add(val_str)

    # Search in students collection
    if val_str:
        s_cond = [{"roll_no": val_str}, {"user_id": val_str}, {"email": val_str}]
        if ObjectId.is_valid(val_str):
            s_cond.append({"_id": ObjectId(val_str)})
        s = students.find_one({"$or": s_cond})
        if s:
            for k in ("_id", "user_id", "roll_no", "email"):
                if s.get(k):
                    ids.add(str(s[k]).strip())

        # Search in users collection
        u_cond = [{"username": val_str}, {"email": val_str}, {"roll_no": val_str}]
        if ObjectId.is_valid(val_str):
            u_cond.append({"_id": ObjectId(val_str)})
        u = users.find_one({"$or": u_cond, "role": "student"})
        if u:
            for k in ("_id", "roll_no", "email", "username"):
                if u.get(k):
                    ids.add(str(u[k]).strip())
    return list(ids)


def is_student_assigned_to_teacher(student_id_or_doc, teacher_id):
    """Check whether a student is assigned to a specific teacher using teacher_student_assignments collection or fallback."""
    if not student_id_or_doc or not teacher_id:
        return False
    t_id_str = str(teacher_id).strip()

    candidate_ids = get_student_candidate_ids(student_id_or_doc)
    if not candidate_ids:
        return False

    # 1. Primary check: teacher_student_assignments collection
    m2m = teacher_student_assignments.find_one({
        "teacher_id": t_id_str,
        "student_id": {"$in": candidate_ids},
        "status": {"$ne": "inactive"}
    })
    if m2m:
        return True

    # 2. Also check if roll_no matches
    m2m_roll = teacher_student_assignments.find_one({
        "teacher_id": t_id_str,
        "student_roll": {"$in": candidate_ids},
        "status": {"$ne": "inactive"}
    })
    if m2m_roll:
        return True

    # Check if student is actively managed in teacher_student_assignments
    has_m2m = teacher_student_assignments.count_documents({
        "$or": [
            {"student_id": {"$in": candidate_ids}},
            {"student_roll": {"$in": candidate_ids}}
        ]
    }) > 0
    if has_m2m:
        # If student has records in teacher_student_assignments, that is the single source of truth
        return False

    # 3. Fallback: Check legacy teacher_id on student/user doc for unmigrated data
    if isinstance(student_id_or_doc, dict):
        if str(student_id_or_doc.get("teacher_id", "")).strip() == t_id_str:
            return True
    val_str = str(candidate_ids[0]) if candidate_ids else ""
    s_cond = [{"roll_no": val_str}, {"user_id": val_str}]
    if ObjectId.is_valid(val_str):
        s_cond.append({"_id": ObjectId(val_str)})
    s = students.find_one({"$or": s_cond})
    if s and str(s.get("teacher_id", "")).strip() == t_id_str:
        return True
    u = users.find_one({"$or": s_cond, "role": "student"})
    if u and str(u.get("teacher_id", "")).strip() == t_id_str:
        return True

    return False


def get_student_teachers(student_id_or_doc):
    """Return list of all teachers assigned to a given student (many-to-many)."""
    candidate_ids = get_student_candidate_ids(student_id_or_doc)
    if not candidate_ids:
        return []

    # Find all active assignments for this student
    assigns = list(teacher_student_assignments.find({
        "$or": [
            {"student_id": {"$in": candidate_ids}},
            {"student_roll": {"$in": candidate_ids}}
        ],
        "status": {"$ne": "inactive"}
    }))

    t_ids = {a["teacher_id"] for a in assigns if a.get("teacher_id")}

    # Also check legacy teacher_id
    if isinstance(student_id_or_doc, dict) and student_id_or_doc.get("teacher_id"):
        t_ids.add(str(student_id_or_doc["teacher_id"]).strip())

    teacher_list = []
    for tid in t_ids:
        t_doc = users.find_one({"_id": oid(tid), "role": "teacher"})
        if t_doc:
            assigned_c = list(courses.find({
                "$or": [{"instructor_id": tid}, {"instructor": t_doc.get("name")}]
            }))
            teacher_list.append({
                "_id": str(t_doc["_id"]),
                "name": t_doc.get("name", "Faculty"),
                "email": t_doc.get("email", ""),
                "username": t_doc.get("username", ""),
                "department": t_doc.get("department", "Faculty"),
                "avatar_color": t_doc.get("avatar_color", "#38405f"),
                "courses": assigned_c,
                "courses_count": len(assigned_c)
            })

    return sorted(teacher_list, key=lambda x: x["name"])


def get_teacher_students(teacher_id):
    """Return all students assigned to a given teacher via teacher_student_assignments."""
    t_id_str = str(teacher_id).strip()

    # Query m2m assignments
    m2m_assigns = list(teacher_student_assignments.find({
        "teacher_id": t_id_str,
        "status": {"$ne": "inactive"}
    }))
    m2m_sids = {a.get("student_id") for a in m2m_assigns if a.get("student_id")}
    m2m_rolls = {a.get("student_roll") for a in m2m_assigns if a.get("student_roll")}

    st_list = []
    seen_rolls = set()

    # Match in students collection
    all_s = list(students.find().sort("roll_no", ASCENDING))
    for s in all_s:
        sid_str = str(s["_id"])
        user_id_str = str(s.get("user_id") or "")
        roll = s.get("roll_no")
        is_assigned = (sid_str in m2m_sids or user_id_str in m2m_sids or roll in m2m_rolls or str(s.get("teacher_id", "")).strip() == t_id_str)
        if is_assigned and roll not in seen_rolls:
            st_list.append(s)
            seen_rolls.add(roll)

    # Match in users collection
    u_list = list(users.find({"role": "student"}))
    for u in u_list:
        uid_str = str(u["_id"])
        roll = u.get("roll_no") or u.get("username", "").upper()
        is_assigned = (uid_str in m2m_sids or roll in m2m_rolls or str(u.get("teacher_id", "")).strip() == t_id_str)
        if is_assigned and roll not in seen_rolls:
            st_list.append({
                "_id": u["_id"],
                "roll_no": roll,
                "name": u.get("name"),
                "email": u.get("email"),
                "department": u.get("department") or u.get("program", "General"),
                "year": 2,
                "teacher_id": t_id_str,
                "teacher_name": u.get("teacher_name", ""),
                "user_id": str(u["_id"])
            })
            seen_rolls.add(roll)

    for s in st_list:
        uid = s.get("user_id") or str(s["_id"])
        metrics = calculate_attendance_metrics(uid)
        s["attendance_pct"] = metrics["percentage"]
        s["total_attendance_days"] = metrics["total_days"]
        s["submissions_count"] = submissions.count_documents({"$or": [{"student_id": uid}, {"student_roll": s.get("roll_no")}]})
    return st_list


def get_all_students_with_details():
    """Return all platform students with assigned teachers (plural), attendance %, and submissions count."""
    all_st = list(students.find().sort("roll_no", ASCENDING))
    seen_rolls = {s.get("roll_no") for s in all_st if s.get("roll_no")}
    u_list = list(users.find({"role": "student"}))
    for u in u_list:
        roll = u.get("roll_no") or u.get("username", "").upper()
        if roll not in seen_rolls:
            all_st.append({
                "_id": u["_id"],
                "roll_no": roll,
                "name": u.get("name"),
                "email": u.get("email"),
                "department": u.get("department") or u.get("program", "General"),
                "year": 2,
                "teacher_id": u.get("teacher_id", ""),
                "teacher_name": u.get("teacher_name", "Unassigned"),
                "user_id": str(u["_id"])
            })
            seen_rolls.add(roll)

    for s in all_st:
        uid = s.get("user_id") or str(s["_id"])
        metrics = calculate_attendance_metrics(uid)
        s["attendance_pct"] = metrics["percentage"]
        s["total_attendance_days"] = metrics["total_days"]
        s["submissions_count"] = submissions.count_documents({"$or": [{"student_id": uid}, {"student_roll": s.get("roll_no")}]})
        assigned_teachers = get_student_teachers(s)
        s["assigned_teachers"] = assigned_teachers
        s["teachers_count"] = len(assigned_teachers)
        s["teacher_names"] = ", ".join(t["name"] for t in assigned_teachers) if assigned_teachers else "Unassigned"
    return all_st


def get_student_record(sid):
    """Find student record by id, roll_no, or user_id."""
    if not sid:
        return None
    val_str = str(sid).strip()
    s_conditions = [{"roll_no": val_str}, {"user_id": val_str}]
    if ObjectId.is_valid(val_str):
        s_conditions.append({"_id": ObjectId(val_str)})
    s = students.find_one({"$or": s_conditions})
    if s:
        return s
    u_conditions = [{"username": val_str}, {"roll_no": val_str}]
    if ObjectId.is_valid(val_str):
        u_conditions.append({"_id": ObjectId(val_str)})
        u_conditions.append({"student_id": ObjectId(val_str)})
    u = users.find_one({"$or": u_conditions, "role": "student"})
    if u:
        return {
            "_id": u["_id"],
            "roll_no": u.get("roll_no") or u.get("username", "").upper(),
            "name": u.get("name"),
            "email": u.get("email"),
            "department": u.get("department") or u.get("program", "General"),
            "year": 2,
            "teacher_id": u.get("teacher_id", ""),
            "teacher_name": u.get("teacher_name", "Unassigned"),
            "user_id": str(u["_id"])
        }
    return None


def serialize_doc(doc):
    """Serialize MongoDB document containing ObjectId and datetime."""
    if not doc:
        return None
    res = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            res[k] = str(v)
        elif isinstance(v, (datetime, date)):
            res[k] = v.isoformat()
        elif isinstance(v, dict):
            res[k] = serialize_doc(v)
        elif isinstance(v, list):
            res[k] = [serialize_doc(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
        else:
            res[k] = v
    if "_id" in res and "id" not in res:
        res["id"] = res["_id"]
    return res


def login_required(view):
    """Ensure user is authenticated."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized. Please login."}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Restrict endpoint to specific roles."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if session["user"].get("role") not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Forbidden: insufficient permissions"}), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_current_user():
    """Fetch current user record from database."""
    if "user" not in session:
        return None
    uid = session["user"].get("id")
    if not uid:
        return None
    u = users.find_one({"_id": oid(uid)})
    return serialize_doc(u) if u else session["user"]


@app.context_processor
def inject_globals():
    """Inject template helper variables."""
    user = get_current_user()
    return {
        "me": user,
        "current_user": user,
        "statuses": STATUSES,
        "priorities": PRIORITIES,
        "task_statuses": TASK_STATUSES,
        "levels": LEVELS,
        "boards": BOARDS,
        "today_str": date.today().isoformat()
    }


@app.errorhandler(403)
def forbidden_handler(_):
    return render_template("error.html", code=403, msg="You do not have permission to access this resource."), 403


@app.errorhandler(404)
def not_found_handler(_):
    return render_template("error.html", code=404, msg="The requested page could not be found."), 404


@app.errorhandler(500)
def server_error_handler(err):
    return render_template("error.html", code=500, msg="An internal server error occurred. Please try again."), 500


# ---------------------------------------------------------------- Metric Calculations
def calculate_attendance_metrics(user_id, month=None, year=None, subject=None):
    """Calculate attendance stats, streak, and 75% Bunk/Safety calculations."""
    if not user_id:
        return {
            "total_days": 0, "present": 0, "absent": 0, "half_day": 0,
            "percentage": 0.0, "streak": 0, "can_bunk": 0, "need_to_attend": 0,
            "is_safe": True, "records": []
        }

    uid_str = str(user_id.get("id") or user_id.get("_id")) if isinstance(user_id, dict) else str(user_id)
    roll = None
    if isinstance(user_id, dict):
        roll = user_id.get("roll_no")
    else:
        if ObjectId.is_valid(uid_str):
            u = users.find_one({"_id": ObjectId(uid_str)})
            if u:
                roll = u.get("roll_no")
            else:
                s = students.find_one({"_id": ObjectId(uid_str)})
                if s:
                    roll = s.get("roll_no")

    or_conds = [{"user_id": uid_str}, {"student_id": uid_str}]
    if roll:
        or_conds.append({"student_roll": roll})

    query = {"$or": or_conds}
    if subject:
        query["subject"] = subject

    records = list(attendance.find(query).sort("date", DESCENDING))

    filtered = []
    for r in records:
        try:
            rd = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if year and rd.year != int(year):
                continue
            if month and rd.month != int(month):
                continue
            filtered.append(r)
        except Exception:
            filtered.append(r)

    total_days = len(filtered)
    present_count = sum(1 for r in filtered if r.get("status") in ("Present", "present"))
    absent_count = sum(1 for r in filtered if r.get("status") in ("Absent", "absent"))
    half_day_count = sum(1 for r in filtered if r.get("status") in ("Half Day", "half_day", "Late", "late"))

    effective_present = present_count + (0.5 * half_day_count)
    percentage = round((effective_present / total_days) * 100, 1) if total_days > 0 else 0.0

    streak = 0
    date_records = {}
    for r in sorted(records, key=lambda x: x.get("date", ""), reverse=True):
        d_str = r.get("date")
        if d_str not in date_records:
            date_records[d_str] = r.get("status")

    today = date.today()
    check_date = today
    if today.isoformat() not in date_records:
        check_date = today - timedelta(days=1)

    while check_date.isoformat() in date_records:
        st = date_records[check_date.isoformat()]
        if st in ("Present", "present"):
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    can_bunk = 0
    need_to_attend = 0
    is_safe = percentage >= 75.0 if total_days > 0 else True

    if total_days > 0:
        if percentage >= 75.0:
            can_bunk = max(0, math.floor((4 * effective_present - 3 * total_days) / 3))
        else:
            need_to_attend = max(0, math.ceil(3 * total_days - 4 * effective_present))

    return {
        "total_days": total_days,
        "present": present_count,
        "absent": absent_count,
        "half_day": half_day_count,
        "percentage": percentage,
        "streak": streak,
        "can_bunk": can_bunk,
        "need_to_attend": need_to_attend,
        "is_safe": is_safe,
        "records": filtered
    }


def calculate_task_metrics(user_id):
    """Calculate task completion percentage and priority breakdown."""
    all_tasks = list(tasks.find({"user_id": str(user_id)}))
    total = len(all_tasks)
    pending = sum(1 for t in all_tasks if t.get("status") == "pending")
    in_progress = sum(1 for t in all_tasks if t.get("status") == "in_progress")
    completed = sum(1 for t in all_tasks if t.get("status") == "completed")
    high_priority = sum(1 for t in all_tasks if t.get("priority") == "high" and t.get("status") != "completed")

    completion_pct = round((completed / total) * 100) if total > 0 else 0

    return {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "high_priority": high_priority,
        "completion_pct": completion_pct
    }


# ---------------------------------------------------------------- Auth & Landing
@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/landing")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        user = users.find_one({
            "$or": [{"username": identifier}, {"email": identifier}]
        })

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user"] = {
                "id": str(user["_id"]),
                "name": user.get("name", "User"),
                "username": user.get("username"),
                "email": user.get("email"),
                "role": user.get("role", "student"),
                "department": user.get("department", ""),
                "level": user.get("level", "college"),
                "program": user.get("program", ""),
                "board": user.get("board", "CBSE"),
                "avatar_color": user.get("avatar_color", "#ff0035"),
                "student_id": str(user.get("student_id", "")) if user.get("student_id") else None
            }
            flash(f"Welcome back, {user.get('name')}! 👋", "ok")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))

        flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        email = f.get("email", "").strip().lower()
        username = f.get("username", "").strip().lower()
        password = f.get("password", "")
        level = f.get("level", "college")
        program = f.get("program", "").strip()
        board = f.get("board", "CBSE")

        if not username and email:
            username = email.split("@")[0]

        if not (name and email and password and username):
            flash("All fields are required.", "error")
            return render_template("signup.html", form=f)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html", form=f)

        if users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash("A user with that username or email already exists.", "error")
            return render_template("signup.html", form=f)

        colors = ["#ff0035", "#38405f", "#59546c", "#8b939c", "#d6002c"]
        avatar_color = colors[len(username) % len(colors)]

        try:
            res = users.insert_one({
                "username": username,
                "email": email,
                "name": name,
                "password": generate_password_hash(password),
                "role": "student",
                "level": level,
                "program": program,
                "class_name": f.get("class_name", ""),
                "board": board,
                "avatar_color": avatar_color,
                "created_at": datetime.now(timezone.utc)
            })

            new_uid = str(res.inserted_id)

            # Auto-seed default curriculum subjects for the student
            default_subs = [
                {"name": "Mathematics", "icon": "📐"},
                {"name": "Science", "icon": "🧪"},
                {"name": "Computer Science", "icon": "💻"},
                {"name": "English", "icon": "📚"},
                {"name": "Social Science", "icon": "🌍"}
            ]
            for s in default_subs:
                subjects.insert_one({
                    "user_id": new_uid,
                    "name": s["name"],
                    "icon": s["icon"],
                    "created_at": datetime.now(timezone.utc)
                })

            session.clear()
            session["user"] = {
                "id": new_uid,
                "name": name,
                "username": username,
                "email": email,
                "role": "student",
                "level": level,
                "program": program,
                "board": board,
                "avatar_color": avatar_color
            }
            flash("Registration successful! Welcome to CAMPUSCORE 🎓", "ok")
            return redirect(url_for("dashboard"))
        except DuplicateKeyError:
            flash("Username or email already registered.", "error")

    return render_template("signup.html", form={})


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out successfully.", "ok")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    uid = user["id"]

    if request.method == "POST":
        action = request.form.get("action", "update_info")
        if action == "update_info":
            name = request.form.get("name", "").strip()
            program = request.form.get("program", "").strip()
            class_name = request.form.get("class_name", "").strip()
            board = request.form.get("board", "CBSE")
            avatar_color = request.form.get("avatar_color", user.get("avatar_color", "#ff0035"))

            if name:
                users.update_one(
                    {"_id": oid(uid)},
                    {"$set": {
                        "name": name, "program": program,
                        "class_name": class_name, "board": board,
                        "avatar_color": avatar_color
                    }}
                )
                session["user"]["name"] = name
                session["user"]["program"] = program
                session["user"]["board"] = board
                session["user"]["avatar_color"] = avatar_color
                flash("Profile details updated successfully! 🎉", "ok")
        elif action == "change_password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            u_doc = users.find_one({"_id": oid(uid)})
            if u_doc and check_password_hash(u_doc["password"], current_pw):
                if len(new_pw) >= 6:
                    users.update_one({"_id": oid(uid)}, {"$set": {"password": generate_password_hash(new_pw)}})
                    flash("Password changed successfully.", "ok")
                else:
                    flash("New password must be at least 6 characters.", "error")
            else:
                flash("Incorrect current password.", "error")

        return redirect(url_for("profile"))

    att_stats = calculate_attendance_metrics(uid)
    task_stats = calculate_task_metrics(uid)
    user_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))
    user_notes_count = notes.count_documents({"user_id": uid})

    # For teacher: get assigned courses
    teacher_courses = []
    if user.get("role") == "teacher":
        teacher_courses = list(courses.find({
            "$or": [{"instructor_id": uid}, {"instructor": user.get("name")}]
        }))

    return render_template("profile.html",
                           user=user,
                           att_stats=att_stats,
                           task_stats=task_stats,
                           user_subjects=user_subjects,
                           notes_count=user_notes_count,
                           teacher_courses=teacher_courses)


# ---------------------------------------------------------------- Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    uid = user["id"]
    role = user.get("role", "student")

    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good Morning"
    elif hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    tips = [
        "Maintain your attendance above 75% to stay worry-free during exam admit card distribution.",
        "Break large assignments down into high and medium priority subtasks.",
        "Daily attendance streaks build consistency. Aim for a 7-day streak! 🔥",
        "Keep your study notes organized with clear headings and tags for quick exam revision.",
        "Check notices regularly for examination schedules and department updates."
    ]
    tip_index = (datetime.now().day + hour) % len(tips)
    current_tip = tips[tip_index]

    att_stats = calculate_attendance_metrics(uid)
    task_stats = calculate_task_metrics(uid)

    recent_tasks = list(tasks.find({
        "user_id": uid,
        "status": {"$ne": "completed"}
    }).sort([("priority", ASCENDING), ("due_date", ASCENDING)]).limit(5))

    recent_notes = list(notes.find({"user_id": uid}).sort("updated_at", DESCENDING).limit(4))
    my_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))
    recent_notices = list(notices.find().sort("created", DESCENDING).limit(4))

    # Role specific data
    student_assignments = []
    student_submissions = []
    my_teachers = []
    teacher_students = []
    teacher_assignments = []
    teacher_pending_submissions = []
    teacher_courses = []
    admin_stats = {}
    all_teachers_overview = []
    recent_attendance_records = []

    if role == "student":
        my_teachers = get_student_teachers(user)
        teacher_ids = [t["_id"] for t in my_teachers]
        if teacher_ids:
            a_query = {"teacher_id": {"$in": teacher_ids}}
        else:
            t_id = user.get("teacher_id")
            a_query = {"teacher_id": t_id} if t_id else {}
        student_assignments = list(assignments.find(a_query).sort("due_date", ASCENDING).limit(6))
        st_subs = list(submissions.find({"$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]}))
        sub_map = {s.get("assignment_id"): s for s in st_subs}
        for a in student_assignments:
            aid_str = str(a["_id"])
            if aid_str in sub_map:
                a["submission"] = sub_map[aid_str]
                a["status_label"] = "Graded" if sub_map[aid_str].get("status") == "graded" else "Submitted"
            else:
                a["submission"] = None
                a["status_label"] = "Pending Submission"
        student_submissions = st_subs

    elif role == "teacher":
        teacher_students = get_teacher_students(uid)
        teacher_assignments = list(assignments.find({"teacher_id": uid}).sort("created_at", DESCENDING))
        for a in teacher_assignments:
            aid_str = str(a["_id"])
            a["submissions_count"] = submissions.count_documents({"assignment_id": aid_str})
            a["graded_count"] = submissions.count_documents({"assignment_id": aid_str, "status": "graded"})
        teacher_pending_submissions = list(submissions.find({"teacher_id": uid, "status": "submitted"}).sort("submitted_at", DESCENDING).limit(5))
        teacher_courses = list(courses.find({
            "$or": [{"instructor_id": uid}, {"instructor": user.get("name")}]
        }))

    elif role == "admin":
        total_students = len(get_all_students_with_details())
        total_teachers = users.count_documents({"role": "teacher"})
        total_courses = courses.count_documents({})
        total_assignments = assignments.count_documents({})
        total_submissions = submissions.count_documents({})
        total_attendance = attendance.count_documents({})
        present_attendance = attendance.count_documents({"status": {"$in": ["Present", "present"]}})
        att_rate = round((present_attendance / total_attendance * 100), 1) if total_attendance > 0 else 0.0

        admin_stats = {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_courses": total_courses,
            "total_assignments": total_assignments,
            "total_submissions": total_submissions,
            "total_attendance": total_attendance,
            "attendance_rate": att_rate
        }

        all_teachers = list(users.find({"role": "teacher"}).sort("name", ASCENDING))
        for t in all_teachers:
            tid_str = str(t["_id"])
            t["students_count"] = len(get_teacher_students(tid_str))
            t["courses_count"] = courses.count_documents({"$or": [{"instructor_id": tid_str}, {"instructor": t.get("name")}]})
            t["assignments_count"] = assignments.count_documents({"teacher_id": tid_str})
        all_teachers_overview = all_teachers
        recent_attendance_records = list(attendance.find().sort("timestamp", DESCENDING).limit(8))

    return render_template("dashboard.html",
                           greeting=greeting,
                           current_tip=current_tip,
                           att_stats=att_stats,
                           task_stats=task_stats,
                           recent_tasks=recent_tasks,
                           recent_notes=recent_notes,
                           my_subjects=my_subjects,
                           recent_notices=recent_notices,
                           my_teachers=my_teachers,
                           student_assignments=student_assignments,
                           student_submissions=student_submissions,
                           teacher_students=teacher_students,
                           teacher_assignments=teacher_assignments,
                           teacher_pending_submissions=teacher_pending_submissions,
                           teacher_courses=teacher_courses,
                           admin_stats=admin_stats,
                           all_teachers_overview=all_teachers_overview,
                           recent_attendance_records=recent_attendance_records)


# ---------------------------------------------------------------- Faculty & Teacher Management (Admin Only)
@app.route("/teachers", methods=["GET"])
@role_required("admin")
def teachers_list():
    """Admin page to check all teachers and assign them courses/subjects."""
    all_teachers = list(users.find({"role": "teacher"}).sort("name", ASCENDING))
    all_courses = list(courses.find().sort("code", ASCENDING))

    # Attach assigned courses detail and student count to each teacher
    for t in all_teachers:
        t_id_str = str(t["_id"])
        t_assigned_ids = t.get("assigned_courses", [])
        # Find courses where instructor_id matches or instructor matches name
        assigned = list(courses.find({
            "$or": [
                {"_id": {"$in": [oid(cid) for cid in t_assigned_ids if ObjectId.is_valid(cid)]}},
                {"instructor_id": t_id_str},
                {"instructor": t.get("name")}
            ]
        }))
        t["courses_list"] = assigned
        t["courses_count"] = len(assigned)
        t["students_count"] = len(get_teacher_students(t_id_str))

    return render_template("teachers.html",
                           teachers=all_teachers,
                           all_courses=all_courses)


@app.route("/teachers/<tid>", methods=["GET"])
@role_required("admin")
def teacher_detail(tid):
    """Admin dedicated view of a specific teacher with their complete list of assigned students."""
    teacher = users.find_one({"_id": oid(tid), "role": "teacher"})
    if not teacher:
        abort(404)
    t_id_str = str(teacher["_id"])
    assigned_students = get_teacher_students(t_id_str)
    assigned_courses = list(courses.find({
        "$or": [{"instructor_id": t_id_str}, {"instructor": teacher.get("name")}]
    }))
    teacher_assignments = list(assignments.find({"teacher_id": t_id_str}))

    # Available students: all platform students who are NOT assigned to THIS teacher!
    # A student assigned to another teacher MUST still appear as available because multiple teachers are allowed!
    all_students = get_all_students_with_details()
    assigned_identifiers = set()
    for s in assigned_students:
        for k in ("_id", "user_id", "roll_no", "email"):
            if s.get(k):
                assigned_identifiers.add(str(s[k]).strip())

    available_students = [
        s for s in all_students
        if str(s.get("_id")).strip() not in assigned_identifiers
        and str(s.get("user_id") or "").strip() not in assigned_identifiers
        and str(s.get("roll_no") or "").strip() not in assigned_identifiers
    ]

    other_teachers = list(users.find({"role": "teacher", "_id": {"$ne": teacher["_id"]}}).sort("name", ASCENDING))

    return render_template("teacher_detail.html",
                           teacher=teacher,
                           students=assigned_students,
                           courses=assigned_courses,
                           assignments=teacher_assignments,
                           available_students=available_students,
                           other_teachers=other_teachers)


@app.route("/teachers/add", methods=["POST"])
@role_required("admin")
def teachers_add():
    """Admin registers a new teacher and assigns initial courses."""
    f = request.form
    name = f.get("name", "").strip()
    email = f.get("email", "").strip().lower()
    username = f.get("username", "").strip().lower()
    password = f.get("password", "")
    department = f.get("department", "").strip()
    selected_course_ids = f.getlist("course_ids")

    if not username and email:
        username = email.split("@")[0]

    if not (name and email and password and username):
        flash("Name, email, username, and password are required.", "error")
        return redirect(url_for("teachers_list"))

    if users.find_one({"$or": [{"username": username}, {"email": email}]}):
        flash("A user with that username or email already exists.", "error")
        return redirect(url_for("teachers_list"))

    try:
        new_teacher = users.insert_one({
            "name": name,
            "email": email,
            "username": username,
            "password": generate_password_hash(password),
            "role": "teacher",
            "department": department,
            "level": "college",
            "program": f"Faculty of {department}" if department else "Faculty",
            "board": "University",
            "avatar_color": "#38405f",
            "assigned_courses": selected_course_ids,
            "created_at": datetime.now(timezone.utc)
        })
        t_id = str(new_teacher.inserted_id)

        # Update selected courses with instructor
        for cid in selected_course_ids:
            courses.update_one({"_id": oid(cid)}, {"$set": {"instructor_id": t_id, "instructor": name}})

        flash(f"Faculty member {name} registered and assigned {len(selected_course_ids)} course(s)! 👨‍🏫", "ok")
    except DuplicateKeyError:
        flash("Username or email already exists.", "error")

    return redirect(url_for("teachers_list"))


@app.route("/teachers/assign", methods=["POST"])
@role_required("admin")
def teachers_assign():
    """Admin updates the courses/subjects assigned to a teacher."""
    teacher_id = request.form.get("teacher_id", "").strip()
    selected_course_ids = request.form.getlist("course_ids")

    teacher = users.find_one({"_id": oid(teacher_id), "role": "teacher"})
    if not teacher:
        flash("Teacher not found.", "error")
        return redirect(url_for("teachers_list"))

    # Update teacher document with new assigned courses
    users.update_one(
        {"_id": teacher["_id"]},
        {"$set": {"assigned_courses": selected_course_ids}}
    )

    # 1. Update all selected courses to be taught by this teacher
    for cid in selected_course_ids:
        courses.update_one(
            {"_id": oid(cid)},
            {"$set": {"instructor_id": teacher_id, "instructor": teacher["name"]}}
        )

    # 2. For courses previously assigned to this teacher that were unselected: unassign them
    courses.update_many(
        {"instructor_id": teacher_id, "_id": {"$nin": [oid(c) for c in selected_course_ids if ObjectId.is_valid(c)]}},
        {"$set": {"instructor_id": "", "instructor": "Unassigned"}}
    )

    flash(f"Updated subject/course assignments for {teacher['name']}. ({len(selected_course_ids)} courses assigned)", "ok")
    return redirect(url_for("teachers_list"))


@app.route("/teachers/delete/<tid>", methods=["POST"])
@role_required("admin")
def teachers_delete(tid):
    """Admin removes a teacher."""
    _id = oid(tid)
    teacher = users.find_one({"_id": _id, "role": "teacher"})
    if teacher:
        courses.update_many({"instructor_id": str(_id)}, {"$set": {"instructor_id": "", "instructor": "Unassigned"}})
        teacher_student_assignments.delete_many({"teacher_id": str(_id)})
        users.delete_one({"_id": _id})
        flash(f"Teacher {teacher['name']} removed and courses unassigned.", "ok")
    return redirect(url_for("teachers_list"))


@app.route("/teachers/<tid>/assign-students", methods=["POST"])
@role_required("admin")
def teacher_assign_students(tid):
    """Admin assigns one or multiple students to a teacher (Many-to-Many)."""
    teacher = users.find_one({"_id": oid(tid), "role": "teacher"})
    if not teacher:
        abort(404)
    sids = request.form.getlist("student_ids")
    if not sids and request.form.get("student_id"):
        sids = [request.form.get("student_id")]

    count = 0
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for sid in sids:
        sid = str(sid).strip()
        if not sid:
            continue
        st_doc = get_student_record(sid)
        st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else sid
        st_name = st_doc.get("name", "Student") if st_doc else "Student"
        st_roll = st_doc.get("roll_no", "") if st_doc else ""

        try:
            teacher_student_assignments.update_one(
                {"teacher_id": str(tid), "student_id": str(st_user_id)},
                {"$set": {
                    "teacher_id": str(tid),
                    "student_id": str(st_user_id),
                    "student_roll": st_roll,
                    "student_name": st_name,
                    "teacher_name": teacher["name"],
                    "assigned_at": now_str,
                    "status": "active"
                }},
                upsert=True
            )
            count += 1
        except Exception:
            pass

    flash(f"Assigned {count} student(s) to faculty member {teacher['name']}. ✅", "ok")
    return redirect(url_for("teacher_detail", tid=tid))


@app.route("/teachers/<tid>/remove-student", methods=["POST"])
@role_required("admin")
def teacher_remove_student(tid):
    """Admin removes a student from a teacher's assigned list."""
    teacher = users.find_one({"_id": oid(tid), "role": "teacher"})
    if not teacher:
        abort(404)
    sid = request.form.get("student_id", "").strip()
    st_doc = get_student_record(sid)
    st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else sid
    candidate_ids = [str(st_user_id), sid]
    if st_doc and st_doc.get("roll_no"):
        candidate_ids.append(st_doc["roll_no"])

    teacher_student_assignments.delete_many({
        "teacher_id": str(tid),
        "$or": [
            {"student_id": {"$in": candidate_ids}},
            {"student_roll": {"$in": candidate_ids}}
        ]
    })
    try:
        students.update_many({"teacher_id": str(tid), "$or": [{"user_id": {"$in": candidate_ids}}, {"roll_no": {"$in": candidate_ids}}]}, {"$set": {"teacher_id": "", "teacher_name": "Unassigned"}})
        users.update_many({"teacher_id": str(tid), "$or": [{"_id": {"$in": [oid(x) for x in candidate_ids if ObjectId.is_valid(x)]}}, {"roll_no": {"$in": candidate_ids}}]}, {"$set": {"teacher_id": "", "teacher_name": "Unassigned"}})
    except Exception:
        pass
    flash(f"Student removed from {teacher['name']}'s assigned list. 🗑️", "ok")
    return redirect(url_for("teacher_detail", tid=tid))


@app.route("/teachers/<tid>/transfer-student", methods=["POST"])
@role_required("admin")
def teacher_transfer_student(tid):
    """Admin transfers a student from one teacher to another."""
    teacher = users.find_one({"_id": oid(tid), "role": "teacher"})
    target_tid = request.form.get("target_teacher_id", "").strip()
    target_teacher = users.find_one({"_id": oid(target_tid), "role": "teacher"})
    if not teacher or not target_teacher:
        flash("Invalid faculty member specified for transfer.", "error")
        return redirect(url_for("teacher_detail", tid=tid))

    sid = request.form.get("student_id", "").strip()
    st_doc = get_student_record(sid)
    st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else sid
    st_name = st_doc.get("name", "Student") if st_doc else "Student"
    st_roll = st_doc.get("roll_no", "") if st_doc else ""
    candidate_ids = [str(st_user_id), sid]
    if st_doc and st_doc.get("roll_no"):
        candidate_ids.append(st_doc["roll_no"])

    # 1. Remove from source teacher
    teacher_student_assignments.delete_many({
        "teacher_id": str(tid),
        "$or": [
            {"student_id": {"$in": candidate_ids}},
            {"student_roll": {"$in": candidate_ids}}
        ]
    })
    try:
        students.update_many({"teacher_id": str(tid), "$or": [{"user_id": {"$in": candidate_ids}}, {"roll_no": {"$in": candidate_ids}}]}, {"$set": {"teacher_id": str(target_tid), "teacher_name": target_teacher["name"]}})
        users.update_many({"teacher_id": str(tid), "$or": [{"_id": {"$in": [oid(x) for x in candidate_ids if ObjectId.is_valid(x)]}}, {"roll_no": {"$in": candidate_ids}}]}, {"$set": {"teacher_id": str(target_tid), "teacher_name": target_teacher["name"]}})
    except Exception:
        pass

    # 2. Add to target teacher
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    teacher_student_assignments.update_one(
        {"teacher_id": str(target_tid), "student_id": str(st_user_id)},
        {"$set": {
            "teacher_id": str(target_tid),
            "student_id": str(st_user_id),
            "student_roll": st_roll,
            "student_name": st_name,
            "teacher_name": target_teacher["name"],
            "assigned_at": now_str,
            "status": "active"
        }},
        upsert=True
    )
    flash(f"Student {st_name} successfully transferred from {teacher['name']} to {target_teacher['name']}. 🔄", "ok")
    return redirect(url_for("teacher_detail", tid=tid))


# ---------------------------------------------------------------- Attendance
@app.route("/attendance", methods=["GET"])
@login_required
def attendance_view():
    user = get_current_user()
    uid = user["id"]
    role = user.get("role", "student")

    # ADMIN: Strictly Read-Only attendance overview & reports
    if role == "admin":
        teacher_flt = request.args.get("teacher_id", "").strip()
        student_flt = request.args.get("student_id", "").strip()
        status_flt = request.args.get("status", "").strip()
        date_flt = request.args.get("date", "").strip()

        query = {}
        if teacher_flt:
            query["teacher_id"] = teacher_flt
        if student_flt:
            query["$or"] = [{"student_id": student_flt}, {"user_id": student_flt}, {"student_roll": student_flt}]
        if status_flt:
            query["status"] = status_flt
        if date_flt:
            query["date"] = date_flt

        records = list(attendance.find(query).sort("date", DESCENDING))
        total_records = len(records)
        present_count = sum(1 for r in records if r.get("status") in ("Present", "present"))
        absent_count = sum(1 for r in records if r.get("status") in ("Absent", "absent"))
        pct = round((present_count / total_records * 100), 1) if total_records > 0 else 0.0

        all_teachers = list(users.find({"role": "teacher"}).sort("name", ASCENDING))
        all_students = get_all_students_with_details()

        return render_template("attendance.html",
                               admin_mode=True,
                               teacher_mode=False,
                               student_mode=False,
                               records=records,
                               total_records=total_records,
                               present_count=present_count,
                               absent_count=absent_count,
                               attendance_pct=pct,
                               all_teachers=all_teachers,
                               all_students=all_students,
                               selected_teacher=teacher_flt,
                               selected_student=student_flt,
                               selected_status=status_flt,
                               selected_date=date_flt)

    # TEACHER: Attendance management and roster marking for assigned students
    elif role == "teacher":
        teacher_courses = list(courses.find({
            "$or": [{"instructor_id": uid}, {"instructor": user.get("name")}]
        }).sort("code", ASCENDING))

        cid = request.args.get("course", "")
        day = request.args.get("date", date.today().isoformat())

        if not cid and len(teacher_courses) > 0:
            cid = str(teacher_courses[0]["_id"])

        selected_course = courses.find_one({"_id": oid(cid)}) if cid else None
        assigned_students = get_teacher_students(uid)

        existing_records = {r.get("student_id") or r.get("user_id"): r.get("status") 
                            for r in attendance.find({"teacher_id": uid, "date": day})}

        teacher_att_history = list(attendance.find({"teacher_id": uid}).sort("date", DESCENDING).limit(50))

        return render_template("attendance.html",
                               admin_mode=False,
                               teacher_mode=True,
                               student_mode=False,
                               courses=teacher_courses,
                               selected_course=selected_course,
                               cid=cid,
                               day=day,
                               students=assigned_students,
                               existing=existing_records,
                               history=teacher_att_history)

    # STUDENT: Personal attendance & 75% Bunk Planner
    else:
        now = datetime.now()
        month = request.args.get("month", str(now.month))
        year = request.args.get("year", str(now.year))
        sub_filter = request.args.get("subject", "")

        user_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))
        metrics = calculate_attendance_metrics(uid, month=month, year=year, subject=sub_filter)

        subject_breakdowns = []
        for s in user_subjects:
            smetrics = calculate_attendance_metrics(uid, month=None, year=None, subject=s["name"])
            subject_breakdowns.append({
                "name": s["name"],
                "icon": s.get("icon", "📘"),
                "stats": smetrics
            })

        return render_template("attendance.html",
                               admin_mode=False,
                               teacher_mode=False,
                               student_mode=True,
                               month=int(month),
                               year=int(year),
                               sub_filter=sub_filter,
                               user_subjects=user_subjects,
                               metrics=metrics,
                               subject_breakdowns=subject_breakdowns)


@app.route("/attendance/mark", methods=["POST"])
@login_required
def attendance_mark():
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    # RBAC Enforcement: Admin CANNOT mark attendance (403 Forbidden)
    if role == "admin":
        abort(403)

    # RBAC Enforcement: Student CANNOT mark attendance (403 Forbidden)
    if role == "student":
        abort(403)

    # Only Teacher can mark attendance, and ONLY for assigned students
    f = request.form
    date_str = f.get("date", date.today().isoformat()).strip()
    subject_val = f.get("subject", "").strip()

    # Case A: Bulk roster save
    if f.get("save_roster"):
        assigned = get_teacher_students(uid)
        count = 0
        for s in assigned:
            sid_str = str(s["_id"])
            st_user_id = s.get("user_id") or sid_str
            status_val = f.get(f"s_{sid_str}", "Present").strip()
            if status_val in STATUSES:
                attendance.update_one(
                    {"teacher_id": uid, "student_id": st_user_id, "date": date_str},
                    {"$set": {
                        "student_id": st_user_id,
                        "user_id": st_user_id,
                        "student_name": s["name"],
                        "student_roll": s["roll_no"],
                        "teacher_id": uid,
                        "teacher_name": user["name"],
                        "subject": subject_val or "General",
                        "status": status_val,
                        "date": date_str,
                        "timestamp": datetime.now(timezone.utc)
                    }},
                    upsert=True
                )
                count += 1
        flash(f"Class attendance saved for {count} assigned students on {date_str}. ✅", "ok")
        return redirect(url_for("attendance_view", date=date_str))

    # Case B: Individual student mark
    target_student_id = f.get("student_id", "").strip()
    status_val = f.get("status", "Present").strip()
    notes_val = f.get("notes", "").strip()

    if not target_student_id:
        flash("Student ID is required.", "error")
        return redirect(url_for("attendance_view"))

    # RBAC check: Student must be assigned to this teacher!
    if not is_student_assigned_to_teacher(target_student_id, uid):
        abort(403)

    st_doc = get_student_record(target_student_id)
    st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else target_student_id
    st_name = st_doc.get("name", "Student") if st_doc else "Student"
    st_roll = st_doc.get("roll_no", "") if st_doc else ""

    attendance.update_one(
        {"teacher_id": uid, "student_id": st_user_id, "date": date_str},
        {"$set": {
            "student_id": st_user_id,
            "user_id": st_user_id,
            "student_name": st_name,
            "student_roll": st_roll,
            "teacher_id": uid,
            "teacher_name": user["name"],
            "subject": subject_val or "General",
            "status": status_val,
            "notes": notes_val,
            "date": date_str,
            "timestamp": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    flash(f"Attendance recorded for {st_name} ({status_val}). ✅", "ok")
    return redirect(request.referrer or url_for("attendance_view"))


@app.route("/attendance/delete/<aid>", methods=["POST"])
@login_required
def attendance_delete(aid):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    # RBAC Enforcement: Admin CANNOT delete attendance records (403 Forbidden)
    if role == "admin":
        abort(403)

    # RBAC Enforcement: Student CANNOT delete attendance records (403 Forbidden)
    if role == "student":
        abort(403)

    # Teacher can delete records for their assigned students
    rec = attendance.find_one({"_id": oid(aid)})
    if not rec:
        abort(404)

    if rec.get("teacher_id") != uid and not is_student_assigned_to_teacher(rec.get("student_id") or rec.get("user_id"), uid):
        abort(403)

    attendance.delete_one({"_id": rec["_id"]})
    flash("Attendance record removed.", "ok")
    return redirect(request.referrer or url_for("attendance_view"))


# ---------------------------------------------------------------- Tasks (Faculty & Admin Only)
@app.route("/tasks", methods=["GET"])
@role_required("teacher", "admin")
def tasks_view():
    user = get_current_user()
    uid = user["id"]

    status_filter = request.args.get("status", "all")
    subject_filter = request.args.get("subject", "")
    priority_filter = request.args.get("priority", "")

    query = {"user_id": uid}
    if status_filter in TASK_STATUSES:
        query["status"] = status_filter
    if subject_filter:
        query["subject"] = subject_filter
    if priority_filter in PRIORITIES:
        query["priority"] = priority_filter

    user_tasks = list(tasks.find(query).sort([
        ("status", ASCENDING),
        ("due_date", ASCENDING),
        ("created_at", DESCENDING)
    ]))

    user_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))
    metrics = calculate_task_metrics(uid)

    return render_template("tasks.html",
                           tasks=user_tasks,
                           subjects=user_subjects,
                           metrics=metrics,
                           status_filter=status_filter,
                           subject_filter=subject_filter,
                           priority_filter=priority_filter)


@app.route("/tasks/create", methods=["POST"])
@role_required("teacher", "admin")
def tasks_create():
    user = get_current_user()
    f = request.form
    title = f.get("title", "").strip()
    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("tasks_view"))

    tasks.insert_one({
        "user_id": user["id"],
        "title": title,
        "description": f.get("description", "").strip(),
        "subject": f.get("subject", "").strip(),
        "priority": f.get("priority", "medium"),
        "status": f.get("status", "pending"),
        "due_date": f.get("due_date", "").strip(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    flash("Task created successfully! 🎯", "ok")
    return redirect(url_for("tasks_view"))


@app.route("/tasks/update/<tid>", methods=["POST"])
@role_required("teacher", "admin")
def tasks_update(tid):
    user = get_current_user()
    f = request.form
    tasks.update_one(
        {"_id": oid(tid), "user_id": user["id"]},
        {"$set": {
            "title": f.get("title", "").strip(),
            "description": f.get("description", "").strip(),
            "subject": f.get("subject", "").strip(),
            "priority": f.get("priority", "medium"),
            "status": f.get("status", "pending"),
            "due_date": f.get("due_date", "").strip(),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    flash("Task updated! ✅", "ok")
    return redirect(url_for("tasks_view"))


@app.route("/tasks/toggle/<tid>", methods=["POST"])
@role_required("teacher", "admin")
def tasks_toggle(tid):
    user = get_current_user()
    t = tasks.find_one({"_id": oid(tid), "user_id": user["id"]})
    if t:
        new_status = "completed" if t.get("status") != "completed" else "pending"
        tasks.update_one(
            {"_id": t["_id"]},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        msg = "Task completed! 🎉" if new_status == "completed" else "Task marked pending."
        flash(msg, "ok")
    return redirect(url_for("tasks_view"))


@app.route("/tasks/delete/<tid>", methods=["POST"])
@role_required("teacher", "admin")
def tasks_delete(tid):
    user = get_current_user()
    tasks.delete_one({"_id": oid(tid), "user_id": user["id"]})
    flash("Task deleted.", "ok")
    return redirect(url_for("tasks_view"))


# ---------------------------------------------------------------- Study Notes (Pure Notes without AI)
@app.route("/notes", methods=["GET"])
@login_required
def notes_view():
    user = get_current_user()
    uid = user["id"]

    sub_filter = request.args.get("subject", "")
    search_query = request.args.get("q", "").strip()

    query = {"user_id": uid}
    if sub_filter:
        query["subject"] = sub_filter
    if search_query:
        query["$or"] = [
            {"title": {"$regex": search_query, "$options": "i"}},
            {"content": {"$regex": search_query, "$options": "i"}},
            {"tags": {"$regex": search_query, "$options": "i"}}
        ]

    user_notes = list(notes.find(query).sort("updated_at", DESCENDING))
    user_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))

    return render_template("notes.html",
                           notes=user_notes,
                           subjects=user_subjects,
                           sub_filter=sub_filter,
                           search_query=search_query)


@app.route("/notes/create", methods=["POST"])
@login_required
def notes_create():
    user = get_current_user()
    f = request.form
    title = f.get("title", "").strip()
    if not title:
        flash("Note title is required.", "error")
        return redirect(url_for("notes_view"))

    subject_val = f.get("subject", "General").strip()

    notes.insert_one({
        "user_id": user["id"],
        "title": title,
        "content": f.get("content", "").strip(),
        "subject": subject_val,
        "tags": f.get("tags", "").strip(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })

    # Ensure subject is enrolled
    if not subjects.find_one({"user_id": user["id"], "name": subject_val}):
        subjects.insert_one({
            "user_id": user["id"],
            "name": subject_val,
            "icon": DEFAULT_SUBJECT_ICONS.get(subject_val, "📘"),
            "created_at": datetime.now(timezone.utc)
        })

    flash("Study note created successfully! 📝", "ok")
    return redirect(url_for("notes_view"))


@app.route("/notes/update/<nid>", methods=["POST"])
@login_required
def notes_update(nid):
    user = get_current_user()
    f = request.form
    notes.update_one(
        {"_id": oid(nid), "user_id": user["id"]},
        {"$set": {
            "title": f.get("title", "").strip(),
            "content": f.get("content", "").strip(),
            "subject": f.get("subject", "").strip(),
            "tags": f.get("tags", "").strip(),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    flash("Note updated! ✅", "ok")
    return redirect(url_for("notes_view"))


@app.route("/notes/delete/<nid>", methods=["POST"])
@login_required
def notes_delete(nid):
    user = get_current_user()
    notes.delete_one({"_id": oid(nid), "user_id": user["id"]})
    flash("Note deleted.", "ok")
    return redirect(url_for("notes_view"))


@app.route("/notes/download/<nid>")
@login_required
def notes_download(nid):
    user = get_current_user()
    n = notes.find_one({"_id": oid(nid), "user_id": user["id"]})
    if not n:
        abort(404)

    fmt = request.args.get("format", "md")
    safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in n["title"])

    if fmt == "pdf":
        return render_template("note_print.html", note=n)
    else:
        filename = f"{safe_title}.md"
        return Response(
            n["content"],
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


# ---------------------------------------------------------------- Subjects
@app.route("/subjects", methods=["GET"])
@login_required
def subjects_view():
    user = get_current_user()
    uid = user["id"]
    user_subjects = list(subjects.find({"user_id": uid}).sort("name", ASCENDING))

    for s in user_subjects:
        s["notes_count"] = notes.count_documents({"user_id": uid, "subject": s["name"]})
        s["tasks_count"] = tasks.count_documents({"user_id": uid, "subject": s["name"]})
        s["att"] = calculate_attendance_metrics(uid, subject=s["name"])

    return render_template("subjects.html", user_subjects=user_subjects)


@app.route("/subjects/add", methods=["POST"])
@login_required
def subjects_add():
    user = get_current_user()
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "📘").strip()

    if not name:
        flash("Subject name is required.", "error")
        return redirect(url_for("subjects_view"))

    if subjects.find_one({"user_id": user["id"], "name": name}):
        flash("You already have this subject enrolled.", "error")
        return redirect(url_for("subjects_view"))

    subjects.insert_one({
        "user_id": user["id"],
        "name": name,
        "icon": icon,
        "created_at": datetime.now(timezone.utc)
    })
    flash(f"Subject '{name}' enrolled! 🎓", "ok")
    return redirect(url_for("subjects_view"))


@app.route("/subjects/delete/<sid>", methods=["POST"])
@login_required
def subjects_delete(sid):
    user = get_current_user()
    subjects.delete_one({"_id": oid(sid), "user_id": user["id"]})
    flash("Subject removed.", "ok")
    return redirect(url_for("subjects_view"))


# ---------------------------------------------------------------- Notices
@app.route("/notices")
@login_required
def notices_list():
    cat_filter = request.args.get("category", "")
    flt = {"category": cat_filter} if cat_filter else {}
    rows = list(notices.find(flt).sort("created", DESCENDING))
    return render_template("notices.html", rows=rows, cat_filter=cat_filter)


@app.route("/notices/add", methods=["POST"])
@role_required("admin", "teacher")
def notices_add():
    user = get_current_user()
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    category = request.form.get("category", "General").strip()

    if title and body:
        notices.insert_one({
            "title": title,
            "body": body,
            "category": category,
            "author": user.get("name", "Faculty"),
            "created": datetime.now(timezone.utc)
        })
        flash("Announcement published! 📢", "ok")
    return redirect(url_for("notices_list"))


@app.route("/notices/delete/<nid>", methods=["POST"])
@role_required("admin")
def notices_delete(nid):
    notices.delete_one({"_id": oid(nid)})
    flash("Announcement deleted.", "ok")
    return redirect(url_for("notices_list"))


# ---------------------------------------------------------------- Institutional Admin: Students & Courses
@app.route("/students", methods=["GET"])
@login_required
def students_list():
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    # RBAC: Students cannot view the complete student list (403 Forbidden)
    if role == "student":
        abort(403)

    q = request.args.get("q", "").strip().lower()

    if role == "teacher":
        # Teacher can ONLY view students assigned to them
        assigned = get_teacher_students(uid)
        if q:
            rows = [s for s in assigned if q in s.get("name", "").lower() or q in s.get("roll_no", "").lower() or q in s.get("email", "").lower()]
        else:
            rows = assigned
        teachers_list = []
    else:
        # Admin can view all students across the platform
        teacher_filter = request.args.get("teacher_id", "").strip()
        all_st = get_all_students_with_details()
        if teacher_filter:
            all_st = [s for s in all_st if s.get("teacher_id") == teacher_filter]
        if q:
            rows = [s for s in all_st if q in s.get("name", "").lower() or q in s.get("roll_no", "").lower() or q in s.get("email", "").lower()]
        else:
            rows = all_st
        teachers_list = list(users.find({"role": "teacher"}).sort("name", ASCENDING))

    return render_template("students.html", rows=rows, q=q, teachers=teachers_list, role=role)


@app.route("/students/<sid>", methods=["GET"])
@login_required
def student_profile_view(sid):
    """View individual student profile and academic record."""
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    s_doc = get_student_record(sid)
    if not s_doc:
        abort(404)

    target_user_id = s_doc.get("user_id") or str(s_doc["_id"])
    target_roll = s_doc.get("roll_no")

    # Authorization Check 1: Student can ONLY view their own profile!
    if role == "student":
        if uid != target_user_id and user.get("roll_no") != target_roll and user.get("username", "").upper() != target_roll:
            abort(403)

    # Authorization Check 2: Teacher can ONLY view assigned students!
    elif role == "teacher":
        if not is_student_assigned_to_teacher(s_doc, uid):
            abort(403)

    # Admin has permission to view all student profiles

    att_stats = calculate_attendance_metrics(target_user_id)
    att_records = list(attendance.find({
        "$or": [{"user_id": target_user_id}, {"student_id": target_user_id}, {"student_roll": target_roll}]
    }).sort("date", DESCENDING))

    student_submissions = list(submissions.find({
        "$or": [{"student_id": target_user_id}, {"student_roll": target_roll}]
    }).sort("submitted_at", DESCENDING))

    all_teachers = list(users.find({"role": "teacher"}).sort("name", ASCENDING)) if role == "admin" else []
    assigned_teachers = get_student_teachers(s_doc)

    return render_template("student_profile.html",
                           student=s_doc,
                           att_stats=att_stats,
                           att_records=att_records,
                           submissions=student_submissions,
                           teachers=all_teachers,
                           assigned_teachers=assigned_teachers,
                           role=role)


@app.route("/students/assign_teacher", methods=["POST"])
@role_required("admin")
def students_assign_teacher():
    """Admin assigns or reassigns a teacher to a student."""
    sid = request.form.get("student_id", "").strip()
    tid = request.form.get("teacher_id", "").strip()
    next_url = request.form.get("next") or request.referrer or url_for("students_list")

    teacher = users.find_one({"_id": oid(tid), "role": "teacher"}) if tid else None
    t_name = teacher["name"] if teacher else "Unassigned"
    tid_str = str(teacher["_id"]) if teacher else ""

    if ObjectId.is_valid(sid):
        students.update_one({"_id": ObjectId(sid)}, {"$set": {"teacher_id": tid_str, "teacher_name": t_name}})
        st = students.find_one({"_id": ObjectId(sid)})
        if st and st.get("roll_no"):
            users.update_one({"roll_no": st["roll_no"]}, {"$set": {"teacher_id": tid_str, "teacher_name": t_name}})

    users.update_one(
        {"$or": [{"_id": oid(sid) if ObjectId.is_valid(sid) else None}, {"student_id": oid(sid) if ObjectId.is_valid(sid) else None}]},
        {"$set": {"teacher_id": tid_str, "teacher_name": t_name}}
    )

    if teacher and tid_str:
        st_doc = get_student_record(sid)
        st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else sid
        st_name = st_doc.get("name", "Student") if st_doc else "Student"
        st_roll = st_doc.get("roll_no", "") if st_doc else ""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        teacher_student_assignments.update_one(
            {"teacher_id": tid_str, "student_id": str(st_user_id)},
            {"$set": {
                "teacher_id": tid_str,
                "student_id": str(st_user_id),
                "student_roll": st_roll,
                "student_name": st_name,
                "teacher_name": t_name,
                "assigned_at": now_str,
                "status": "active"
            }},
            upsert=True
        )

    flash(f"Student assigned to faculty {t_name}. ✅", "ok")
    return redirect(next_url)


@app.route("/students/add", methods=["POST"])
@role_required("admin")
def students_add():
    f = request.form
    roll = f["roll_no"].strip().upper()
    try:
        res = students.insert_one({
            "roll_no": roll,
            "name": f["name"].strip(),
            "email": f["email"].strip(),
            "department": f["department"].strip(),
            "year": int(f.get("year", 1)),
            "created": datetime.now(timezone.utc)
        })
        users.insert_one({
            "username": roll.lower(),
            "email": f["email"].strip().lower(),
            "name": f["name"].strip(),
            "role": "student",
            "level": "college",
            "program": f["department"].strip(),
            "student_id": res.inserted_id,
            "password": generate_password_hash(roll.lower()),
            "created_at": datetime.now(timezone.utc)
        })
        flash(f"Student enrolled. Login credentials: {roll.lower()} / {roll.lower()}", "ok")
    except DuplicateKeyError:
        flash("A student with that roll number or email already exists.", "error")
    return redirect(url_for("students_list"))


@app.route("/students/delete/<sid>", methods=["POST"])
@role_required("admin")
def students_delete(sid):
    _id = oid(sid)
    students.delete_one({"_id": _id})
    users.delete_one({"student_id": _id})
    flash("Student record deleted.", "ok")
    return redirect(url_for("students_list"))


@app.route("/courses", methods=["GET"])
@login_required
def courses_list():
    user = get_current_user()
    role = user.get("role", "student")

    # If teacher: show their assigned courses first
    if role == "teacher":
        rows = list(courses.find({
            "$or": [{"instructor_id": user["id"]}, {"instructor": user.get("name")}]
        }).sort("code", ASCENDING))
    else:
        rows = list(courses.find().sort("code", ASCENDING))

    teachers = list(users.find({"role": "teacher"}).sort("name", ASCENDING))
    return render_template("courses.html", rows=rows, teachers=teachers)


@app.route("/courses/add", methods=["POST"])
@role_required("admin")
def courses_add():
    f = request.form
    code = f["code"].strip().upper()
    name = f["name"].strip()
    department = f["department"].strip()
    credits_val = int(f.get("credits", 3))
    instructor_id = f.get("instructor_id", "").strip()

    instructor_name = "Unassigned"
    if instructor_id:
        t_user = users.find_one({"_id": oid(instructor_id), "role": "teacher"})
        if t_user:
            instructor_name = t_user["name"]

    try:
        res = courses.insert_one({
            "code": code,
            "name": name,
            "department": department,
            "credits": credits_val,
            "instructor_id": instructor_id,
            "instructor": instructor_name
        })
        cid_str = str(res.inserted_id)

        # Append course to teacher's assigned_courses
        if instructor_id:
            users.update_one(
                {"_id": oid(instructor_id)},
                {"$addToSet": {"assigned_courses": cid_str}}
            )

        flash(f"Course {code} added and assigned to {instructor_name}.", "ok")
    except DuplicateKeyError:
        flash("That course code is already registered.", "error")
    return redirect(url_for("courses_list"))


@app.route("/courses/delete/<cid>", methods=["POST"])
@role_required("admin")
def courses_delete(cid):
    _id = oid(cid)
    # Remove from teacher assigned_courses
    users.update_many({}, {"$pull": {"assigned_courses": cid}})
    courses.delete_one({"_id": _id})
    attendance.delete_many({"course_id": cid})
    flash("Course deleted.", "ok")
    return redirect(url_for("courses_list"))


# ---------------------------------------------------------------- Assignments & Submissions
@app.route("/assignments", methods=["GET"])
@login_required
def assignments_list():
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    if role == "student":
        # Student sees assignments from ALL their assigned teachers (Many-to-Many)
        my_teachers = get_student_teachers(user)
        teacher_ids = [t["_id"] for t in my_teachers]
        if teacher_ids:
            a_query = {"teacher_id": {"$in": teacher_ids}}
        else:
            t_id = user.get("teacher_id")
            a_query = {"teacher_id": t_id} if t_id else {}
        user_assignments = list(assignments.find(a_query).sort("due_date", ASCENDING))
        st_subs = list(submissions.find({"$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]}))
        sub_map = {s.get("assignment_id"): s for s in st_subs}
        for a in user_assignments:
            aid_str = str(a["_id"])
            if aid_str in sub_map:
                a["submission"] = sub_map[aid_str]
                a["status_label"] = "Graded" if sub_map[aid_str].get("status") == "graded" else "Submitted"
            else:
                a["submission"] = None
                a["status_label"] = "Pending Submission"

        return render_template("assignments.html",
                               role="student",
                               assignments=user_assignments)

    elif role == "teacher":
        # Teacher sees their own assignments
        teacher_assignments = list(assignments.find({"teacher_id": uid}).sort("created_at", DESCENDING))
        assigned_students = get_teacher_students(uid)
        total_assigned_count = len(assigned_students)
        for a in teacher_assignments:
            aid_str = str(a["_id"])
            a["submissions_count"] = submissions.count_documents({"assignment_id": aid_str})
            a["graded_count"] = submissions.count_documents({"assignment_id": aid_str, "status": "graded"})
            a["total_students"] = total_assigned_count

        teacher_courses = list(courses.find({
            "$or": [{"instructor_id": uid}, {"instructor": user.get("name")}]
        }))

        return render_template("assignments.html",
                               role="teacher",
                               assignments=teacher_assignments,
                               courses=teacher_courses)

    else:
        # Admin sees all assignments across all faculty
        all_assignments = list(assignments.find().sort("created_at", DESCENDING))
        for a in all_assignments:
            aid_str = str(a["_id"])
            a["submissions_count"] = submissions.count_documents({"assignment_id": aid_str})
            a["graded_count"] = submissions.count_documents({"assignment_id": aid_str, "status": "graded"})

        return render_template("assignments.html",
                               role="admin",
                               assignments=all_assignments)


@app.route("/assignments/create", methods=["POST"])
@login_required
def assignments_create():
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    # Student & Admin cannot create assignments (User requirement: Teacher only!)
    if role != "teacher":
        abort(403)

    f = request.form
    title = f.get("title", "").strip()
    if not title:
        flash("Assignment title is required.", "error")
        return redirect(url_for("assignments_list"))

    assignments.insert_one({
        "teacher_id": uid,
        "teacher_name": user.get("name", "Faculty"),
        "title": title,
        "description": f.get("description", "").strip(),
        "subject": f.get("subject", "").strip(),
        "due_date": f.get("due_date", (date.today() + timedelta(days=7)).isoformat()),
        "total_marks": int(f.get("total_marks", 100)),
        "department": user.get("department", ""),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    flash("Assignment created successfully! 📄", "ok")
    return redirect(url_for("assignments_list"))


@app.route("/assignments/<aid>", methods=["GET"])
@login_required
def assignment_detail(aid):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    a = assignments.find_one({"_id": oid(aid)})
    if not a:
        abort(404)

    aid_str = str(a["_id"])

    if role == "teacher":
        # Teacher can ONLY view assignments they created! (403 for other teachers)
        if a.get("teacher_id") != uid:
            abort(403)

        subs = list(submissions.find({"assignment_id": aid_str}).sort("submitted_at", DESCENDING))
        assigned_students = get_teacher_students(uid)
        return render_template("assignment_detail.html",
                               assignment=a,
                               submissions=subs,
                               assigned_students=assigned_students,
                               role="teacher")

    elif role == "student":
        # Student views details and their OWN submission
        sub = submissions.find_one({
            "assignment_id": aid_str,
            "$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]
        })
        return render_template("assignment_detail.html",
                               assignment=a,
                               my_submission=sub,
                               role="student")

    else:
        # Admin can view assignment and all submissions
        subs = list(submissions.find({"assignment_id": aid_str}).sort("submitted_at", DESCENDING))
        return render_template("assignment_detail.html",
                               assignment=a,
                               submissions=subs,
                               role="admin")


@app.route("/assignments/update/<aid>", methods=["POST"])
@login_required
def assignment_update(aid):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    if role != "teacher":
        abort(403)

    a = assignments.find_one({"_id": oid(aid)})
    if not a:
        abort(404)

    if a.get("teacher_id") != uid:
        abort(403)

    f = request.form
    assignments.update_one(
        {"_id": a["_id"]},
        {"$set": {
            "title": f.get("title", a["title"]).strip(),
            "description": f.get("description", a.get("description", "")).strip(),
            "subject": f.get("subject", a.get("subject", "")).strip(),
            "due_date": f.get("due_date", a.get("due_date", "")).strip(),
            "total_marks": int(f.get("total_marks", a.get("total_marks", 100))),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    flash("Assignment details updated! ✅", "ok")
    return redirect(url_for("assignment_detail", aid=aid))


@app.route("/assignments/delete/<aid>", methods=["POST"])
@login_required
def assignment_delete(aid):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    if role != "teacher":
        abort(403)

    a = assignments.find_one({"_id": oid(aid)})
    if not a:
        abort(404)

    if a.get("teacher_id") != uid:
        abort(403)

    assignments.delete_one({"_id": a["_id"]})
    submissions.delete_many({"assignment_id": aid})
    flash("Assignment and associated submissions deleted.", "ok")
    return redirect(url_for("assignments_list"))


@app.route("/assignments/<aid>/submit", methods=["POST"])
@login_required
def assignment_submit(aid):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    if role != "student":
        abort(403)

    a = assignments.find_one({"_id": oid(aid)})
    if not a:
        abort(404)

    content = request.form.get("content", "").strip()
    if not content:
        flash("Submission content or link is required.", "error")
        return redirect(url_for("assignment_detail", aid=aid))

    aid_str = str(a["_id"])
    submissions.update_one(
        {"assignment_id": aid_str, "$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]},
        {"$set": {
            "assignment_id": aid_str,
            "assignment_title": a["title"],
            "student_id": uid,
            "student_name": user.get("name"),
            "student_roll": user.get("roll_no", user.get("username", "").upper()),
            "teacher_id": a.get("teacher_id"),
            "content": content,
            "submitted_at": datetime.now(timezone.utc),
            "status": "submitted"
        }},
        upsert=True
    )
    flash("Assignment submitted successfully! 🚀", "ok")
    return redirect(url_for("assignment_detail", aid=aid))


@app.route("/submissions/<sub_id>", methods=["GET"])
@login_required
def submission_detail(sub_id):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    sub = submissions.find_one({"_id": oid(sub_id)})
    if not sub:
        abort(404)

    # Authorization checks:
    # 1. Student can ONLY view their own submission!
    if role == "student":
        if sub.get("student_id") != uid and sub.get("student_roll") != user.get("roll_no"):
            abort(403)

    # 2. Teacher can ONLY view submissions for assignments they own!
    elif role == "teacher":
        if sub.get("teacher_id") != uid:
            abort(403)

    a = assignments.find_one({"_id": oid(sub["assignment_id"])}) if ObjectId.is_valid(sub.get("assignment_id", "")) else None

    return render_template("submission_detail.html",
                           submission=sub,
                           assignment=a,
                           role=role)


@app.route("/submissions/<sub_id>/grade", methods=["POST"])
@login_required
def submission_grade(sub_id):
    user = get_current_user()
    role = user.get("role", "student")
    uid = user["id"]

    if role != "teacher":
        abort(403)

    sub = submissions.find_one({"_id": oid(sub_id)})
    if not sub:
        abort(404)

    # Verify teacher owns this assignment/submission
    if sub.get("teacher_id") != uid:
        abort(403)

    f = request.form
    marks_val = f.get("marks")
    marks = int(marks_val) if marks_val and marks_val.isdigit() else None
    feedback = f.get("feedback", "").strip()

    submissions.update_one(
        {"_id": sub["_id"]},
        {"$set": {
            "marks": marks,
            "feedback": feedback,
            "status": "graded",
            "graded_at": datetime.now(timezone.utc)
        }}
    )
    flash(f"Submission for {sub.get('student_name')} evaluated and graded! 📝", "ok")
    return redirect(request.referrer or url_for("assignment_detail", aid=sub["assignment_id"]))


# ---------------------------------------------------------------- REST API Endpoints
@app.route("/api/auth", methods=["GET", "POST"])
def api_auth():
    action = request.args.get("action") or (request.json.get("action") if request.is_json else "")
    data = request.get_json(silent=True) or request.form.to_dict() or {}

    if action == "register":
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        level = data.get("level", "school")
        program = data.get("program", "")
        class_name = data.get("class_name", "")
        board = data.get("board", "CBSE")

        if not (name and email and password):
            return jsonify({"error": "Name, email, and password are required"}), 400

        if users.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409

        username = email.split("@")[0]
        res = users.insert_one({
            "username": username,
            "email": email,
            "name": name,
            "password": generate_password_hash(password),
            "role": "student",
            "level": level,
            "program": program,
            "class_name": class_name,
            "board": board,
            "avatar_color": "#ff0035",
            "created_at": datetime.now(timezone.utc)
        })
        return jsonify({
            "message": "Registration successful!",
            "token": f"token-{res.inserted_id}",
            "user": {
                "id": str(res.inserted_id),
                "name": name,
                "email": email,
                "level": level,
                "program": program,
                "board": board
            }
        }), 201

    elif action == "login":
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        user = users.find_one({"$or": [{"email": email}, {"username": email}]})
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        session["user"] = {
            "id": str(user["_id"]),
            "name": user.get("name"),
            "email": user.get("email"),
            "username": user.get("username"),
            "role": user.get("role", "student")
        }
        user_clean = serialize_doc(user)
        user_clean.pop("password", None)
        return jsonify({
            "message": "Login successful!",
            "token": f"token-{user['_id']}",
            "user": user_clean
        })

    elif action == "profile":
        u = get_current_user()
        if not u:
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify({"user": u})

    elif action == "update_profile":
        u = get_current_user()
        if not u:
            return jsonify({"error": "Unauthorized"}), 401
        users.update_one(
            {"_id": oid(u["id"])},
            {"$set": {
                "name": data.get("name", u.get("name")),
                "program": data.get("program", u.get("program")),
                "class_name": data.get("class_name", u.get("class_name")),
                "board": data.get("board", u.get("board"))
            }}
        )
        return jsonify({"message": "Profile updated successfully"})

    return jsonify({"error": "Invalid action parameter"}), 400


@app.route("/api/tasks", methods=["GET", "POST", "PUT", "DELETE"])
def api_tasks():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]

    if request.method == "GET":
        if request.args.get("action") == "stats":
            return jsonify({"stats": calculate_task_metrics(uid)})
        rows = [serialize_doc(t) for t in tasks.find({"user_id": uid}).sort("due_date", ASCENDING)]
        return jsonify({"tasks": rows})

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        res = tasks.insert_one({
            "user_id": uid,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "subject": data.get("subject", ""),
            "priority": data.get("priority", "medium"),
            "status": data.get("status", "pending"),
            "due_date": data.get("due_date"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
        t = serialize_doc(tasks.find_one({"_id": res.inserted_id}))
        return jsonify({"message": "Task created!", "task": t}), 201

    elif request.method == "PUT":
        data = request.get_json(silent=True) or request.form.to_dict()
        tid = request.args.get("id") or data.get("id")
        data.pop("id", None)
        data.pop("_id", None)
        data["updated_at"] = datetime.now(timezone.utc)
        tasks.update_one({"_id": oid(tid), "user_id": uid}, {"$set": data})
        t = serialize_doc(tasks.find_one({"_id": oid(tid)}))
        return jsonify({"message": "Task updated!", "task": t})

    elif request.method == "DELETE":
        tid = request.args.get("id")
        tasks.delete_one({"_id": oid(tid), "user_id": uid})
        return jsonify({"message": "Task deleted!"})


@app.route("/api/attendance", methods=["GET", "POST", "PUT", "DELETE"])
def api_attendance():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]
    role = user.get("role", "student")

    if request.method == "GET":
        target_uid = request.args.get("user_id") or request.args.get("student_id")
        action = request.args.get("action")
        month = request.args.get("month")
        year = request.args.get("year")

        if role == "student":
            # Student can only access their own records
            if target_uid and target_uid != uid and target_uid != user.get("roll_no"):
                return jsonify({"error": "Forbidden: Students can only view their own records"}), 403
            if action == "stats":
                return jsonify({"stats": calculate_attendance_metrics(uid, month=month, year=year)})
            rows = [serialize_doc(a) for a in attendance.find({"$or": [{"user_id": uid}, {"student_id": uid}, {"student_roll": user.get("roll_no")}]}).sort("date", DESCENDING)]
            return jsonify({"attendance": rows})

        elif role == "teacher":
            # Teacher can access assigned students
            if target_uid:
                if not is_student_assigned_to_teacher(target_uid, uid):
                    return jsonify({"error": "Forbidden: Student not assigned to you"}), 403
                if action == "stats":
                    return jsonify({"stats": calculate_attendance_metrics(target_uid, month=month, year=year)})
                rows = [serialize_doc(a) for a in attendance.find({"$or": [{"user_id": target_uid}, {"student_id": target_uid}]}).sort("date", DESCENDING)]
                return jsonify({"attendance": rows})
            rows = [serialize_doc(a) for a in attendance.find({"teacher_id": uid}).sort("date", DESCENDING)]
            return jsonify({"attendance": rows})

        else:
            # Admin can view all
            q = {}
            if target_uid:
                q["$or"] = [{"user_id": target_uid}, {"student_id": target_uid}]
            if request.args.get("teacher_id"):
                q["teacher_id"] = request.args.get("teacher_id")
            rows = [serialize_doc(a) for a in attendance.find(q).sort("date", DESCENDING)]
            return jsonify({"attendance": rows})

    elif request.method in ("POST", "PUT"):
        # ADMIN CANNOT MARK ATTENDANCE (403 Forbidden)
        if role == "admin":
            return jsonify({"error": "Forbidden: Admin has strictly read-only access to attendance"}), 403
        # STUDENT CANNOT MARK ATTENDANCE (403 Forbidden)
        if role == "student":
            return jsonify({"error": "Forbidden: Students cannot mark or modify attendance"}), 403

        # Teacher marks attendance for assigned student
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        target_student = data.get("student_id") or data.get("user_id")
        if not target_student or not is_student_assigned_to_teacher(target_student, uid):
            return jsonify({"error": "Forbidden: Student not assigned to this teacher"}), 403

        st_doc = get_student_record(target_student)
        st_user_id = st_doc.get("user_id") or str(st_doc["_id"]) if st_doc else target_student
        st_name = st_doc.get("name", "Student") if st_doc else "Student"
        st_roll = st_doc.get("roll_no", "") if st_doc else ""

        res = attendance.insert_one({
            "student_id": st_user_id,
            "user_id": st_user_id,
            "student_name": st_name,
            "student_roll": st_roll,
            "teacher_id": uid,
            "teacher_name": user.get("name"),
            "date": data.get("date", date.today().isoformat()),
            "status": data.get("status", "Present"),
            "subject": data.get("subject", "General"),
            "notes": data.get("notes", ""),
            "timestamp": datetime.now(timezone.utc)
        })
        return jsonify({"message": "Attendance marked!", "id": str(res.inserted_id)}), 201

    elif request.method == "DELETE":
        # ADMIN CANNOT DELETE ATTENDANCE (403 Forbidden)
        if role == "admin":
            return jsonify({"error": "Forbidden: Admin cannot modify or delete attendance records"}), 403
        # STUDENT CANNOT DELETE ATTENDANCE (403 Forbidden)
        if role == "student":
            return jsonify({"error": "Forbidden: Students cannot modify or delete attendance"}), 403

        aid = request.args.get("id") or (request.json.get("id") if request.is_json else None)
        if not aid:
            return jsonify({"error": "Missing attendance id"}), 400
        rec = attendance.find_one({"_id": oid(aid)})
        if not rec:
            return jsonify({"error": "Record not found"}), 404
        if rec.get("teacher_id") != uid and not is_student_assigned_to_teacher(rec.get("student_id") or rec.get("user_id"), uid):
            return jsonify({"error": "Forbidden: Cannot delete record of unassigned student"}), 403

        attendance.delete_one({"_id": rec["_id"]})
        return jsonify({"message": "Attendance record deleted!"})


@app.route("/api/assignments", methods=["GET", "POST", "PUT", "DELETE"])
def api_assignments():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]
    role = user.get("role", "student")

    if request.method == "GET":
        if role == "student":
            my_teachers = get_student_teachers(user)
            t_ids = [t["_id"] for t in my_teachers]
            if t_ids:
                q = {"teacher_id": {"$in": t_ids}}
            else:
                t_id = user.get("teacher_id")
                q = {"teacher_id": t_id} if t_id else {}
            rows = [serialize_doc(a) for a in assignments.find(q).sort("due_date", ASCENDING)]
        elif role == "teacher":
            rows = [serialize_doc(a) for a in assignments.find({"teacher_id": uid}).sort("created_at", DESCENDING)]
        else:
            rows = [serialize_doc(a) for a in assignments.find().sort("created_at", DESCENDING)]
        return jsonify({"assignments": rows})

    elif request.method == "POST":
        if role != "teacher":
            return jsonify({"error": "Forbidden: Only teachers can create assignments"}), 403
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        res = assignments.insert_one({
            "teacher_id": uid,
            "teacher_name": user.get("name"),
            "title": data.get("title", "Untitled Assignment"),
            "description": data.get("description", ""),
            "subject": data.get("subject", ""),
            "due_date": data.get("due_date", (date.today() + timedelta(days=7)).isoformat()),
            "total_marks": int(data.get("total_marks", 100)),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
        a = serialize_doc(assignments.find_one({"_id": res.inserted_id}))
        return jsonify({"message": "Assignment created!", "assignment": a}), 201

    elif request.method in ("PUT", "DELETE"):
        if role != "teacher":
            return jsonify({"error": "Forbidden: Only teachers can edit or delete assignments"}), 403
        aid = request.args.get("id") or (request.json.get("id") if request.is_json else None)
        a = assignments.find_one({"_id": oid(aid)})
        if not a:
            return jsonify({"error": "Assignment not found"}), 404
        if a.get("teacher_id") != uid:
            return jsonify({"error": "Forbidden: Cannot modify assignment of another teacher"}), 403

        if request.method == "DELETE":
            assignments.delete_one({"_id": a["_id"]})
            submissions.delete_many({"assignment_id": aid})
            return jsonify({"message": "Assignment deleted!"})
        else:
            data = request.get_json(silent=True) or request.form.to_dict() or {}
            data.pop("id", None)
            data.pop("_id", None)
            data["updated_at"] = datetime.now(timezone.utc)
            assignments.update_one({"_id": a["_id"]}, {"$set": data})
            return jsonify({"message": "Assignment updated!"})


@app.route("/api/submissions", methods=["GET", "POST"])
def api_submissions():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]
    role = user.get("role", "student")

    if request.method == "GET":
        if role == "student":
            rows = [serialize_doc(s) for s in submissions.find({"$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]})]
        elif role == "teacher":
            rows = [serialize_doc(s) for s in submissions.find({"teacher_id": uid})]
        else:
            rows = [serialize_doc(s) for s in submissions.find()]
        return jsonify({"submissions": rows})

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        action = data.get("action", "submit")

        if action == "grade":
            if role != "teacher":
                return jsonify({"error": "Forbidden: Only teachers can evaluate submissions"}), 403
            sub_id = data.get("submission_id")
            sub = submissions.find_one({"_id": oid(sub_id)})
            if not sub:
                return jsonify({"error": "Submission not found"}), 404
            if sub.get("teacher_id") != uid:
                return jsonify({"error": "Forbidden: Cannot grade submission of another teacher's student"}), 403
            submissions.update_one(
                {"_id": sub["_id"]},
                {"$set": {
                    "marks": data.get("marks"),
                    "feedback": data.get("feedback"),
                    "status": "graded",
                    "graded_at": datetime.now(timezone.utc)
                }}
            )
            return jsonify({"message": "Submission graded successfully!"})

        else: # Submit
            if role != "student":
                return jsonify({"error": "Forbidden: Only students can submit assignments"}), 403
            aid = data.get("assignment_id")
            a = assignments.find_one({"_id": oid(aid)})
            if not a:
                return jsonify({"error": "Assignment not found"}), 404
            aid_str = str(a["_id"])
            submissions.update_one(
                {"assignment_id": aid_str, "$or": [{"student_id": uid}, {"student_roll": user.get("roll_no")}]},
                {"$set": {
                    "assignment_id": aid_str,
                    "assignment_title": a["title"],
                    "student_id": uid,
                    "student_name": user.get("name"),
                    "student_roll": user.get("roll_no", user.get("username", "").upper()),
                    "teacher_id": a.get("teacher_id"),
                    "content": data.get("content", ""),
                    "submitted_at": datetime.now(timezone.utc),
                    "status": "submitted"
                }},
                upsert=True
            )
            return jsonify({"message": "Assignment submitted successfully!"}), 201


@app.route("/api/notes", methods=["GET", "POST", "PUT", "DELETE"])
def api_notes():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]

    if request.method == "GET":
        sub = request.args.get("subject")
        flt = {"user_id": uid}
        if sub:
            flt["subject"] = sub
        rows = [serialize_doc(n) for n in notes.find(flt).sort("updated_at", DESCENDING)]
        return jsonify({"notes": rows})

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        res = notes.insert_one({
            "user_id": uid,
            "title": data.get("title", "Untitled Note"),
            "content": data.get("content", ""),
            "subject": data.get("subject", "General"),
            "tags": data.get("tags", ""),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
        n = serialize_doc(notes.find_one({"_id": res.inserted_id}))
        return jsonify({"message": "Note created!", "note": n}), 201

    elif request.method == "DELETE":
        nid = request.args.get("id")
        notes.delete_one({"_id": oid(nid), "user_id": uid})
        return jsonify({"message": "Note deleted!"})


@app.route("/api/subjects", methods=["GET", "POST", "DELETE"])
def api_subjects():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    uid = user["id"]

    if request.method == "GET":
        rows = [serialize_doc(s) for s in subjects.find({"user_id": uid}).sort("name", ASCENDING)]
        return jsonify({"subjects": rows})

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        name = data.get("name", "").strip()
        icon = data.get("icon", "📘")
        res = subjects.insert_one({
            "user_id": uid,
            "name": name,
            "icon": icon,
            "created_at": datetime.now(timezone.utc)
        })
        s = serialize_doc(subjects.find_one({"_id": res.inserted_id}))
        return jsonify({"message": "Subject added!", "subject": s}), 201

    elif request.method == "DELETE":
        sid = request.args.get("id")
        subjects.delete_one({"_id": oid(sid), "user_id": uid})
        return jsonify({"message": "Subject deleted!"})


@app.route("/api/download")
def api_download():
    """CAMPUSCORE compatible minimal valid PDF generator."""
    subject = request.args.get("subject", "Subject")
    topic = request.args.get("topic", "Topic")
    ptype = request.args.get("type", "Material")

    safe_name = f"{subject}_{topic}_{ptype}".replace(" ", "_") + ".pdf"
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj\n"
        b"4 0 obj <</Length 260>> stream\n"
        b"BT /F1 22 Tf 50 720 Td (CAMPUSCORE Study Material) Tj\n"
        b"/F1 14 Tf 0 -35 Td (Subject: " + subject.encode("latin-1", "replace") + b") Tj\n"
        b"/F1 14 Tf 0 -25 Td (Topic: " + topic.encode("latin-1", "replace") + b") Tj\n"
        b"/F1 12 Tf 0 -25 Td (Type: " + ptype.encode("latin-1", "replace") + b") Tj\n"
        b"/F1 10 Tf 0 -45 Td (Curated by CAMPUSCORE Academic Learning Platform.) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000056 00000 n \n0000000111 00000 n \n0000000213 00000 n \n0000000520 00000 n \n"
        b"trailer <</Size 6 /Root 1 0 R>>\nstartxref\n600\n%%EOF"
    )
    return Response(
        pdf_content,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'}
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
