from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import auth as auth_router
from .routers import backup, children, classes, exams, scores, stats, subjects

# 首次启动自动建表
Base.metadata.create_all(bind=engine)


# 轻量迁移：给老库补新列/重建废弃列（SQLite 的 create_all 不会改已有表）
def _migrate():
    from sqlalchemy import select, text

    add_plan = {
        "children": {
            "enroll_year": "INTEGER",
            "class_name": "VARCHAR(50) DEFAULT ''",
            "student_no": "VARCHAR(50) DEFAULT ''",
            "first_enroll_year": "INTEGER",
        },
        "subjects": {"version": "VARCHAR(50) DEFAULT ''", "child_id": "INTEGER"},
        "classes": {
            "child_id": "INTEGER",  # 归属孩子
            "stage": "VARCHAR(10) DEFAULT '小学'",  # 小学/初中/高中
            "enroll_year": "INTEGER",  # 该阶段入学年份
            "school": "VARCHAR(100) DEFAULT ''",
            "student_no": "VARCHAR(50) DEFAULT ''",
        },
        "scores": {
            "tags": "VARCHAR(200) DEFAULT ''",
            "starred": "BOOLEAN DEFAULT 0",
            "high_score": "FLOAT",
            "high_scorer": "VARCHAR(50) DEFAULT ''",
        },
        "exams": {
            "tags": "VARCHAR(200) DEFAULT ''",
            "starred": "BOOLEAN DEFAULT 0",
            "high_score": "FLOAT",
            "high_scorer": "VARCHAR(50) DEFAULT ''",
            "year_rank": "INTEGER",  # 全科总排名（学年），手动录入
        },
    }
    with engine.begin() as conn:
        for table, cols in add_plan.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))

        # 孩子旧字段（入学年份/班级名/学校/学号）→ 自动生成一条班级记录（就读经历）。
        # 优先并入未挂孩子的同名旧班级（继承人数/竞争对手）；只迁移还没有班级记录的孩子，可重复执行
        ch_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(children)"))}
        if "first_enroll_year" in ch_cols:
            # 首次入学时间：历史孩子的 enroll_year 语义即小学入学年份
            conn.execute(text(
                "UPDATE children SET first_enroll_year = enroll_year "
                "WHERE first_enroll_year IS NULL AND enroll_year IS NOT NULL"
            ))
        # 清理孤儿班级记录（归属孩子已删除的）
        if "first_enroll_year" in ch_cols:
            conn.execute(text(
                "DELETE FROM classes WHERE child_id IS NOT NULL AND child_id NOT IN (SELECT id FROM children)"
            ))

        # 学期管理：units.term 改用短学期名（四上/初一上），按学科归属孩子的就读经历推算；
        # 学科学期集合存 subject_terms 表；全局 terms 表弃用
        # （units 的 sort_no/name 调整在下方事务外进行，避免被 units 重建逻辑影响）

        c_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(classes)"))}
        if {"child_id", "stage", "enroll_year"}.issubset(c_cols):
            from datetime import date as _date

            _today = _date.today()
            _start = _today.year if _today.month >= 8 else _today.year - 1
            conn.execute(text(
                "INSERT INTO classes (child_id, stage, enroll_year, school, name, size, student_no, rivals, note) "
                "SELECT c.id, "
                f"CASE WHEN {_start} - c.enroll_year + 1 > 6 THEN '初中' ELSE '小学' END, "
                "c.enroll_year, c.school, c.class_name, "
                "COALESCE(oc.size, 0), c.student_no, COALESCE(oc.rivals, ''), '' "
                "FROM children c "
                "LEFT JOIN classes oc ON oc.name = c.class_name AND oc.child_id IS NULL "
                "WHERE c.enroll_year IS NOT NULL AND c.class_name != '' "
                "AND NOT EXISTS (SELECT 1 FROM classes WHERE child_id = c.id)"
            ))

        # subjects：去掉 sort/default_total（旧列 NOT NULL 无默认值，会卡住新插入）
        s_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(subjects)"))}
        if s_cols and "sort" in s_cols:
            conn.execute(text(
                "CREATE TABLE subjects_new (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(50) NOT NULL, color VARCHAR(20) NOT NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "INSERT INTO subjects_new (id, name, color, created_at) "
                "SELECT id, name, color, created_at FROM subjects"
            ))
            conn.execute(text("DROP TABLE subjects"))
            conn.execute(text("ALTER TABLE subjects_new RENAME TO subjects"))

        # units：去掉 sort，补 term（NULL=不限学期）
        u_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(units)"))}
        if u_cols and "sort" in u_cols:
            term_expr = "term" if "term" in u_cols else "NULL"
            conn.execute(text(
                "CREATE TABLE units_new (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "subject_id INTEGER NOT NULL, name VARCHAR(50) NOT NULL, term VARCHAR(50))"
            ))
            conn.execute(text(
                f"INSERT INTO units_new (id, subject_id, name, term) "
                f"SELECT id, subject_id, name, {term_expr} FROM units"
            ))
            conn.execute(text("DROP TABLE units"))
            conn.execute(text("ALTER TABLE units_new RENAME TO units"))
        elif u_cols and "term" not in u_cols:
            conn.execute(text("ALTER TABLE units ADD COLUMN term VARCHAR(50)"))

        # 学期叫法统一：上学期→第一学期，下学期→第二学期
        for table in ("scores", "exams", "units"):
            t_cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if t_cols and "term" in t_cols:
                conn.execute(text(f"UPDATE {table} SET term = REPLACE(term, '上学期', '第一学期') WHERE term LIKE '%上学期%'"))
                conn.execute(text(f"UPDATE {table} SET term = REPLACE(term, '下学期', '第二学期') WHERE term LIKE '%下学期%'"))

        # 叫法再统一：第一学期→第1学期，第二学期→第2学期
        for table in ("scores", "exams"):
            t_cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if t_cols and "term" in t_cols:
                conn.execute(text(
                    f"UPDATE {table} SET term = "
                    f"REPLACE(REPLACE(term, '第一学期', '第1学期'), '第二学期', '第2学期') "
                    f"WHERE term LIKE '%学期'"
                ))

        # 学期按日期重算：第一学期=8~次年1月，第二学期=2~7月（1月的期末属第一学期）
        term_expr = (
            "(CASE WHEN CAST(substr({t}.date,6,2) AS INT) >= 8 "
            "THEN substr({t}.date,1,4) || '-' || (CAST(substr({t}.date,1,4) AS INT) + 1) || ' 第1学期' "
            "WHEN CAST(substr({t}.date,6,2) AS INT) <= 1 "
            "THEN (CAST(substr({t}.date,1,4) AS INT) - 1) || '-' || substr({t}.date,1,4) || ' 第1学期' "
            "ELSE (CAST(substr({t}.date,1,4) AS INT) - 1) || '-' || substr({t}.date,1,4) || ' 第2学期' END)"
        )
        conn.execute(text("UPDATE exams SET term = " + term_expr.format(t="exams")))
        # 挂场次的成绩跟随场次学期
        conn.execute(text("UPDATE scores SET term = e.term FROM exams e WHERE scores.exam_id = e.id"))
        # 独立成绩按自身日期重算
        conn.execute(text("UPDATE scores SET term = " + term_expr.format(t="scores") + " WHERE exam_id IS NULL"))

        # 类型更名：期中测试 → 期中考试（考试类型已精简为 单元测试/期中考试/期末考试）
        for table in ("scores", "exams"):
            t_cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if t_cols and "type" in t_cols:
                conn.execute(text(f"UPDATE {table} SET type = '期中考试' WHERE type = '期中测试'"))

        # 年级修正：有入学年份的孩子，年级一律按记录日期推算（当时读几年级）
        # SQLite 无两参 min/max，用 CASE + max/min 函数（多参数版可用）
        gexpr = (
            "max(1, min(9, (CASE WHEN CAST(substr({t}.date,6,2) AS INT) >= 8 "
            "THEN CAST(substr({t}.date,1,4) AS INT) ELSE CAST(substr({t}.date,1,4) AS INT) - 1 END) "
            "- c.enroll_year + 1))"
        )
        conn.execute(text(
            "UPDATE exams SET grade = " + gexpr.format(t="exams") +
            " FROM children c WHERE c.id = exams.child_id AND c.enroll_year IS NOT NULL"
        ))
        # 挂场次的成绩跟随场次年级
        conn.execute(text("UPDATE scores SET grade = e.grade FROM exams e WHERE scores.exam_id = e.id"))
        # 独立成绩按自身日期推算
        conn.execute(text(
            "UPDATE scores SET grade = " + gexpr.format(t="scores") +
            " FROM children c WHERE c.id = scores.child_id AND c.enroll_year IS NOT NULL AND scores.exam_id IS NULL"
        ))

        # 成绩↔单元 改多对多：旧的单值 unit_id 迁到 score_units 关联表。
        # unit_id 带 FK 约束，SQLite 不允许直接 DROP 该列，需重建 scores 表
        s_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(scores)"))}
        if s_cols and "unit_id" in s_cols:
            conn.execute(text(
                "INSERT OR IGNORE INTO score_units (score_id, unit_id) "
                "SELECT id, unit_id FROM scores WHERE unit_id IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE TABLE scores_new ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "child_id INTEGER NOT NULL REFERENCES children (id), "
                "subject_id INTEGER NOT NULL REFERENCES subjects (id), "
                "exam_id INTEGER REFERENCES exams (id), "
                "date DATE NOT NULL, grade INTEGER NOT NULL, term VARCHAR(50) NOT NULL, "
                "type VARCHAR(50) NOT NULL, regular_score FLOAT NOT NULL, regular_total FLOAT NOT NULL, "
                "bonus_score FLOAT, bonus_total FLOAT, grade_rank INTEGER, class_rank INTEGER, class_size INTEGER, "
                "note VARCHAR(500) NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "INSERT INTO scores_new (id, child_id, subject_id, exam_id, date, grade, term, type, "
                "regular_score, regular_total, bonus_score, bonus_total, grade_rank, class_rank, class_size, note, created_at) "
                "SELECT id, child_id, subject_id, exam_id, date, grade, term, type, "
                "regular_score, regular_total, bonus_score, bonus_total, grade_rank, class_rank, class_size, note, created_at "
                "FROM scores"
            ))
            conn.execute(text("DROP TABLE scores"))
            conn.execute(text("ALTER TABLE scores_new RENAME TO scores"))

    # 事务提交后（units 等表结构已定型）：
    with engine.begin() as conn:
        # units 补 sort_no 列并按学科内 id 顺序初始化单元序号
        u_cols2 = {row[1] for row in conn.execute(text("PRAGMA table_info(units)"))}
        if u_cols2 and "sort_no" not in u_cols2:
            conn.execute(text("ALTER TABLE units ADD COLUMN sort_no INTEGER DEFAULT 0"))
        # 序号重算在下方 Python 步骤进行（需在长学期名转换之后，按"学科+学期"分组编号）
        # 自动生成的名称"第N单元"清空（新结构中名称由用户录入，序号单独一列）
        conn.execute(text("UPDATE units SET name = '' WHERE name GLOB '第[0-9]单元' OR name GLOB '第[0-9][0-9]单元'"))

    # units.term 长学期名 → 短学期名（四上/初一上），按学科归属孩子的就读经历推算
    from sqlalchemy.orm import Session as _Session

    from .models import SchoolClass, Subject, Unit
    from .term import short_term_from_long

    with _Session(bind=engine) as ses:
        units = ses.scalars(select(Unit).where(Unit.term.like("%学期"))).all()
        for u in units:
            subject = ses.get(Subject, u.subject_id)
            if not subject or not subject.child_id:
                continue
            classes = ses.scalars(
                select(SchoolClass).where(SchoolClass.child_id == subject.child_id)
            ).all()
            short = short_term_from_long(classes, u.term)
            if short:
                u.term = short
        ses.commit()

        # 序号按"学科+学期"分组重排，每个学期都从第1单元开始
        from collections import defaultdict

        all_units = ses.scalars(select(Unit).order_by(Unit.subject_id, Unit.id)).all()
        groups = defaultdict(list)
        for u in all_units:
            groups[(u.subject_id, u.term)].append(u)
        for us in groups.values():
            for i, u in enumerate(us, 1):
                u.sort_no = i
        ses.commit()

    # 学科学期集合初始化：收集该学科单元用到的学期；全局 terms 表弃用删除
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO subject_terms (subject_id, term) "
            "SELECT DISTINCT subject_id, term FROM units WHERE term IS NOT NULL AND term != ''"
        ))
        # 去重（历史无唯一约束可能重复插入）并补唯一索引，保证一个学科一个学期只一条
        conn.execute(text(
            "DELETE FROM subject_terms WHERE id NOT IN "
            "(SELECT MIN(id) FROM subject_terms GROUP BY subject_id, term)"
        ))
        # 清理历史长学期名残留（如"2026-2027 第一学期"，单元已换算为短名）
        conn.execute(text("DELETE FROM subject_terms WHERE term LIKE '%学期'"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_terms ON subject_terms (subject_id, term)"
        ))
        conn.execute(text("DROP TABLE IF EXISTS terms"))


_migrate()

app = FastAPI(title="学生成绩助手", version="0.1.0")

# 开发模式下前端 vite 跨域用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api")
app.include_router(children.router, prefix="/api")
app.include_router(classes.router, prefix="/api")
app.include_router(subjects.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(scores.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(backup.router, prefix="/api")

# 成绩图片目录（不存在则创建），通过 /uploads/<文件名> 访问
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 生产模式：服务前端打包产物
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # index.html 不缓存：发版后浏览器必须拿到新 hash 的资源引用；
        # /assets 下带 hash 的文件可以长期缓存
        file = STATIC_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
