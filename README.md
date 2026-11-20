# CAMPUSCORE 🎓 &bull; Student Academic Management & Faculty Attendance Portal

CAMPUSCORE is a full-stack, web-based platform designed specifically for school and college students following the **CBSE** and university curriculum, paired with an institutional faculty and course allocation system.

---

## 🎨 Design System: Dark & Light Mode Palettes

CAMPUSCORE includes full support for both Dark Mode and Light Mode, with a zero-flicker instantaneous theme loader, interactive ☀️ / 🌙 toggle in the navigation header, and persistence in `localStorage`.

### 🌑 Dark Mode Palette (Default)
| Variable | Token Name | Hex Code | HSL / Usage |
| :--- | :--- | :--- | :--- |
| `--ink-black` | Ink Black | `#0e131fff` | `hsla(222, 38%, 9%, 1)` &bull; Canvas & dark background |
| `--twilight-indigo` | Twilight Indigo | `#38405fff` | `hsla(228, 26%, 30%, 1)` &bull; Borders & structural panels |
| `--vintage-grape` | Vintage Grape | `#59546cff` | `hsla(252, 13%, 38%, 1)` &bull; Muted accents & dividers |
| `--cool-steel` | Cool Steel | `#8b939cff` | `hsla(212, 8%, 58%, 1)` &bull; Secondary text & icons |
| `--strawberry-red` | Strawberry Red | `#ff0035ff` | `hsla(348, 100%, 50%, 1)` &bull; Primary CTA, highlights, active pills |

* **Dark Gradient:** `linear-gradient(135deg, #0e131fff, #38405fff, #59546cff, #8b939cff, #ff0035ff)`

### ☀️ Light Mode Palette
| Variable | Token Name | Hex Code | HSL / Usage |
| :--- | :--- | :--- | :--- |
| `--wheat` | Wheat | `#f5e0b7ff` | `hsla(40, 76%, 84%, 1)` &bull; Soft canvas tint & warm card surfaces |
| `--soft-fawn` | Soft Fawn | `#d6ba73ff` | `hsla(43, 55%, 65%, 1)` &bull; Warm gold accent, borders, active focus |
| `--muted-teal` | Muted Teal | `#8bbf9fff` | `hsla(143, 29%, 65%, 1)` &bull; Primary buttons & badges |
| `--silver` | Silver | `#bab6b5ff` | `hsla(12, 3%, 72%, 1)` &bull; Crisp dividers, borders & scrollbars |
| `--thistle` | Thistle | `#d9bfd2ff` | `hsla(316, 25%, 80%, 1)` &bull; Pastel badge backgrounds & accents |

* **Light Gradient:** `linear-gradient(135deg, #f5e0b7ff, #d6ba73ff, #8bbf9fff, #bab6b5ff, #d9bfd2ff)`

---

## 💻 Tech Stack
- **Backend:** Python 3.12, Flask 3.0.3 (Jinja2 Templates & Headless REST API)
- **Database:** MongoDB **Atlas** (pymongo 4.8.0, dnspython)
- **Frontend / Styling:** Custom CSS with CSS variables, Tailwind CSS, Lucide Icons, Marked.js (Markdown), KaTeX (LaTeX math)
- **No External AI APIs Required:** All AI dependencies, badges, and external LLM calls have been stripped out cleanly in favor of robust, self-contained study notes and curriculum repositories.

---

## ✨ Features

### 1. 👨‍🏫 Real Faculty Subject & Course Allocation (Admin + Teacher System)
- **Faculty Management Portal (`/teachers`):**
  - Institutional Admin can review all registered faculty members.
  - One-click modal to **assign subjects/courses** to any teacher using interactive course checkboxes.
  - Ability to register new faculty members with immediate initial course assignments.
- **Role-Aware Class Attendance (`/attendance?mode=roster`):**
  - **No more empty `-- Choose Course --` dropdown!** Teachers automatically see only the courses assigned to them by the Admin.
  - If a teacher has not yet been assigned any courses, an informative alert box directs them to contact the Admin.
  - Automatic security check preventing teachers from grading courses outside their assignment.
  - Admins retain access to all courses across all departments.

### 2. 📅 Daily Attendance & 75% Bunk Planner
- **Personal Daily Log:** Mark attendance for specific subjects (*Present*, *Absent*, or *Late / Half Day*).
- **75% Attendance Safety Calculator:**
  - When attendance $\ge 75\%$: Calculates exactly how many classes you can **safely bunk** while staying eligible for exam admit cards.
  - When attendance $< 75\%$: Calculates the exact number of **consecutive classes** you must attend to recover to 75%.
- **Consecutive Day Streak (🔥):** Streak habit counter.
- **Monthly Filter & Calendar:** View attendance statistics per month, year, and subject.

### 3. 📝 Study Notes & Lecture Materials
- **Markdown & LaTeX Equations:** Rich note creation supporting Markdown formatting and math formulas.
- **Search & Filter:** Live text search by title, keyword, or tag with subject dropdown filtering.
- **Full-Screen Reader:** Modal reading view with rendered Markdown and KaTeX math.
- **Export & Print:** 1-click download as Markdown (`.md`) or formatted print view for PDF export.

### 4. ✅ Task & Assignment Management
- **Priority Matrix:** High (🔴), Medium (🟡), and Low (🟢) priorities.
- **Status Lifecycle:** *Pending* &rarr; *In Progress* &rarr; *Completed*.
- **Quick Checkbox:** 1-click completion toggle with visual strike-through.
- **Due Date Tracking:** Due date picker with calendar badge.

### 5. 📘 Enrolled Subjects & Custom Icons
- Add custom subjects with personalized emojis (`📐`, `🧪`, `💻`, `⚡`, `🌍`, `🧬`, `📈`, `📚`).
- Direct subject-level analytics tracking linked notes, tasks, and attendance percentage.

### 6. 📢 Campus Bulletin Board & Notices
- Filter circulars by category: *Exams*, *General*, *Urgent*, *Events*.
- Faculty/Admin publishing and deletion controls.

### 7. 🔌 Complete Headless REST API Endpoints
- `POST /api/auth?action=register` & `POST /api/auth?action=login`
- `GET|POST|PUT|DELETE /api/tasks` & `GET /api/tasks?action=stats`
- `GET|POST|DELETE /api/attendance` & `GET /api/attendance?action=stats`
- `GET|POST|DELETE /api/notes`
- `GET|POST|DELETE /api/subjects`
- `GET /api/download` (Generates compliant PDF documents)

---

## 🔑 Demo Logins

| Role | Username | Password | Access Capabilities |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | Full access: Faculty course assignments, student enrollment, course catalog, bulletin board |
| **Teacher** | `teacher` | `teacher123` | Class attendance roster for assigned courses (`CS201`, `CS301`), notices |
| **Student** | `student` | `student123` | Personal 75% Bunk Planner, tasks, study notes, curriculum subjects |

---

## 🚀 Quick Start Guide

### 1. Activate Virtual Environment
```powershell
.\venv\Scripts\activate
```

### 2. Verify `.env` Configuration
In `campuscore/.env`:
```env
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.ygsitkx.mongodb.net/?retryWrites=true&w=majority
DB_NAME=campuscore
SECRET_KEY=campuscore_secret_key_2026
```

### 3. Run Unit Tests
```powershell
.\venv\Scripts\python.exe campuscore\test_app.py
```

### 4. Start the Application
```powershell
cd campuscore
..\venv\Scripts\python.exe app.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser.
