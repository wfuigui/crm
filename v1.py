"""待办计时器 - Todo Timer App"""

import sqlite3
import os
import customtkinter as ctk
from tkinter import Canvas, messagebox
from datetime import datetime, timedelta

# ============================================================
# 1. 常量与配置
# ============================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo_timer.db")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#0f0f1a",
    "sidebar": "#0a0a14",
    "card": "#1a1a2e",
    "card_hover": "#252540",
    "accent": "#6fa8dc",
    "green": "#6ecf8e",
    "red": "#e06070",
    "yellow": "#e8c85a",
    "peach": "#e8a060",
    "text": "#e8e8f0",
    "text_dim": "#9098b0",
    "blue": "#6fa8dc",
    "lavender": "#9aa0d0",
}

CAT_COLORS = ["#89b4fa", "#a6e3a1", "#f9e2af", "#fab387", "#f38ba8",
              "#cba6f7", "#94e2d5", "#f5c2e7", "#89dceb", "#eba0ac"]

FONTS = {
    "timer_big": ("Consolas", 64, "bold"),
    "title": ("Microsoft YaHei", 20, "bold"),
    "subtitle": ("Microsoft YaHei", 15, "bold"),
    "body": ("Microsoft YaHei", 13),
    "small": ("Microsoft YaHei", 11),
    "tiny": ("Microsoft YaHei", 10),
    "stat_big": ("Consolas", 36, "bold"),
}


