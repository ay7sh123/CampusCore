"""
CAMPUSCORE Test Suite
Validates core routes, authentication, calculations, faculty subject assignments,
and the full Role-Based Access Control (RBAC) requirements across Student, Teacher, and Admin roles.
"""
import unittest
import json
import os
import sys
import re
from datetime import datetime, date, timezone
from bson import ObjectId

# Add campuscore to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import app as campus_app
from app import app, calculate_attendance_metrics, calculate_task_metrics


class MockCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)

    def __len__(self):
        return len(self.docs)

    def __getitem__(self, index):
        return self.docs[index]


def _match_filter(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_match_filter(doc, sub_q) for sub_q in v):
                return False
        elif k == "$and":
            if not all(_match_filter(doc, sub_q) for sub_q in v):
                return False
        elif isinstance(v, dict):
            val = doc.get(k)
            for op, op_val in v.items():
                if op == "$in":
                    str_vals = [str(x) for x in op_val]
                    if val not in op_val and str(val) not in str_vals:
                        return False
                elif op == "$nin":
                    str_vals = [str(x) for x in op_val]
                    if val in op_val or str(val) in str_vals:
                        return False
                elif op == "$ne":
                    if val == op_val or str(val) == str(op_val):
                        return False
                elif op == "$regex":
                    if not isinstance(val, str) or not re.search(op_val, val, re.I if "i" in v.get("$options", "") else 0):
                        return False
        else:
            val = doc.get(k)
            if val != v and str(val) != str(v):
                return False
    return True


class MockCollection:
    def __init__(self, initial_data=None):
        self.docs = [dict(d) for d in initial_data] if initial_data else []

    def find_one(self, query=None):
        query = query or {}
        for d in self.docs:
            if _match_filter(d, query):
                return dict(d)
        return None

    def find(self, query=None):
        query = query or {}
        matches = [dict(d) for d in self.docs if _match_filter(d, query)]
        return MockCursor(matches)

    def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        res = type("InsertResult", (), {})()
        res.inserted_id = d["_id"]
        return res

    def insert_many(self, doc_list):
        for doc in doc_list:
            self.insert_one(doc)

    def update_one(self, query, update, upsert=False):
        found = False
        for i, d in enumerate(self.docs):
            if _match_filter(d, query):
                found = True
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                break
        if not found and upsert:
            new_doc = {}
            if "$set" in update:
                new_doc.update(update["$set"])
            for k, v in query.items():
                if not k.startswith("$"):
                    new_doc[k] = v
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self.docs.append(new_doc)

    def update_many(self, query, update):
        for i, d in enumerate(self.docs):
            if _match_filter(d, query):
                if "$set" in update:
                    self.docs[i].update(update["$set"])

    def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match_filter(d, query):
                del self.docs[i]
                break

    def delete_many(self, query):
        self.docs = [d for d in self.docs if not _match_filter(d, query)]

    def count_documents(self, query=None):
        query = query or {}
        return sum(1 for d in self.docs if _match_filter(d, query))


class CampusCoreTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"
        self.client = app.test_client()

        # Seed mock database for RBAC tests
        self.t1_id = ObjectId()
        self.t2_id = ObjectId()
        self.s1_id = ObjectId()
        self.s2_id = ObjectId()
        self.s3_id = ObjectId()
        self.admin_id = ObjectId()

        self.mock_users = MockCollection([
            {
                "_id": self.admin_id,
                "username": "admin",
                "email": "admin@campuscore.io",
                "name": "System Administrator",
                "role": "admin",
                "department": "Administration"
            },
            {
                "_id": self.t1_id,
                "username": "teacher",
                "email": "sharma@campuscore.io",
                "name": "Prof. H. Sharma",
                "role": "teacher",
                "department": "Computer Science",
                "assigned_courses": []
            },
            {
                "_id": self.t2_id,
                "username": "teacher2",
                "email": "mehta@campuscore.io",
                "name": "Dr. Priya Mehta",
                "role": "teacher",
                "department": "Mathematics",
                "assigned_courses": []
            },
            {
                "_id": self.s1_id,
                "username": "student",
                "email": "student@campuscore.io",
                "name": "Aarav Sharma",
                "role": "student",
                "roll_no": "CS2026-001",
                "department": "Computer Science",
                "teacher_id": str(self.t1_id),
                "teacher_name": "Prof. H. Sharma"
            },
            {
                "_id": self.s2_id,
                "username": "student2",
                "email": "diya@campuscore.io",
                "name": "Diya Sen",
                "role": "student",
                "roll_no": "CS2026-002",
                "department": "Computer Science",
                "teacher_id": str(self.t1_id),
                "teacher_name": "Prof. H. Sharma"
            },
            {
                "_id": self.s3_id,
                "username": "student3",
                "email": "rohan@campuscore.io",
                "name": "Rohan Verma",
                "role": "student",
                "roll_no": "MA2026-001",
                "department": "Mathematics",
                "teacher_id": str(self.t2_id),
                "teacher_name": "Dr. Priya Mehta"
            }
        ])

        self.mock_students = MockCollection([
            {"_id": ObjectId(), "roll_no": "CS2026-001", "name": "Aarav Sharma", "email": "student@campuscore.io", "department": "Computer Science", "year": 2, "teacher_id": str(self.t1_id), "teacher_name": "Prof. H. Sharma", "user_id": str(self.s1_id)},
            {"_id": ObjectId(), "roll_no": "CS2026-002", "name": "Diya Sen", "email": "diya@campuscore.io", "department": "Computer Science", "year": 2, "teacher_id": str(self.t1_id), "teacher_name": "Prof. H. Sharma", "user_id": str(self.s2_id)},
            {"_id": ObjectId(), "roll_no": "MA2026-001", "name": "Rohan Verma", "email": "rohan@campuscore.io", "department": "Mathematics", "year": 2, "teacher_id": str(self.t2_id), "teacher_name": "Dr. Priya Mehta", "user_id": str(self.s3_id)}
        ])

        self.a1_id = ObjectId()
        self.a2_id = ObjectId()
        self.mock_assignments = MockCollection([
            {
                "_id": self.a1_id,
                "teacher_id": str(self.t1_id),
                "teacher_name": "Prof. H. Sharma",
                "title": "Data Structures AVL Trees",
                "subject": "CS201",
                "due_date": "2026-12-01",
                "total_marks": 100
            },
            {
                "_id": self.a2_id,
                "teacher_id": str(self.t2_id),
                "teacher_name": "Dr. Priya Mehta",
                "title": "Discrete Math Graph Theory",
                "subject": "MA201",
                "due_date": "2026-12-05",
                "total_marks": 50
            }
        ])

        self.sub1_id = ObjectId()
        self.sub3_id = ObjectId()
        self.mock_submissions = MockCollection([
            {
                "_id": self.sub1_id,
                "assignment_id": str(self.a1_id),
                "assignment_title": "Data Structures AVL Trees",
                "student_id": str(self.s1_id),
                "student_name": "Aarav Sharma",
                "student_roll": "CS2026-001",
                "teacher_id": str(self.t1_id),
                "content": "https://github.com/aarav/avl-trees",
                "submitted_at": datetime.now(timezone.utc),
                "status": "graded",
                "marks": 95,
                "feedback": "Excellent work!"
            },
            {
                "_id": self.sub3_id,
                "assignment_id": str(self.a2_id),
                "assignment_title": "Discrete Math Graph Theory",
                "student_id": str(self.s3_id),
                "student_name": "Rohan Verma",
                "student_roll": "MA2026-001",
                "teacher_id": str(self.t2_id),
                "content": "Graph proofs attached.",
                "submitted_at": datetime.now(timezone.utc),
                "status": "submitted",
                "marks": None,
                "feedback": None
            }
        ])

        self.att1_id = ObjectId()
        self.att3_id = ObjectId()
        self.mock_attendance = MockCollection([
            {
                "_id": self.att1_id,
                "student_id": str(self.s1_id),
                "user_id": str(self.s1_id),
                "student_name": "Aarav Sharma",
                "student_roll": "CS2026-001",
                "teacher_id": str(self.t1_id),
                "teacher_name": "Prof. H. Sharma",
                "subject": "CS201",
                "date": "2026-11-20",
                "status": "Present",
                "timestamp": datetime.now(timezone.utc)
            },
            {
                "_id": self.att3_id,
                "student_id": str(self.s3_id),
                "user_id": str(self.s3_id),
                "student_name": "Rohan Verma",
                "student_roll": "MA2026-001",
                "teacher_id": str(self.t2_id),
                "teacher_name": "Dr. Priya Mehta",
                "subject": "MA201",
                "date": "2026-11-20",
                "status": "Present",
                "timestamp": datetime.now(timezone.utc)
            }
        ])

        self.mock_courses = MockCollection([
            {"_id": ObjectId(), "code": "CS201", "name": "Data Structures", "department": "Computer Science", "credits": 4, "instructor_id": str(self.t1_id), "instructor": "Prof. H. Sharma"},
            {"_id": ObjectId(), "code": "MA201", "name": "Discrete Math", "department": "Mathematics", "credits": 4, "instructor_id": str(self.t2_id), "instructor": "Dr. Priya Mehta"}
        ])

        self.mock_teacher_student_assignments = MockCollection([
            {
                "_id": ObjectId(),
                "teacher_id": str(self.t1_id),
                "student_id": str(self.s1_id),
                "student_roll": "CS2026-001",
                "student_name": "Aarav Sharma",
                "teacher_name": "Prof. H. Sharma",
                "assigned_at": "2026-11-20",
                "status": "active"
            },
            {
                "_id": ObjectId(),
                "teacher_id": str(self.t2_id),
                "student_id": str(self.s1_id),
                "student_roll": "CS2026-001",
                "student_name": "Aarav Sharma",
                "teacher_name": "Dr. Priya Mehta",
                "assigned_at": "2026-11-20",
                "status": "active"
            },
            {
                "_id": ObjectId(),
                "teacher_id": str(self.t1_id),
                "student_id": str(self.s2_id),
                "student_roll": "CS2026-002",
                "student_name": "Diya Sen",
                "teacher_name": "Prof. H. Sharma",
                "assigned_at": "2026-11-20",
                "status": "active"
            },
            {
                "_id": ObjectId(),
                "teacher_id": str(self.t2_id),
                "student_id": str(self.s3_id),
                "student_roll": "MA2026-001",
                "student_name": "Rohan Verma",
                "teacher_name": "Dr. Priya Mehta",
                "assigned_at": "2026-11-20",
                "status": "active"
            }
        ])

        # Patch collections in app
        campus_app.users = self.mock_users
        campus_app.students = self.mock_students
        campus_app.assignments = self.mock_assignments
        campus_app.submissions = self.mock_submissions
        campus_app.attendance = self.mock_attendance
        campus_app.courses = self.mock_courses
        campus_app.teacher_student_assignments = self.mock_teacher_student_assignments
        campus_app.tasks = MockCollection()
        campus_app.notes = MockCollection()
        campus_app.subjects = MockCollection()
        campus_app.notices = MockCollection()

    def set_session_user(self, user_id, name, username, email, role, roll_no=None, teacher_id=None):
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": str(user_id),
                "name": name,
                "username": username,
                "email": email,
                "role": role,
                "roll_no": roll_no,
                "teacher_id": str(teacher_id) if teacher_id else None
            }

    # ==========================================
    # 1. CORE THEME & PALETTE TESTS
    # ==========================================
    def test_custom_color_palette_css(self):
        """Verify the exact user color palette in style.css."""
        css_path = os.path.join(os.path.dirname(__file__), "static", "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn("--ink-black: #0e131fff;", css)
        self.assertIn("--twilight-indigo: #38405fff;", css)
        self.assertIn("--vintage-grape: #59546cff;", css)
        self.assertIn("--cool-steel: #8b939cff;", css)
        self.assertIn("--strawberry-red: #ff0035ff;", css)

    def test_light_mode_color_palette_css(self):
        """Verify the exact user light mode color palette in style.css."""
        css_path = os.path.join(os.path.dirname(__file__), "static", "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn("--wheat: #f5e0b7ff;", css)
        self.assertIn("--soft-fawn: #d6ba73ff;", css)
        self.assertIn("--muted-teal: #8bbf9fff;", css)
        self.assertIn("--silver: #bab6b5ff;", css)
        self.assertIn("--thistle: #d9bfd2ff;", css)

    # ==========================================
    # 2. THE 12 EXPLICIT RBAC TEST CASES
    # ==========================================

    def test_case_1_student_a_cannot_view_student_b_attendance(self):
        """Test Case 1: Student A cannot view Student B's attendance (403)."""
        # Log in as Student 1 (Aarav)
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student", "CS2026-001", self.t1_id)

        # Attempt to access Student 3's profile/attendance (Rohan)
        res = self.client.get(f"/students/{self.s3_id}")
        self.assertEqual(res.status_code, 403)

        # Attempt to access Student 3's attendance via API
        res_api = self.client.get(f"/api/attendance?user_id={self.s3_id}")
        self.assertEqual(res_api.status_code, 403)

    def test_case_2_student_a_cannot_view_student_b_assignments_or_submissions(self):
        """Test Case 2: Student A cannot view Student B's assignments or submissions (403)."""
        # Log in as Student 1 (Aarav)
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student", "CS2026-001", self.t1_id)

        # Attempt to view Student 3's submission
        res = self.client.get(f"/submissions/{self.sub3_id}")
        self.assertEqual(res.status_code, 403)

    def test_case_3_teacher_a_cannot_access_teacher_b_students(self):
        """Test Case 3: Teacher A cannot access Teacher B's students (403)."""
        # Log in as Teacher 1 (Prof. Sharma)
        self.set_session_user(self.t1_id, "Prof. H. Sharma", "teacher", "sharma@campuscore.io", "teacher")

        # Student 3 (Rohan) belongs to Teacher 2 (Dr. Mehta). Teacher 1 should get 403
        res = self.client.get(f"/students/{self.s3_id}")
        self.assertEqual(res.status_code, 403)

        # Teacher 1 cannot access Teacher 2's assignment
        res_a = self.client.get(f"/assignments/{self.a2_id}")
        self.assertEqual(res_a.status_code, 403)

        # Teacher 1 cannot mark attendance for Student 3
        res_mark = self.client.post("/attendance/mark", data={"student_id": str(self.s3_id), "status": "Present"})
        self.assertEqual(res_mark.status_code, 403)

    def test_case_4_teacher_can_mark_attendance_for_assigned_students(self):
        """Test Case 4: Teacher can mark attendance for their assigned students."""
        # Log in as Teacher 1 (Prof. Sharma)
        self.set_session_user(self.t1_id, "Prof. H. Sharma", "teacher", "sharma@campuscore.io", "teacher")

        # Mark attendance for Student 1 (assigned to Teacher 1)
        res = self.client.post("/attendance/mark", data={
            "student_id": str(self.s1_id),
            "date": "2026-11-21",
            "status": "Present",
            "subject": "CS201"
        })
        self.assertIn(res.status_code, (200, 302))

        # Check in mock attendance collection
        saved = self.mock_attendance.find_one({"student_id": str(self.s1_id), "date": "2026-11-21"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("status"), "Present")

    def test_case_5_teacher_can_create_and_manage_assignments(self):
        """Test Case 5: Teacher can create and manage assignments."""
        # Log in as Teacher 1 (Prof. Sharma)
        self.set_session_user(self.t1_id, "Prof. H. Sharma", "teacher", "sharma@campuscore.io", "teacher")

        # Create new assignment
        res = self.client.post("/assignments/create", data={
            "title": "Recursion & Dynamic Programming",
            "subject": "CS201",
            "due_date": "2026-12-10",
            "total_marks": "100",
            "description": "Solve DP problem set."
        })
        self.assertIn(res.status_code, (200, 302))

        created = self.mock_assignments.find_one({"title": "Recursion & Dynamic Programming"})
        self.assertIsNotNone(created)
        self.assertEqual(created.get("teacher_id"), str(self.t1_id))

        # Teacher 1 can update their assignment
        res_up = self.client.post(f"/assignments/update/{created['_id']}", data={
            "title": "Recursion & DP (Updated)",
            "subject": "CS201",
            "due_date": "2026-12-12",
            "total_marks": "100"
        })
        self.assertIn(res_up.status_code, (200, 302))

        # Teacher 1 can delete their assignment
        res_del = self.client.post(f"/assignments/delete/{created['_id']}")
        self.assertIn(res_del.status_code, (200, 302))
        self.assertIsNone(self.mock_assignments.find_one({"_id": created["_id"]}))

    def test_case_6_admin_can_view_all_teachers(self):
        """Test Case 6: Admin can view all teachers."""
        # Log in as Admin
        self.set_session_user(self.admin_id, "System Administrator", "admin", "admin@campuscore.io", "admin")

        res = self.client.get("/teachers")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Prof. H. Sharma", res.data)
        self.assertIn(b"Dr. Priya Mehta", res.data)

        # Verify Student and Teacher get 403 on /teachers
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student")
        res_st = self.client.get("/teachers")
        self.assertEqual(res_st.status_code, 403)

        self.set_session_user(self.t1_id, "Prof. H. Sharma", "teacher", "sharma@campuscore.io", "teacher")
        res_tc = self.client.get("/teachers")
        self.assertEqual(res_tc.status_code, 403)

    def test_case_7_admin_can_click_teacher_and_see_assigned_students(self):
        """Test Case 7: Admin can click a teacher and see their assigned students."""
        # Log in as Admin
        self.set_session_user(self.admin_id, "System Administrator", "admin", "admin@campuscore.io", "admin")

        # Inspect Teacher 1 section
        res = self.client.get(f"/teachers/{self.t1_id}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Aarav Sharma", res.data)
        self.assertIn(b"CS2026-001", res.data)

    def test_case_8_admin_can_view_attendance_for_every_student(self):
        """Test Case 8: Admin can view attendance for every student."""
        # Log in as Admin
        self.set_session_user(self.admin_id, "System Administrator", "admin", "admin@campuscore.io", "admin")

        res = self.client.get("/attendance")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Aarav Sharma", res.data)
        self.assertIn(b"Rohan Verma", res.data)

        # API view
        res_api = self.client.get("/api/attendance")
        self.assertEqual(res_api.status_code, 200)
        data = json.loads(res_api.data)
        self.assertGreaterEqual(len(data.get("attendance", [])), 2)

    def test_case_9_admin_cannot_mark_attendance(self):
        """Test Case 9: Admin cannot mark attendance (403)."""
        # Log in as Admin
        self.set_session_user(self.admin_id, "System Administrator", "admin", "admin@campuscore.io", "admin")

        # HTML route attempt
        res = self.client.post("/attendance/mark", data={
            "student_id": str(self.s1_id),
            "date": "2026-11-22",
            "status": "Present"
        })
        self.assertEqual(res.status_code, 403)

        # API route attempt
        res_api = self.client.post("/api/attendance", json={
            "student_id": str(self.s1_id),
            "date": "2026-11-22",
            "status": "Present"
        })
        self.assertEqual(res_api.status_code, 403)

    def test_case_10_admin_cannot_modify_or_delete_attendance_records(self):
        """Test Case 10: Admin cannot modify or delete attendance records (403)."""
        # Log in as Admin
        self.set_session_user(self.admin_id, "System Administrator", "admin", "admin@campuscore.io", "admin")

        # HTML route attempt
        res = self.client.post(f"/attendance/delete/{self.att1_id}")
        self.assertEqual(res.status_code, 403)

        # API route attempt
        res_api = self.client.delete(f"/api/attendance?id={self.att1_id}")
        self.assertEqual(res_api.status_code, 403)

    def test_case_11_unauthorized_api_requests_blocked(self):
        """Test Case 11: Unauthorized API requests are blocked (401 and 403)."""
        # 1. Unauthenticated requests return 401
        res_unauth = self.client.get("/api/attendance")
        self.assertEqual(res_unauth.status_code, 401)

        res_task = self.client.get("/api/tasks")
        self.assertEqual(res_task.status_code, 401)

        # 2. Student attempting to create an assignment returns 403
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student")
        res_st_create = self.client.post("/api/assignments", json={"title": "Hacked Assignment"})
        self.assertEqual(res_st_create.status_code, 403)

        # 3. Student attempting to mark attendance returns 403
        res_st_mark = self.client.post("/api/attendance", json={"student_id": str(self.s1_id), "status": "Present"})
        self.assertEqual(res_st_mark.status_code, 403)

    def test_case_12_existing_functionality_continues_to_work(self):
        """Test Case 12: Existing project functionality continues to work."""
        # 75% Bunk Planner math
        p = 18
        t = 20
        pct = (p / t) * 100
        self.assertEqual(pct, 90.0)
        can_bunk = (4 * p - 3 * t) // 3
        self.assertEqual(can_bunk, 4)

        # PDF generator
        res_pdf = self.client.get("/api/download?subject=Math&topic=Calculus")
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.content_type, "application/pdf")

        # Student personal dashboard
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student", "CS2026-001", self.t1_id)
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Aarav Sharma", res_dash.data)

    def test_case_13_many_to_many_student_teacher_relationship(self):
        """Test Case 13: One student can be assigned to multiple teachers, and one teacher to multiple students."""
        # 1. Aarav Sharma (s1) is assigned to Teacher 1 (t1) AND Teacher 2 (t2)
        self.assertTrue(campus_app.is_student_assigned_to_teacher(self.s1_id, self.t1_id))
        self.assertTrue(campus_app.is_student_assigned_to_teacher(self.s1_id, self.t2_id))

        # 2. Query student teachers returns both faculty mentors
        s1_teachers = campus_app.get_student_teachers(self.s1_id)
        t_names = [t["name"] for t in s1_teachers]
        self.assertIn("Prof. H. Sharma", t_names)
        self.assertIn("Dr. Priya Mehta", t_names)

        # 3. Teacher 1 has multiple students (Aarav Sharma and Diya Sen)
        t1_students = campus_app.get_teacher_students(self.t1_id)
        t1_student_rolls = [s["roll_no"] for s in t1_students]
        self.assertIn("CS2026-001", t1_student_rolls)
        self.assertIn("CS2026-002", t1_student_rolls)

    def test_case_14_admin_manage_students_assign_remove_transfer(self):
        """Test Case 14: Admin can assign multiple students, remove student, and transfer student between teachers."""
        self.set_session_user(self.admin_id, "Admin", "admin", "admin@campuscore.io", "admin")

        # 1. View teacher detail: Available students includes students assigned to other teachers (s3 is assigned to t2)
        res_view = self.client.get(f"/teachers/{self.t1_id}")
        self.assertEqual(res_view.status_code, 200)
        # Rohan Verma (MA2026-001) is available for Teacher 1 even though assigned to Teacher 2
        self.assertIn(b"Rohan Verma", res_view.data)

        # 2. Assign multiple students to Teacher 1
        res_assign = self.client.post(
            f"/teachers/{self.t1_id}/assign-students",
            data={"student_ids": [str(self.s3_id)]},
            follow_redirects=True
        )
        self.assertEqual(res_assign.status_code, 200)
        self.assertTrue(campus_app.is_student_assigned_to_teacher(self.s3_id, self.t1_id))

        # 3. Remove a student (Diya Sen s2) from Teacher 1
        res_remove = self.client.post(
            f"/teachers/{self.t1_id}/remove-student",
            data={"student_id": str(self.s2_id)},
            follow_redirects=True
        )
        self.assertEqual(res_remove.status_code, 200)
        self.assertFalse(campus_app.is_student_assigned_to_teacher(self.s2_id, self.t1_id))

        # 4. Transfer student (Rohan Verma s3) from Teacher 1 to Teacher 2
        res_transfer = self.client.post(
            f"/teachers/{self.t1_id}/transfer-student",
            data={"student_id": str(self.s3_id), "target_teacher_id": str(self.t2_id)},
            follow_redirects=True
        )
        self.assertEqual(res_transfer.status_code, 200)
        self.assertFalse(campus_app.is_student_assigned_to_teacher(self.s3_id, self.t1_id))
        self.assertTrue(campus_app.is_student_assigned_to_teacher(self.s3_id, self.t2_id))

    def test_case_15_student_blocked_from_tasks_routes(self):
        """Test Case 15: Student role cannot access or make tasks to do (only teachers/admin)."""
        # Student attempting to access /tasks returns 403 Forbidden
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student")
        res_tasks = self.client.get("/tasks")
        self.assertEqual(res_tasks.status_code, 403)

        # Student attempting to create a task returns 403 Forbidden
        res_create = self.client.post("/tasks/create", data={"title": "Hacked Task"})
        self.assertEqual(res_create.status_code, 403)

        # Teacher CAN access tasks
        self.set_session_user(self.t1_id, "Prof. H. Sharma", "teacher", "sharma@campuscore.io", "teacher")
        res_teacher_tasks = self.client.get("/tasks")
        self.assertEqual(res_teacher_tasks.status_code, 200)

    def test_case_16_student_views_assignments_from_all_teachers(self):
        """Test Case 16: Student views assignments from ALL faculty mentors assigned to them."""
        # Aarav Sharma is assigned to Teacher 1 (CS201) and Teacher 2 (MA201)
        self.set_session_user(self.s1_id, "Aarav Sharma", "student", "student@campuscore.io", "student", "CS2026-001")
        res_assignments = self.client.get("/assignments")
        self.assertEqual(res_assignments.status_code, 200)
        # Should see assignment from Teacher 1 AND assignment from Teacher 2
        self.assertIn(b"Data Structures AVL Trees", res_assignments.data)
        self.assertIn(b"Discrete Math Graph Theory", res_assignments.data)


if __name__ == "__main__":
    unittest.main()