# ============================================================
# 2. Database
# ============================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#89b4fa',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category_id INTEGER,
                is_completed INTEGER DEFAULT 0,
                total_seconds INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );
            CREATE TABLE IF NOT EXISTS time_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                todo_id INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0,
                FOREIGN KEY (todo_id) REFERENCES todos(id)
            );
        """)
        # 迁移：为旧数据库的 categories 表添加 color 列
        try:
            self.conn.execute("ALTER TABLE categories ADD COLUMN color TEXT DEFAULT '#89b4fa'")
        except sqlite3.OperationalError:
            pass
        # 迁移：为 todos 表添加 sort_order 列
        try:
            self.conn.execute("ALTER TABLE todos ADD COLUMN sort_order INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def add_category(self, name, color=None):
        if color is None:
            count = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            color = CAT_COLORS[count % len(CAT_COLORS)]
        cur = self.conn.cursor()
        cur.execute("INSERT INTO categories (name, color) VALUES (?, ?)", (name, color))
        self.conn.commit()
        return cur.lastrowid

    def get_categories(self):
        return self.conn.execute("SELECT id, name, color FROM categories ORDER BY id").fetchall()

    def update_category(self, cid, name):
        self.conn.execute("UPDATE categories SET name=? WHERE id=?", (name, cid))
        self.conn.commit()

    def delete_category(self, cid):
        self.conn.execute("UPDATE todos SET category_id=NULL WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        self.conn.commit()

    def add_todo(self, title, category_id=None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO todos (title, category_id) VALUES (?, ?)", (title, category_id))
        self.conn.commit()
        return cur.lastrowid

    def get_todos(self, category_id=None, show_completed=True):
        query = """
            SELECT t.id, t.title, t.category_id, c.name, c.color, t.is_completed, t.total_seconds
            FROM todos t LEFT JOIN categories c ON t.category_id = c.id
        """
        conditions, params = [], []
        if category_id:
            conditions.append("t.category_id = ?")
            params.append(category_id)
        if not show_completed:
            conditions.append("t.is_completed = 0")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY t.is_completed ASC, t.sort_order ASC, t.created_at DESC"
        return self.conn.execute(query, params).fetchall()

    def update_sort_order(self, tid, order):
        self.conn.execute("UPDATE todos SET sort_order=? WHERE id=?", (order, tid))
        self.conn.commit()

    def update_todo(self, tid, title=None, category_id=None):
        if title is not None:
            self.conn.execute("UPDATE todos SET title=? WHERE id=?", (title, tid))
        if category_id is not None:
            self.conn.execute("UPDATE todos SET category_id=? WHERE id=?", (category_id, tid))
        self.conn.commit()

    def delete_todo(self, tid):
        self.conn.execute("DELETE FROM time_records WHERE todo_id=?", (tid,))
        self.conn.execute("DELETE FROM todos WHERE id=?", (tid,))
        self.conn.commit()

    def toggle_complete(self, tid):
        row = self.conn.execute("SELECT is_completed FROM todos WHERE id=?", (tid,)).fetchone()
        if row:
            new_val = 0 if row[0] else 1
            completed_at = datetime.now().isoformat() if new_val else None
            self.conn.execute(
                "UPDATE todos SET is_completed=?, completed_at=? WHERE id=?",
                (new_val, completed_at, tid),
            )
            self.conn.commit()

    def add_seconds_to_todo(self, tid, seconds):
        self.conn.execute("UPDATE todos SET total_seconds = total_seconds + ? WHERE id=?", (seconds, tid))
        self.conn.commit()

    def start_record(self, tid):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO time_records (todo_id, start_time) VALUES (?, ?)",
            (tid, datetime.now().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def stop_record(self, record_id, duration_seconds):
        self.conn.execute(
            "UPDATE time_records SET end_time=?, duration_seconds=? WHERE id=?",
            (datetime.now().isoformat(), duration_seconds, record_id),
        )
        self.conn.commit()

    def get_overall_stats(self, start_date=None, end_date=None, category_id=None):
        conds_t, conds_r, p_t, p_r = [], [], [], []
        if start_date:
            conds_t.append("t.completed_at >= ?")
            conds_r.append("r.start_time >= ?")
            p_t.append(start_date)
            p_r.append(start_date)
        if end_date:
            conds_t.append("t.completed_at <= ?")
            conds_r.append("r.start_time <= ?")
            p_t.append(end_date + " 23:59:59")
            p_r.append(end_date + " 23:59:59")
        if category_id:
            conds_t.append("t.category_id = ?")
            conds_r.append("t.category_id = ?")
            p_t.append(category_id)
            p_r.append(category_id)

        wt = (" WHERE " + " AND ".join(conds_t)) if conds_t else ""
        wr = (" JOIN todos t ON r.todo_id = t.id WHERE " + " AND ".join(conds_r)) if conds_r else ""

        completed = self.conn.execute(f"SELECT COUNT(*) FROM todos t{wt}", p_t).fetchone()[0] or 0
        total = self.conn.execute(f"SELECT COALESCE(SUM(r.duration_seconds), 0) FROM time_records r{wr}", p_r).fetchone()[0] or 0
        days = self.conn.execute(f"SELECT COUNT(DISTINCT DATE(r.start_time)) FROM time_records r{wr}", p_r).fetchone()[0] or 1
        return completed, total, total // max(days, 1)

    def get_today_seconds(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM time_records WHERE DATE(start_time) = ?", (today,)
        ).fetchone()[0] or 0

    def get_today_records(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.conn.execute("""
            SELECT t.title, c.name, c.color, SUM(r.duration_seconds)
            FROM time_records r
            JOIN todos t ON r.todo_id = t.id
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE DATE(r.start_time) = ?
            GROUP BY r.todo_id ORDER BY SUM(r.duration_seconds) DESC
        """, (today,)).fetchall()

    def get_daily_stats(self, start_date=None, end_date=None, category_id=None):
        conds, params = [], []
        if start_date:
            conds.append("r.start_time >= ?")
            params.append(start_date)
        if end_date:
            conds.append("r.start_time <= ?")
            params.append(end_date + " 23:59:59")
        if category_id:
            conds.append("t.category_id = ?")
            params.append(category_id)
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        return self.conn.execute(f"""
            SELECT DATE(r.start_time), COALESCE(SUM(r.duration_seconds), 0)
            FROM time_records r JOIN todos t ON r.todo_id = t.id
            {where} GROUP BY DATE(r.start_time) ORDER BY DATE(r.start_time)
        """, params).fetchall()

    def get_category_stats(self, start_date=None, end_date=None):
        conds, params = [], []
        if start_date:
            conds.append("r.start_time >= ?")
            params.append(start_date)
        if end_date:
            conds.append("r.start_time <= ?")
            params.append(end_date + " 23:59:59")
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        return self.conn.execute(f"""
            SELECT COALESCE(c.name, '未分类'), COALESCE(c.color, '#6c7086'), SUM(r.duration_seconds)
            FROM time_records r
            JOIN todos t ON r.todo_id = t.id
            LEFT JOIN categories c ON t.category_id = c.id
            {where}
            GROUP BY t.category_id ORDER BY SUM(r.duration_seconds) DESC
        """, params).fetchall()

    def close(self):
        self.conn.close()


# ============================================================
# 3. 工具函数
# ============================================================

def fmt(s):
    s = max(s, 0)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def fmt_short(s):
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m" if h > 0 else f"{m}m"


def fmt_timer(s):
    return f"{s // 3600:02d} : {(s % 3600) // 60:02d} : {s % 60:02d}"


# ============================================================
# 4. 新建待办对话框（支持内联创建分类）
# ============================================================

class AddTodoDialog(ctk.CTkToplevel):
    def __init__(self, parent, db, on_save, todo=None):
        super().__init__(parent)
        self.db = db
        self.on_save = on_save
        self.todo = todo
        self.title("编辑待办" if todo else "新建待办")
        self.geometry("420x320")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.after(100, self.grab_set)

        # 待办名称
        ctk.CTkLabel(self, text="待办名称", font=FONTS["body"], text_color=COLORS["text_dim"]).pack(anchor="w", padx=30, pady=(25, 5))
        self.title_entry = ctk.CTkEntry(self, width=360, height=38, font=FONTS["body"],
                                         fg_color=COLORS["card"], border_color=COLORS["text_dim"],
                                         placeholder_text="输入待办名称...")
        self.title_entry.pack(padx=30, pady=(0, 15))
        if todo:
            self.title_entry.insert(0, todo[1])

        # 分类选择
        ctk.CTkLabel(self, text="选择分类", font=FONTS["body"], text_color=COLORS["text_dim"]).pack(anchor="w", padx=30, pady=(0, 5))

        cat_frame = ctk.CTkFrame(self, fg_color="transparent")
        cat_frame.pack(fill="x", padx=30, pady=(0, 20))

        self.categories = self.db.get_categories()
        cat_names = ["无分类"] + [c[1] for c in self.categories]
        self.cat_var = ctk.StringVar(value="无分类")

        if todo and todo[2]:
            for c in self.categories:
                if c[0] == todo[2]:
                    self.cat_var.set(c[1])
                    break

        self.cat_menu = ctk.CTkOptionMenu(
            cat_frame, variable=self.cat_var, values=cat_names, width=260, height=36,
            font=FONTS["body"], fg_color=COLORS["card"], button_color=COLORS["accent"],
            dropdown_fg_color=COLORS["card"],
        )
        self.cat_menu.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            cat_frame, text="+ 新分类", width=80, height=36, font=FONTS["small"],
            fg_color=COLORS["accent"], hover_color=COLORS["lavender"],
            command=self._add_category_inline,
        ).pack(side="left")

        # 按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="保存", width=140, height=40, font=FONTS["subtitle"],
                       fg_color=COLORS["green"], hover_color="#8cc896",
                       command=self._save).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="取消", width=100, height=40, font=FONTS["subtitle"],
                       fg_color=COLORS["card"], hover_color=COLORS["card_hover"],
                       command=self.destroy).pack(side="left", padx=10)

    def _add_category_inline(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("新建分类")
        dialog.geometry("300x140")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg"])
        dialog.after(100, dialog.grab_set)

        ctk.CTkLabel(dialog, text="分类名称", font=FONTS["body"], text_color=COLORS["text_dim"]).pack(pady=(20, 5))
        entry = ctk.CTkEntry(dialog, width=240, height=36, font=FONTS["body"],
                              fg_color=COLORS["card"], border_color=COLORS["text_dim"])
        entry.pack(pady=5)

        def save_cat():
            name = entry.get().strip()
            if not name:
                return
            try:
                cid = self.db.add_category(name)
                self.categories = self.db.get_categories()
                cat_names = ["无分类"] + [c[1] for c in self.categories]
                self.cat_menu.configure(values=cat_names)
                self.cat_var.set(name)
                dialog.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("错误", "该分类已存在", parent=dialog)

        ctk.CTkButton(dialog, text="确定", width=100, height=32, font=FONTS["body"],
                       fg_color=COLORS["green"], command=save_cat).pack(pady=10)

    def _save(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入待办名称", parent=self)
            return
        cat_name = self.cat_var.get()
        cat_id = next((c[0] for c in self.categories if c[1] == cat_name), None)
        try:
            if self.todo:
                self.db.update_todo(self.todo[0], title=title, category_id=cat_id)
            else:
                self.db.add_todo(title, cat_id)
            self.on_save()
            self.destroy()
        except Exception as e:
            messagebox.showerror("错误", str(e), parent=self)


# ============================================================
# 5. 计时器浮层
# ============================================================

class TimerOverlay(ctk.CTkFrame):
    def __init__(self, master, db, on_close):
        super().__init__(master, fg_color=COLORS["bg"])
        self.db = db
        self.on_close = on_close
        self.current_todo = None
        self.running = False
        self.start_time = None
        self.elapsed = 0
        self.record_id = None
        self._after_id = None
        self._build_ui()

    def _build_ui(self):
        # 顶部返回栏
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=50)
        top_bar.pack(fill="x", padx=20, pady=(15, 5))
        top_bar.pack_propagate(False)

        ctk.CTkButton(
            top_bar, text="< 返回", width=80, height=36, font=FONTS["body"],
            fg_color=COLORS["card"], hover_color=COLORS["card_hover"],
            command=self._go_back,
        ).pack(side="left")

        self.task_title_label = ctk.CTkLabel(top_bar, text="", font=FONTS["subtitle"], text_color=COLORS["text"])
        self.task_title_label.pack(side="left", padx=20)

        self.task_time_label = ctk.CTkLabel(top_bar, text="", font=FONTS["small"], text_color=COLORS["text_dim"])
        self.task_time_label.pack(side="right")

        # 计时器主体
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.pack(expand=True)

        self.status_label = ctk.CTkLabel(center, text="准备开始", font=FONTS["body"], text_color=COLORS["text_dim"])
        self.status_label.pack(pady=(0, 20))

        self.timer_label = ctk.CTkLabel(center, text="00 : 00 : 00", font=FONTS["timer_big"], text_color=COLORS["text"])
        self.timer_label.pack(pady=10)

        self.progress_bar = ctk.CTkProgressBar(center, width=400, height=6, corner_radius=3,
                                                fg_color=COLORS["card"], progress_color=COLORS["accent"])
        self.progress_bar.pack(pady=(20, 40))
        self.progress_bar.set(0)

        # 按钮
        btn_frame = ctk.CTkFrame(center, fg_color="transparent")
        btn_frame.pack()

        self.start_btn = ctk.CTkButton(
            btn_frame, text="开始计时", width=180, height=50, font=FONTS["subtitle"],
            fg_color=COLORS["green"], hover_color="#8cc896",
            corner_radius=25, command=self._toggle,
        )
        self.start_btn.pack(side="left", padx=15)

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="停止并保存", width=140, height=50, font=FONTS["subtitle"],
            fg_color=COLORS["red"], hover_color="#d97a8a",
            corner_radius=25, command=self._stop, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=15)

    def open_with_todo(self, todo):
        """todo: (id, title, cat_id, cat_name, cat_color, is_completed, total_seconds)"""
        self.current_todo = todo
        self.elapsed = 0
        self.running = False
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

        self.task_title_label.configure(text=todo[1])
        self.task_time_label.configure(text=f"累计: {fmt(todo[6])}")
        self.timer_label.configure(text="00 : 00 : 00", text_color=COLORS["text"])
        self.status_label.configure(text="准备开始", text_color=COLORS["text_dim"])
        self.start_btn.configure(text="开始计时", fg_color=COLORS["green"], hover_color="#8cc896", state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress_bar.set(0)

    def _toggle(self):
        if not self.running:
            self._start()
        else:
            self._pause()

    def _start(self):
        self.running = True
        self.start_time = datetime.now()
        if not self.record_id:
            self.record_id = self.db.start_record(self.current_todo[0])
        self.start_btn.configure(text="暂停", fg_color=COLORS["yellow"], hover_color="#d4c47e")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="专注中...", text_color=COLORS["green"])
        self._tick()

    def _pause(self):
        self.running = False
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.start_btn.configure(text="继续计时", fg_color=COLORS["green"], hover_color="#8cc896")
        self.status_label.configure(text="已暂停", text_color=COLORS["yellow"])

    def _stop(self):
        if self.running:
            self.running = False
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None

        if self.record_id and self.elapsed > 0:
            self._confirm_time()
        else:
            self.record_id = None
            self.elapsed = 0
            self.on_close()

    def _confirm_time(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("确认专注时间")
        dialog.geometry("340x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg"])
        dialog.after(100, dialog.grab_set)

        ctk.CTkLabel(dialog, text="本次专注时长", font=FONTS["body"],
                     text_color=COLORS["text_dim"]).pack(pady=(25, 5))

        time_entry = ctk.CTkEntry(dialog, width=200, height=44, font=FONTS["stat_big"],
                                   fg_color=COLORS["card"], border_color=COLORS["accent"],
                                   justify="center")
        time_entry.pack(pady=5)
        time_entry.insert(0, fmt(self.elapsed))
        time_entry.select_range(0, "end")

        ctk.CTkLabel(dialog, text="可修改后保存，格式 HH:MM:SS", font=FONTS["tiny"],
                     text_color=COLORS["text_dim"]).pack(pady=(2, 10))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)

        def save():
            text = time_entry.get().strip()
            try:
                parts = text.split(":")
                if len(parts) == 3:
                    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                    secs = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = int(parts[0]), int(parts[1])
                    secs = m * 60 + s
                else:
                    secs = int(text)
                if secs < 0:
                    secs = 0
            except ValueError:
                messagebox.showerror("错误", "时间格式不正确", parent=dialog)
                return

            self.db.stop_record(self.record_id, secs)
            self.db.add_seconds_to_todo(self.current_todo[0], secs)
            self.record_id = None
            self.elapsed = 0
            dialog.destroy()
            self.on_close()

        def discard():
            self.db.delete_record(self.record_id)
            self.record_id = None
            self.elapsed = 0
            dialog.destroy()
            self.on_close()

        ctk.CTkButton(btn_frame, text="保存", width=100, height=36, font=FONTS["body"],
                       fg_color=COLORS["green"], command=save).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="丢弃记录", width=80, height=36, font=FONTS["body"],
                       fg_color=COLORS["red"], command=discard).pack(side="left", padx=8)

    def _tick(self):
        if not self.running:
            return
        self.elapsed = int((datetime.now() - self.start_time).total_seconds())
        self.timer_label.configure(text=fmt_timer(self.elapsed))
        # 进度条：每秒变化，模拟脉搏效果
        pulse = (self.elapsed % 60) / 60
        self.progress_bar.set(pulse)
        self._after_id = self.after(1000, self._tick)

    def _go_back(self):
        if self.running:
            if not messagebox.askyesno("确认", "计时中，停止并保存后返回？"):
                return
            self._stop()
        elif self.record_id and self.elapsed > 0:
            self._confirm_time()
        else:
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None
            self.record_id = None
            self.elapsed = 0
            self.running = False
            self.on_close()


# ============================================================
# 6. 主视图：待办列表
# ============================================================

class TodoListView(ctk.CTkFrame):
    def __init__(self, master, db, on_timer_open):
        super().__init__(master, fg_color=COLORS["bg"])
        self.db = db
        self.on_timer_open = on_timer_open
        self.active_cat_id = None
        self._dragging = False
        self._dragged = False
        self._drag_row = None
        self._drag_todo = None
        self._build_ui()

    def _build_ui(self):
        # 左侧边栏
        self.sidebar = ctk.CTkFrame(self, width=160, fg_color=COLORS["sidebar"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        sidebar_title = ctk.CTkLabel(self.sidebar, text="分类", font=FONTS["subtitle"], text_color=COLORS["text"])
        sidebar_title.pack(pady=(20, 15), padx=15, anchor="w")

        self.cat_list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent",
                                                      scrollbar_button_color=COLORS["card"])
        self.cat_list_frame.pack(fill="both", expand=True, padx=5)

        # 右侧内容区
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True)

        # 顶部工具栏
        toolbar = ctk.CTkFrame(content, fg_color="transparent", height=50)
        toolbar.pack(fill="x", padx=20, pady=(15, 5))
        toolbar.pack_propagate(False)

        self.title_label = ctk.CTkLabel(toolbar, text="全部待办", font=FONTS["title"], text_color=COLORS["text"])
        self.title_label.pack(side="left")

        self.show_completed_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            toolbar, text="显示已完成", variable=self.show_completed_var,
            command=self.refresh_todos, font=FONTS["small"], text_color=COLORS["text_dim"],
            fg_color=COLORS["accent"], hover_color=COLORS["lavender"],
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            toolbar, text="+ 新建待办", width=110, height=36, font=FONTS["body"],
            fg_color=COLORS["green"], hover_color="#8cc896", corner_radius=18,
            command=self._add_todo,
        ).pack(side="right", padx=10)

        # 待办列表
        self.todo_list = ctk.CTkScrollableFrame(content, fg_color="transparent",
                                                  scrollbar_button_color=COLORS["card"])
        self.todo_list.pack(fill="both", expand=True, padx=15, pady=(5, 15))

    def refresh(self):
        self.refresh_sidebar()
        self.refresh_todos()

    def refresh_sidebar(self):
        for w in self.cat_list_frame.winfo_children():
            w.destroy()

        # "全部"按钮
        all_btn = ctk.CTkButton(
            self.cat_list_frame, text="全部待办", height=36, font=FONTS["body"],
            fg_color=COLORS["accent"] if self.active_cat_id is None else "transparent",
            hover_color=COLORS["card_hover"], text_color=COLORS["text"],
            anchor="w", corner_radius=8,
            command=lambda: self._select_cat(None),
        )
        all_btn.pack(fill="x", pady=2, padx=5)

        cats = self.db.get_categories()
        for cid, name, color in cats:
            is_active = self.active_cat_id == cid
            btn = ctk.CTkButton(
                self.cat_list_frame, text=name, height=36, font=FONTS["body"],
                fg_color=COLORS["card"] if is_active else "transparent",
                hover_color=COLORS["card_hover"], text_color=COLORS["text"],
                anchor="w", corner_radius=8,
                command=lambda c=cid: self._select_cat(c),
            )
            btn.pack(fill="x", pady=2, padx=5)

            # 彩色指示条
            indicator = ctk.CTkFrame(btn, width=4, height=20, fg_color=color, corner_radius=2)
            indicator.place(x=5, rely=0.5, anchor="w")

        # 管理分类按钮
        ctk.CTkButton(
            self.cat_list_frame, text="管理分类", height=30, font=FONTS["tiny"],
            fg_color="transparent", hover_color=COLORS["card"],
            text_color=COLORS["text_dim"], corner_radius=6,
            command=self._manage_categories,
        ).pack(fill="x", pady=(10, 2), padx=5)

    def refresh_todos(self):
        for w in self.todo_list.winfo_children():
            w.destroy()

        show = self.show_completed_var.get()
        todos = self.db.get_todos(category_id=self.active_cat_id, show_completed=show)

        if not todos:
            ctk.CTkLabel(self.todo_list, text="暂无待办\n点击右上角 + 新建",
                         font=FONTS["body"], text_color=COLORS["text_dim"],
                         justify="center").pack(pady=80)
            return

        for todo in todos:
            self._create_row(todo)

    def _create_row(self, todo):
        _tid, title, _cat_id, cat_name, cat_color, is_completed, total_sec = todo
        color = cat_color or COLORS["text_dim"]

        row = ctk.CTkFrame(self.todo_list, fg_color=COLORS["card"], corner_radius=10, height=64)
        row.todo_id = todo[0]
        row.pack(fill="x", pady=4)
        row.pack_propagate(False)

        # 拖拽手柄
        handle = ctk.CTkLabel(row, text="⋮⋮", font=FONTS["body"], text_color=COLORS["text_dim"], width=20)
        handle.pack(side="left", padx=(4, 0), pady=10)

        # 左侧彩色条
        bar = ctk.CTkFrame(row, width=5, fg_color=color, corner_radius=2)
        bar.pack(side="left", fill="y", padx=(4, 0), pady=8)

        # 分类标签
        if cat_name:
            tag = ctk.CTkLabel(row, text=cat_name, font=FONTS["tiny"], text_color=color,
                               fg_color=COLORS["sidebar"], corner_radius=4, width=50, height=22)
            tag.pack(side="left", padx=(10, 5), pady=10)

        # 标题
        title_color = COLORS["text_dim"] if is_completed else COLORS["text"]
        title_text = title
        if is_completed:
            title_text = title + "  ✓"
        ctk.CTkLabel(row, text=title_text, font=FONTS["body"],
                      text_color=title_color).pack(side="left", padx=10, pady=10, fill="x", expand=True)

        # 时长
        ctk.CTkLabel(row, text=fmt(total_sec), font=FONTS["small"],
                      text_color=COLORS["accent"]).pack(side="right", padx=15, pady=10)

        # 箭头
        ctk.CTkLabel(row, text=">", font=FONTS["subtitle"],
                      text_color=COLORS["text_dim"]).pack(side="right", pady=10)

        # 点击行 -> 打开计时器（短按）
        def on_click(event, t=todo):
            if not self._dragging and not t[5]:
                self.on_timer_open(t)

        # 长按检测
        long_press_id = [None]
        press_y = [0]

        def on_press(event):
            press_y[0] = event.y_root
            long_press_id[0] = self.todo_list.after(500, lambda: on_long_press(event, todo))

        def on_release(event):
            if long_press_id[0]:
                self.todo_list.after_cancel(long_press_id[0])
                long_press_id[0] = None
            if self._dragging:
                self._end_drag(event)
            elif not self._dragged:
                on_click(event)

        def on_motion(event):
            if long_press_id[0]:
                dy = abs(event.y_root - press_y[0])
                if dy > 8:
                    self.todo_list.after_cancel(long_press_id[0])
                    long_press_id[0] = None
                    self._start_drag(event, row)
            if self._dragging:
                self._do_drag(event, row)

        def on_long_press(event, t):
            long_press_id[0] = None
            self._show_todo_menu(event, t)

        row.bind("<ButtonPress-1>", on_press)
        row.bind("<ButtonRelease-1>", on_release)
        row.bind("<B1-Motion>", on_motion)
        for child in row.winfo_children():
            child.bind("<ButtonPress-1>", on_press)
            child.bind("<ButtonRelease-1>", on_release)
            child.bind("<B1-Motion>", on_motion)

    def _show_todo_menu(self, event, todo):
        from tkinter import Menu
        menu = Menu(self, tearoff=0, bg=COLORS["card"], fg=COLORS["text"],
                    activebackground=COLORS["accent"], activeforeground=COLORS["text"],
                    font=FONTS["small"])
        menu.add_command(label="删除", command=lambda: self._delete_todo(todo[0]))
        menu.add_command(label="标记完成", command=lambda: self._toggle_complete(todo[0]))
        menu.tk_popup(event.x_root, event.y_root)

    def _delete_todo(self, tid):
        if messagebox.askyesno("确认", "确定要删除这条待办吗？"):
            self.db.delete_todo(tid)
            self.refresh_todos()

    def _toggle_complete(self, tid):
        self.db.toggle_complete(tid)
        self.refresh_todos()

    def _start_drag(self, event, row):
        self._dragging = True
        self._dragged = False
        self._drag_row = row
        row.configure(fg_color=COLORS["accent"])

    def _do_drag(self, event, row):
        self._dragged = True
        mouse_y = event.y_root
        children = list(self.todo_list.winfo_children())
        row_idx = children.index(row)
        for i, child in enumerate(children):
            if child is row:
                continue
            child_y = child.winfo_rooty()
            child_h = child.winfo_height()
            if mouse_y < child_y + child_h // 2 and i < row_idx:
                row.pack_forget()
                row.pack(before=child, fill="x", pady=4)
                break
            elif mouse_y > child_y + child_h // 2 and i > row_idx:
                row.pack_forget()
                row.pack(after=child, fill="x", pady=4)
                break

    def _end_drag(self, event):
        if self._drag_row:
            self._drag_row.configure(fg_color=COLORS["card"])
        self._save_order()
        self._dragging = False
        self._drag_row = None

    def _save_order(self):
        children = self.todo_list.winfo_children()
        for idx, child in enumerate(children):
            tid = getattr(child, "todo_id", None)
            if tid is not None:
                self.db.update_sort_order(tid, idx)

    def _select_cat(self, cat_id):
        self.active_cat_id = cat_id
        if cat_id is None:
            self.title_label.configure(text="全部待办")
        else:
            cats = self.db.get_categories()
            name = next((c[1] for c in cats if c[0] == cat_id), "")
            self.title_label.configure(text=name)
        self.refresh()

    def _add_todo(self):
        AddTodoDialog(self, self.db, self.refresh_todos)

    def _manage_categories(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("管理分类")
        dialog.geometry("350x400")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg"])
        dialog.after(100, dialog.grab_set)

        ctk.CTkLabel(dialog, text="分类管理", font=FONTS["subtitle"], text_color=COLORS["text"]).pack(pady=(15, 10))

        list_frame = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        def refresh_list():
            for w in list_frame.winfo_children():
                w.destroy()
            cats = self.db.get_categories()
            for cid, name, color in cats:
                row = ctk.CTkFrame(list_frame, fg_color=COLORS["card"], corner_radius=8, height=40)
                row.pack(fill="x", pady=3)
                row.pack_propagate(False)

                ind = ctk.CTkFrame(row, width=4, fg_color=color, corner_radius=2)
                ind.pack(side="left", fill="y", padx=(8, 5), pady=6)

                ctk.CTkLabel(row, text=name, font=FONTS["body"], text_color=COLORS["text"]).pack(side="left", padx=5)

                ctk.CTkButton(
                    row, text="×", width=30, height=26, font=FONTS["body"],
                    fg_color=COLORS["red"], hover_color="#d97a8a",
                    command=lambda c=cid: (self.db.delete_category(c), refresh_list(), self.refresh_sidebar()),
                ).pack(side="right", padx=8)

        refresh_list()

        # 底部新建
        bottom = ctk.CTkFrame(dialog, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=10)
        new_entry = ctk.CTkEntry(bottom, width=200, height=34, font=FONTS["body"],
                                  fg_color=COLORS["card"], placeholder_text="新分类名称...")
        new_entry.pack(side="left", padx=(0, 10))

        def add_new():
            name = new_entry.get().strip()
            if not name:
                return
            try:
                self.db.add_category(name)
                new_entry.delete(0, "end")
                refresh_list()
                self.refresh()
            except sqlite3.IntegrityError:
                messagebox.showerror("错误", "该分类已存在", parent=dialog)

        ctk.CTkButton(bottom, text="添加", width=70, height=34, font=FONTS["body"],
                       fg_color=COLORS["green"], command=add_new).pack(side="left")


# ============================================================
# 7. 统计视图
# ============================================================

class StatsView(ctk.CTkFrame):
    def __init__(self, master, db):
        super().__init__(master, fg_color=COLORS["bg"])
        self.db = db
        self._build_ui()

    def _build_ui(self):
        # 滚动容器
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # 日期筛选
        filter_bar = ctk.CTkFrame(scroll, fg_color="transparent")
        filter_bar.pack(fill="x", padx=10, pady=(5, 15))

        for label, days in [("今天", 0), ("近7天", 7), ("近30天", 30), ("全部", None)]:
            ctk.CTkButton(
                filter_bar, text=label, width=70, height=32, font=FONTS["small"],
                fg_color=COLORS["card"], hover_color=COLORS["card_hover"],
                corner_radius=8, command=lambda d=days: self._set_range(d),
            ).pack(side="left", padx=4)

        ctk.CTkLabel(filter_bar, text="从", font=FONTS["small"], text_color=COLORS["text_dim"]).pack(side="left", padx=(15, 3))
        self.start_entry = ctk.CTkEntry(filter_bar, width=100, height=30, font=FONTS["small"],
                                         fg_color=COLORS["card"], placeholder_text="YYYY-MM-DD")
        self.start_entry.pack(side="left", padx=3)
        ctk.CTkLabel(filter_bar, text="至", font=FONTS["small"], text_color=COLORS["text_dim"]).pack(side="left", padx=3)
        self.end_entry = ctk.CTkEntry(filter_bar, width=100, height=30, font=FONTS["small"],
                                       fg_color=COLORS["card"], placeholder_text="YYYY-MM-DD")
        self.end_entry.pack(side="left", padx=3)

        ctk.CTkButton(filter_bar, text="查询", width=60, height=30, font=FONTS["small"],
                       fg_color=COLORS["accent"], command=self.refresh).pack(side="left", padx=8)

        # 概览卡片行
        cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_frame.pack(fill="x", padx=10, pady=(0, 15))

        self.card_labels = {}
        for label, key in [("总专注时长", "total"), ("完成次数", "completed"), ("日均时长", "daily")]:
            card = ctk.CTkFrame(cards_frame, fg_color=COLORS["card"], corner_radius=12, height=100)
            card.pack(side="left", fill="both", expand=True, padx=6)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=FONTS["small"], text_color=COLORS["text_dim"]).pack(pady=(15, 2))
            vl = ctk.CTkLabel(card, text="0", font=FONTS["stat_big"], text_color=COLORS["accent"])
            vl.pack()
            self.card_labels[key] = vl

        # 今日专注
        today_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=12)
        today_card.pack(fill="x", padx=10, pady=(0, 15))

        today_header = ctk.CTkFrame(today_card, fg_color="transparent")
        today_header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(today_header, text="今日专注", font=FONTS["subtitle"], text_color=COLORS["text"]).pack(side="left")
        self.today_val = ctk.CTkLabel(today_header, text="0h 0m", font=FONTS["subtitle"], text_color=COLORS["green"])
        self.today_val.pack(side="right")

        self.today_progress = ctk.CTkProgressBar(today_card, height=8, corner_radius=4,
                                                  fg_color=COLORS["sidebar"], progress_color=COLORS["green"])
        self.today_progress.pack(fill="x", padx=20, pady=(0, 5))
        self.today_progress.set(0)

        # 今日记录列表
        self.today_records_frame = ctk.CTkFrame(today_card, fg_color="transparent")
        self.today_records_frame.pack(fill="x", padx=20, pady=(0, 15))

        # 分类分布（横向条形图）
        dist_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=12)
        dist_card.pack(fill="x", padx=10, pady=(0, 15))
        ctk.CTkLabel(dist_card, text="专注分布", font=FONTS["subtitle"], text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(15, 10))
        dist_body = ctk.CTkFrame(dist_card, fg_color="transparent")
        dist_body.pack(fill="x", padx=20, pady=(0, 15))
        self.pie_canvas = Canvas(dist_body, bg=COLORS["card"], highlightthickness=0, height=220)
        self.pie_canvas.pack(side="left", fill="both", expand=True)
        self.legend_frame = ctk.CTkFrame(dist_body, fg_color="transparent")
        self.legend_frame.pack(side="right", padx=(10, 0))

        # 近7天柱状图
        chart_card = ctk.CTkFrame(scroll, fg_color=COLORS["card"], corner_radius=12)
        chart_card.pack(fill="x", padx=10, pady=(0, 15))
        ctk.CTkLabel(chart_card, text="近7天专注", font=FONTS["subtitle"], text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(15, 5))

        self.chart_canvas = Canvas(chart_card, bg=COLORS["card"], highlightthickness=0, height=220)
        self.chart_canvas.pack(fill="x", padx=20, pady=(0, 15))

    def _set_range(self, days):
        today = datetime.now()
        if days == 0:
            d = today.strftime("%Y-%m-%d")
            self.start_entry.delete(0, "end"); self.start_entry.insert(0, d)
            self.end_entry.delete(0, "end"); self.end_entry.insert(0, d)
        elif days is None:
            self.start_entry.delete(0, "end"); self.end_entry.delete(0, "end")
        else:
            self.start_entry.delete(0, "end"); self.start_entry.insert(0, (today - timedelta(days=days)).strftime("%Y-%m-%d"))
            self.end_entry.delete(0, "end"); self.end_entry.insert(0, today.strftime("%Y-%m-%d"))
        self.refresh()

    def refresh(self):
        start_date = self.start_entry.get().strip() or None
        end_date = self.end_entry.get().strip() or None
        for d in [start_date, end_date]:
            if d:
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("提示", "日期格式应为 YYYY-MM-DD")
                    return

        # 概览
        completed, total_sec, daily_avg = self.db.get_overall_stats(start_date, end_date)
        self.card_labels["total"].configure(text=fmt(total_sec))
        self.card_labels["completed"].configure(text=str(completed))
        self.card_labels["daily"].configure(text=fmt(daily_avg))

        # 今日
        today_sec = self.db.get_today_seconds()
        self.today_val.configure(text=fmt_short(today_sec))
        self.today_progress.set(min(today_sec / 14400, 1.0))

        # 今日记录
        for w in self.today_records_frame.winfo_children():
            w.destroy()
        records = self.db.get_today_records()
        if records:
            for title, cat_name, color, secs in records:
                row = ctk.CTkFrame(self.today_records_frame, fg_color=COLORS["sidebar"], corner_radius=6, height=32)
                row.pack(fill="x", pady=2)
                row.pack_propagate(False)
                ctk.CTkLabel(row, text=title, font=FONTS["small"], text_color=COLORS["text"]).pack(side="left", padx=10)
                if cat_name:
                    ctk.CTkLabel(row, text=cat_name, font=FONTS["tiny"], text_color=color or COLORS["text_dim"]).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=fmt(secs), font=FONTS["small"], text_color=COLORS["accent"]).pack(side="right", padx=10)
        else:
            ctk.CTkLabel(self.today_records_frame, text="今天还没有专注记录",
                         font=FONTS["small"], text_color=COLORS["text_dim"]).pack(pady=5)

        # 分类分布饼图
        for w in self.legend_frame.winfo_children():
            w.destroy()
        self.pie_canvas.delete("all")
        cat_stats = self.db.get_category_stats(start_date, end_date)
        if cat_stats:
            total_sec = sum(s for _, _, s in cat_stats) or 1
            self._draw_pie(cat_stats, total_sec)
            # 图例
            for name, color, secs in cat_stats:
                pct = secs / total_sec * 100
                row = ctk.CTkFrame(self.legend_frame, fg_color="transparent")
                row.pack(fill="x", anchor="w", pady=2)
                dot = ctk.CTkFrame(row, width=10, height=10, fg_color=color, corner_radius=5)
                dot.pack(side="left", padx=(0, 6))
                ctk.CTkLabel(row, text=f"{name}  {fmt(secs)} ({pct:.0f}%)",
                             font=FONTS["tiny"], text_color=COLORS["text"]).pack(side="left")
        else:
            self.pie_canvas.create_text(110, 110, text="暂无数据",
                                        fill=COLORS["text_dim"], font=FONTS["body"])

        # 柱状图
        self._draw_chart(start_date, end_date)

    def _draw_pie(self, cat_stats, total_sec):
        import math
        self.pie_canvas.delete("all")
        self.pie_canvas.update_idletasks()
        w = self.pie_canvas.winfo_width() or 300
        h = 240
        cx, cy = w // 2, h // 2
        r = min(cx, cy) - 40

        start_angle = 0
        for name, color, secs in cat_stats:
            extent = (secs / total_sec) * 360
            self.pie_canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=start_angle, extent=extent,
                fill=color, outline=COLORS["card"], width=2,
            )
            # 名称+时间标注在扇区外侧
            mid_angle = math.radians(start_angle + extent / 2)
            # 内侧时间
            if extent > 20:
                ir = r * 0.6
                ix = cx + ir * math.cos(mid_angle)
                iy = cy - ir * math.sin(mid_angle)
                self.pie_canvas.create_text(
                    ix, iy, text=fmt(secs),
                    fill="#ffffff", font=("Consolas", 8, "bold"),
                )
            # 外侧名称
            or_ = r + 18
            ox = cx + or_ * math.cos(mid_angle)
            oy = cy - or_ * math.sin(mid_angle)
            self.pie_canvas.create_text(
                ox, oy, text=name,
                fill=color, font=FONTS["tiny"],
            )
            start_angle += extent

    def _draw_chart(self, start_date, end_date):
        self.chart_canvas.delete("all")
        self.chart_canvas.update_idletasks()
        w = self.chart_canvas.winfo_width() or 600

        daily = self.db.get_daily_stats(start_date, end_date)
        # 取最近7天
        if len(daily) > 7:
            daily = daily[-7:]

        if not daily:
            self.chart_canvas.create_text(w // 2, 110, text="暂无数据",
                                          fill=COLORS["text_dim"], font=FONTS["body"])
            return

        h = 220
        ml, mr, mt, mb = 10, 10, 20, 35
        cw = w - ml - mr
        ch = h - mt - mb
        max_val = max(v for _, v in daily) or 1
        n = len(daily)
        gap = max(6, cw // (n * 3))
        bw = max(20, (cw - gap * (n + 1)) // n)

        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for i, (label, val) in enumerate(daily):
            x = ml + gap + i * (bw + gap)
            bh = (val / max_val) * ch if max_val > 0 else 0
            yt = mt + ch - bh
            yb = mt + ch

            # 渐变色柱子
            self.chart_canvas.create_rectangle(x, yt, x + bw, yb, fill=COLORS["accent"], outline="")

            if val > 0:
                self.chart_canvas.create_text(x + bw // 2, yt - 10, text=fmt_short(val),
                                              fill=COLORS["text"], font=FONTS["tiny"])

            # 日期标签
            try:
                dt = datetime.strptime(label, "%Y-%m-%d")
                day_label = weekdays[dt.weekday()]
            except Exception:
                day_label = label[-5:]
            self.chart_canvas.create_text(x + bw // 2, yb + 15, text=day_label,
                                          fill=COLORS["text_dim"], font=FONTS["tiny"])

        self.chart_canvas.create_line(ml, mt + ch, ml + cw, mt + ch, fill=COLORS["text_dim"], width=1)


# ============================================================
# 8. 主应用
# ============================================================

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("待办计时器")
        self.geometry("900x650")
        self.minsize(750, 500)
        self.db = Database()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.current_view = "todo"

        # 内容区（先放，占满空间）
        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.content.pack(side="top", fill="both", expand=True)

        # 底部导航栏（后放，固定在底部）
        self.nav_bar = ctk.CTkFrame(self, fg_color=COLORS["sidebar"], height=50, corner_radius=0)
        self.nav_bar.pack(side="bottom", fill="x")
        self.nav_bar.pack_propagate(False)

        self.nav_buttons = {}
        for label, key in [("待办", "todo"), ("统计", "stats")]:
            btn = ctk.CTkButton(
                self.nav_bar, text=label, width=120, height=36, font=FONTS["body"],
                fg_color="transparent", hover_color=COLORS["card"],
                corner_radius=8,
                command=lambda k=key: self._switch_view(k),
            )
            btn.pack(side="left", padx=20, pady=7)
            self.nav_buttons[key] = btn

        # 创建视图
        self.todo_view = TodoListView(self.content, self.db, self._open_timer)
        self.stats_view = StatsView(self.content, self.db)
        self.timer_overlay = TimerOverlay(self.content, self.db, self._close_timer)

        self._show_todo()
        self._update_nav()

    def _hide_all(self):
        for w in self.content.winfo_children():
            w.pack_forget()

    def _switch_view(self, key):
        if key == self.current_view:
            return
        self._hide_all()
        if key == "todo":
            self._show_todo()
        elif key == "stats":
            self._show_stats()
        self.current_view = key
        self._update_nav()

    def _show_todo(self):
        self.todo_view.pack(in_=self.content, fill="both", expand=True)
        self.todo_view.refresh()

    def _show_stats(self):
        self.stats_view.pack(in_=self.content, fill="both", expand=True)
        self.stats_view.refresh()

    def _update_nav(self):
        for key, btn in self.nav_buttons.items():
            if key == self.current_view:
                btn.configure(fg_color=COLORS["accent"], text_color=COLORS["bg"])
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text_dim"])

    def _open_timer(self, todo):
        self._hide_all()
        self.timer_overlay.pack(in_=self.content, fill="both", expand=True)
        self.timer_overlay.open_with_todo(todo)
        self.current_view = "timer"
        # 隐藏导航栏（计时全屏体验）
        self.nav_bar.pack_forget()

    def _close_timer(self):
        self._hide_all()
        self.todo_view.pack(in_=self.content, fill="both", expand=True)
        self.todo_view.refresh_todos()
        self.current_view = "todo"
        # 恢复导航栏
        self.nav_bar.pack(side="bottom", fill="x")
        self._update_nav()

    def _on_close(self):
        if self.timer_overlay.running:
            if not messagebox.askyesno("确认", "计时中，确定退出？"):
                return
            self.timer_overlay._stop()
        self.db.close()
        self.destroy()


# ============================================================
# 9. 入口
# ============================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()
