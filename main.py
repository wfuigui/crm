"""待办计时器 - KivyMD 版（安卓/桌面通用）"""

import sqlite3
import os
import math
from datetime import datetime, timedelta

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.list import (
    MDList, OneLineListItem, TwoLineListItem,
    OneLineAvatarIconListItem, IconLeftWidget,
    ThreeLineAvatarIconListItem,
)
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.widget import MDWidget
from kivymd.uix.behaviors import TouchBehavior
from kivymd.toast import toast

# ============================================================
# 1. 常量
# ============================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo_timer.db")

CAT_COLORS = [
    "#89b4fa", "#a6e3a1", "#f9e2af", "#fab387", "#f38ba8",
    "#cba6f7", "#94e2d5", "#f5c2e7", "#89dceb", "#eba0ac",
]

# ============================================================
# 2. Database（与 v1.py 共享）
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
        for col, default in [
            ("color", "'#89b4fa'"), ("sort_order", "0"),
        ]:
            try:
                self.conn.execute(f"ALTER TABLE categories ADD COLUMN {col} TEXT DEFAULT {default}")
            except sqlite3.OperationalError:
                pass
        try:
            self.conn.execute("ALTER TABLE todos ADD COLUMN sort_order INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def add_category(self, name, color=None):
        if color is None:
            cnt = self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            color = CAT_COLORS[cnt % len(CAT_COLORS)]
        cur = self.conn.cursor()
        cur.execute("INSERT INTO categories (name, color) VALUES (?, ?)", (name, color))
        self.conn.commit()
        return cur.lastrowid

    def get_categories(self):
        return self.conn.execute("SELECT id, name, color FROM categories ORDER BY id").fetchall()

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
        conds, params = [], []
        if category_id:
            conds.append("t.category_id = ?")
            params.append(category_id)
        if not show_completed:
            conds.append("t.is_completed = 0")
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY t.is_completed ASC, t.sort_order ASC, t.created_at DESC"
        return self.conn.execute(query, params).fetchall()

    def update_sort_order(self, tid, order):
        self.conn.execute("UPDATE todos SET sort_order=? WHERE id=?", (order, tid))
        self.conn.commit()

    def delete_todo(self, tid):
        self.conn.execute("DELETE FROM time_records WHERE todo_id=?", (tid,))
        self.conn.execute("DELETE FROM todos WHERE id=?", (tid,))
        self.conn.commit()

    def toggle_complete(self, tid):
        row = self.conn.execute("SELECT is_completed FROM todos WHERE id=?", (tid,)).fetchone()
        if row:
            new = 0 if row[0] else 1
            self.conn.execute(
                "UPDATE todos SET is_completed=?, completed_at=? WHERE id=?",
                (new, datetime.now().isoformat() if new else None, tid),
            )
            self.conn.commit()

    def add_seconds_to_todo(self, tid, seconds):
        self.conn.execute("UPDATE todos SET total_seconds = total_seconds + ? WHERE id=?", (seconds, tid))
        self.conn.commit()

    def start_record(self, tid):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO time_records (todo_id, start_time) VALUES (?, ?)",
                    (tid, datetime.now().isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def stop_record(self, record_id, duration_seconds):
        self.conn.execute(
            "UPDATE time_records SET end_time=?, duration_seconds=? WHERE id=?",
            (datetime.now().isoformat(), duration_seconds, record_id),
        )
        self.conn.commit()

    def delete_record(self, record_id):
        self.conn.execute("DELETE FROM time_records WHERE id=?", (record_id,))
        self.conn.commit()

    def get_overall_stats(self, start_date=None, end_date=None, category_id=None):
        ct, cr, pt, pr = [], [], [], []
        if start_date:
            ct.append("t.completed_at >= ?"); cr.append("r.start_time >= ?")
            pt.append(start_date); pr.append(start_date)
        if end_date:
            ct.append("t.completed_at <= ?"); cr.append("r.start_time <= ?")
            pt.append(end_date + " 23:59:59"); pr.append(end_date + " 23:59:59")
        if category_id:
            ct.append("t.category_id = ?"); cr.append("t.category_id = ?")
            pt.append(category_id); pr.append(category_id)
        wt = (" WHERE " + " AND ".join(ct)) if ct else ""
        wr = (" JOIN todos t ON r.todo_id = t.id WHERE " + " AND ".join(cr)) if cr else ""
        comp = self.conn.execute(f"SELECT COUNT(*) FROM todos t{wt}", pt).fetchone()[0] or 0
        total = self.conn.execute(f"SELECT COALESCE(SUM(r.duration_seconds),0) FROM time_records r{wr}", pr).fetchone()[0] or 0
        days = self.conn.execute(f"SELECT COUNT(DISTINCT DATE(r.start_time)) FROM time_records r{wr}", pr).fetchone()[0] or 1
        return comp, total, total // max(days, 1)

    def get_today_seconds(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.conn.execute(
            "SELECT COALESCE(SUM(duration_seconds),0) FROM time_records WHERE DATE(start_time)=?", (today,)
        ).fetchone()[0] or 0

    def get_today_records(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.conn.execute("""
            SELECT t.title, c.name, c.color, SUM(r.duration_seconds)
            FROM time_records r JOIN todos t ON r.todo_id=t.id
            LEFT JOIN categories c ON t.category_id=c.id
            WHERE DATE(r.start_time)=?
            GROUP BY r.todo_id ORDER BY SUM(r.duration_seconds) DESC
        """, (today,)).fetchall()

    def get_daily_stats(self, start_date=None, end_date=None, category_id=None):
        conds, params = [], []
        if start_date: conds.append("r.start_time >= ?"); params.append(start_date)
        if end_date: conds.append("r.start_time <= ?"); params.append(end_date + " 23:59:59")
        if category_id: conds.append("t.category_id = ?"); params.append(category_id)
        w = (" WHERE " + " AND ".join(conds)) if conds else ""
        return self.conn.execute(f"""
            SELECT DATE(r.start_time), COALESCE(SUM(r.duration_seconds),0)
            FROM time_records r JOIN todos t ON r.todo_id=t.id
            {w} GROUP BY DATE(r.start_time) ORDER BY DATE(r.start_time)
        """, params).fetchall()

    def get_category_stats(self, start_date=None, end_date=None):
        conds, params = [], []
        if start_date: conds.append("r.start_time >= ?"); params.append(start_date)
        if end_date: conds.append("r.start_time <= ?"); params.append(end_date + " 23:59:59")
        w = (" WHERE " + " AND ".join(conds)) if conds else ""
        return self.conn.execute(f"""
            SELECT COALESCE(c.name,'未分类'), COALESCE(c.color,'#6c7086'), SUM(r.duration_seconds)
            FROM time_records r JOIN todos t ON r.todo_id=t.id
            LEFT JOIN categories c ON t.category_id=c.id
            {w} GROUP BY t.category_id ORDER BY SUM(r.duration_seconds) DESC
        """, params).fetchall()

    def close(self):
        self.conn.close()


# ============================================================
# 3. 工具函数
# ============================================================

def fmt(s):
    s = max(s, 0)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

def fmt_short(s):
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m" if h > 0 else f"{m}m"


# ============================================================
# 4. KV 语言 UI
# ============================================================

KV = '''
<TodoItem>:
    size_hint_y: None
    height: dp(64)
    elevation: 1
    radius: [8]
    padding: dp(12)
    md_bg_color: app.theme_cls.bg_darkest
    on_release: app.open_timer(root.todo_data)
    MDBoxLayout:
        orientation: "horizontal"
        MDBoxLayout:
            size_hint_x: 0.05
            md_bg_color: root.cat_color if root.cat_color else [0,0,0,0]
            radius: [2]
        MDBoxLayout:
            orientation: "vertical"
            padding: [dp(8), 0, 0, 0]
            MDLabel:
                text: root.todo_title
                font_style: "Body1"
                theme_text_color: "Custom"
                text_color: 1,1,1,0.9 if not root.is_completed else 0.6
                shorten: True
                shorten_from: "right"
            MDLabel:
                text: root.cat_name if root.cat_name else ""
                font_style: "Caption"
                theme_text_color: "Custom"
                text_color: root.cat_color if root.cat_color else [0.6,0.6,0.6,1]
                size_hint_y: 0.4
        MDLabel:
            text: root.time_text
            font_style: "Body2"
            theme_text_color: "Custom"
            text_color: app.theme_cls.primary_color
            size_hint_x: 0.25
            halign: "right"

<TimerScreen>:
    name: "timer"
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: "计时中"
            left_action_items: [["arrow-left", lambda x: app.stop_and_back()]]
            elevation: 2
        MDBoxLayout:
            orientation: "vertical"
            adaptive_height: True
            padding: dp(20)
            MDLabel:
                id: task_label
                text: "选择待办开始计时"
                font_style: "H5"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1,1,1,0.7
            MDLabel:
                id: status_label
                text: ""
                font_style: "Body2"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 0.43, 0.81, 0.56
                size_hint_y: None
                height: dp(24)
        MDBoxLayout:
            orientation: "vertical"
            padding: dp(40)
            MDLabel:
                id: timer_label
                text: "00 : 00 : 00"
                font_style: "H3"
                halign: "center"
                theme_text_color: "Custom"
                text_color: 1,1,1,1
                font_name: "RobotoMono-Regular"
            MDProgressBar:
                id: progress
                value: 0
                color: app.theme_cls.primary_color
                size_hint_y: None
                height: dp(4)
        MDBoxLayout:
            orientation: "horizontal"
            adaptive_height: True
            padding: dp(20)
            spacing: dp(20)
            MDRaisedButton:
                id: start_btn
                text: "开始计时"
                on_release: root.toggle_timer()
                md_bg_color: 0.43, 0.81, 0.56
                size_hint_x: 0.5
            MDRaisedButton:
                id: stop_btn
                text: "停止并保存"
                on_release: root.stop_timer()
                md_bg_color: 0.88, 0.38, 0.44
                size_hint_x: 0.5
                disabled: True
        Widget:

<StatsScreen>:
    name: "stats"
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: "统计"
            elevation: 2
        MDScrollView:
            MDBoxLayout:
                orientation: "vertical"
                adaptive_height: True
                padding: dp(16)
                spacing: dp(12)
                # 概览卡片
                MDCard:
                    size_hint_y: None
                    height: dp(100)
                    radius: [12]
                    md_bg_color: app.theme_cls.bg_darkest
                    padding: dp(16)
                    MDBoxLayout:
                        orientation: "horizontal"
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                text: "总专注"
                                font_style: "Caption"
                                halign: "center"
                            MDLabel:
                                id: stat_total
                                text: "00:00:00"
                                font_style: "H6"
                                halign: "center"
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                text: "完成"
                                font_style: "Caption"
                                halign: "center"
                            MDLabel:
                                id: stat_completed
                                text: "0"
                                font_style: "H6"
                                halign: "center"
                        MDBoxLayout:
                            orientation: "vertical"
                            MDLabel:
                                text: "日均"
                                font_style: "Caption"
                                halign: "center"
                            MDLabel:
                                id: stat_daily
                                text: "00:00:00"
                                font_style: "H6"
                                halign: "center"
                # 今日专注
                MDCard:
                    size_hint_y: None
                    height: dp(100)
                    radius: [12]
                    md_bg_color: app.theme_cls.bg_darkest
                    padding: dp(16)
                    MDBoxLayout:
                        orientation: "vertical"
                        MDBoxLayout:
                            orientation: "horizontal"
                            MDLabel:
                                text: "今日专注"
                                font_style: "Subtitle1"
                            MDLabel:
                                id: today_val
                                text: "0h 0m"
                                font_style: "Subtitle1"
                                halign: "right"
                                theme_text_color: "Custom"
                                text_color: 0.43, 0.81, 0.56
                        MDProgressBar:
                            id: today_progress
                            value: 0
                            color: 0.43, 0.81, 0.56
                            size_hint_y: None
                            height: dp(6)
                # 今日记录
                MDCard:
                    size_hint_y: None
                    height: dp(40) + len(today_records_box.children) * dp(36)
                    radius: [12]
                    md_bg_color: app.theme_cls.bg_darkest
                    padding: dp(16)
                    MDBoxLayout:
                        id: today_records_box
                        orientation: "vertical"
                        adaptive_height: True
                        spacing: dp(4)
                # 分类分布
                MDCard:
                    size_hint_y: None
                    height: dp(40) + len(dist_box.children) * dp(30)
                    radius: [12]
                    md_bg_color: app.theme_cls.bg_darkest
                    padding: dp(16)
                    MDBoxLayout:
                        id: dist_box
                        orientation: "vertical"
                        adaptive_height: True
                        spacing: dp(6)
                        MDLabel:
                            text: "专注分布"
                            font_style: "Subtitle1"
                            size_hint_y: None
                            height: dp(30)
                Widget:

<TodoListScreen>:
    name: "todos"
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: "待办计时器"
            elevation: 2
            right_action_items: [["plus", lambda x: app.show_add_todo_dialog()]]
        MDBoxLayout:
            orientation: "horizontal"
            # 左侧分类栏
            MDBoxLayout:
                orientation: "vertical"
                size_hint_x: 0.28
                md_bg_color: 0.04, 0.04, 0.08
                padding: dp(8)
                MDLabel:
                    text: "分类"
                    font_style: "Subtitle2"
                    size_hint_y: None
                    height: dp(36)
                MDScrollView:
                    MDBoxLayout:
                        id: cat_box
                        orientation: "vertical"
                        adaptive_height: True
                        spacing: dp(4)
            # 右侧待办列表
            MDBoxLayout:
                orientation: "vertical"
                MDScrollView:
                    MDBoxLayout:
                        id: todo_box
                        orientation: "vertical"
                        adaptive_height: True
                        padding: dp(8)
                        spacing: dp(6)

MDBottomNavigation:
    panel_color: 0.04, 0.04, 0.08
    MDBottomNavigationItem:
        name: "todos"
        text: "待办"
        icon: "format-list-checks"
        TodoListScreen:
            id: todo_screen
    MDBottomNavigationItem:
        name: "stats"
        text: "统计"
        icon: "chart-bar"
        StatsScreen:
            id: stats_screen
'''


# ============================================================
# 5. 自定义组件
# ============================================================

class TodoItem(MDCard):
    todo_data = None
    todo_title = ""
    cat_name = ""
    cat_color = [0.6, 0.6, 0.6, 1]
    is_completed = False
    time_text = ""
    todo_id = 0


class TodoListScreen(MDScreen):
    active_cat_id = None
    _show_completed = True

    def on_enter(self):
        Clock.schedule_once(lambda dt: self.refresh(), 0.1)

    def refresh(self):
        self.refresh_cats()
        self.refresh_todos()

    def refresh_cats(self):
        box = self.ids.cat_box
        box.clear_widgets()
        app = MDApp.get_running_app()

        # "全部" 按钮
        btn = MDRaisedButton if self.active_cat_id is None else MDFlatButton
        all_btn = MDFlatButton(
            text="全部",
            size_hint_y=None,
            height=dp(36),
        )
        if self.active_cat_id is None:
            all_btn.md_bg_color = app.theme_cls.primary_color
        all_btn.bind(on_release=lambda x: self.select_cat(None))
        box.add_widget(all_btn)

        for cid, name, color in app.db.get_categories():
            b = MDFlatButton(
                text=name,
                size_hint_y=None,
                height=dp(36),
            )
            if self.active_cat_id == cid:
                b.md_bg_color = self._hex_to_rgba(color, 0.3)
            b.bind(on_release=lambda x, c=cid: self.select_cat(c))
            box.add_widget(b)

        # 管理分类按钮
        manage_btn = MDFlatButton(
            text="+ 管理分类",
            size_hint_y=None,
            height=dp(32),
            theme_text_color="Custom",
            text_color=[0.6, 0.6, 0.6, 1],
        )
        manage_btn.bind(on_release=lambda x: self.show_manage_cats())
        box.add_widget(manage_btn)

    def refresh_todos(self):
        box = self.ids.todo_box
        box.clear_widgets()
        app = MDApp.get_running_app()
        todos = app.db.get_todos(category_id=self.active_cat_id, show_completed=self._show_completed)

        if not todos:
            box.add_widget(MDLabel(
                text="暂无待办\n点击右上角 + 新建",
                halign="center",
                theme_text_color="Custom",
                text_color=[0.6, 0.6, 0.6, 1],
                size_hint_y=None,
                height=dp(100),
            ))
            return

        for todo in todos:
            tid, title, cat_id, cat_name, cat_color, is_completed, total_sec = todo
            item = TodoItem()
            item.todo_data = todo
            item.todo_id = tid
            item.todo_title = ("✓ " if is_completed else "") + title
            item.cat_name = cat_name or ""
            item.cat_color = self._hex_to_rgba(cat_color, 1) if cat_color else [0.6, 0.6, 0.6, 1]
            item.is_completed = bool(is_completed)
            item.time_text = fmt(total_sec)
            box.add_widget(item)

    def select_cat(self, cat_id):
        self.active_cat_id = cat_id
        self.refresh()

    def show_manage_cats(self):
        app = MDApp.get_running_app()
        cats = app.db.get_categories()
        content = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8), padding=dp(16))
        for cid, name, color in cats:
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            row.add_widget(MDLabel(text=name, size_hint_x=0.7))
            del_btn = MDIconButton(icon="delete", icon_color=[0.88, 0.38, 0.44, 1])
            del_btn.bind(on_release=lambda x, c=cid: self._delete_cat(c))
            row.add_widget(del_btn)
            content.add_widget(row)

        self._cat_dialog = MDDialog(
            title="管理分类",
            type="custom",
            content_cls=content,
            buttons=[MDFlatButton(text="关闭", on_release=lambda x: self._cat_dialog.dismiss())],
        )
        self._cat_dialog.open()

    def _delete_cat(self, cid):
        MDApp.get_running_app().db.delete_category(cid)
        self._cat_dialog.dismiss()
        self.refresh()

    @staticmethod
    def _hex_to_rgba(hex_str, alpha):
        h = hex_str.lstrip("#")
        r, g, b = int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255
        return [r, g, b, alpha]


class TimerScreen(MDScreen):
    current_todo = None
    running = False
    start_time = None
    elapsed = 0
    record_id = None

    def open_with_todo(self, todo):
        self.current_todo = todo
        self.elapsed = 0
        self.running = False
        self.record_id = None
        self.ids.task_label.text = todo[1]
        self.ids.timer_label.text = "00 : 00 : 00"
        self.ids.status_label.text = "准备开始"
        self.ids.status_label.text_color = [0.6, 0.6, 0.6, 1]
        self.ids.start_btn.text = "开始计时"
        self.ids.start_btn.md_bg_color = [0.43, 0.81, 0.56, 1]
        self.ids.start_btn.disabled = False
        self.ids.stop_btn.disabled = True
        self.ids.progress.value = 0

    def toggle_timer(self):
        if not self.running:
            self.start_timer()
        else:
            self.pause_timer()

    def start_timer(self):
        app = MDApp.get_running_app()
        self.running = True
        self.start_time = datetime.now()
        if not self.record_id:
            self.record_id = app.db.start_record(self.current_todo[0])
        self.ids.start_btn.text = "暂停"
        self.ids.start_btn.md_bg_color = [0.91, 0.76, 0.35, 1]
        self.ids.stop_btn.disabled = False
        self.ids.status_label.text = "专注中..."
        self.ids.status_label.text_color = [0.43, 0.81, 0.56, 1]
        Clock.schedule_interval(self.tick, 1)

    def pause_timer(self):
        self.running = False
        Clock.unschedule(self.tick)
        self.ids.start_btn.text = "继续计时"
        self.ids.start_btn.md_bg_color = [0.43, 0.81, 0.56, 1]
        self.ids.status_label.text = "已暂停"
        self.ids.status_label.text_color = [0.91, 0.76, 0.35, 1]

    def tick(self, dt):
        if not self.running:
            return False
        self.elapsed = int((datetime.now() - self.start_time).total_seconds())
        self.ids.timer_label.text = fmt(self.elapsed)
        self.ids.progress.value = (self.elapsed % 60) / 60 * 100
        return True

    def stop_timer(self):
        app = MDApp.get_running_app()
        if self.running:
            self.running = False
            Clock.unschedule(self.tick)
        if self.record_id and self.elapsed > 0:
            # 显示修改时间对话框
            self.show_confirm_dialog()
        else:
            self._cleanup_and_back()

    def show_confirm_dialog(self):
        content = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8), padding=dp(16))
        content.add_widget(MDLabel(text="本次专注时长", halign="center"))
        time_field = MDTextField(
            text=fmt(self.elapsed),
            halign="center",
            font_style="H5",
            size_hint_y=None,
            height=dp(60),
        )
        content.add_widget(time_field)
        content.add_widget(MDLabel(text="格式 HH:MM:SS，可修改", halign="center", font_style="Caption"))

        def save():
            try:
                parts = time_field.text.strip().split(":")
                if len(parts) == 3:
                    secs = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                elif len(parts) == 2:
                    secs = int(parts[0])*60 + int(parts[1])
                else:
                    secs = int(parts[0])
                secs = max(secs, 0)
            except ValueError:
                toast("时间格式不正确")
                return
            app = MDApp.get_running_app()
            app.db.stop_record(self.record_id, secs)
            app.db.add_seconds_to_todo(self.current_todo[0], secs)
            self._confirm_dialog.dismiss()
            self._cleanup_and_back()

        def discard():
            app = MDApp.get_running_app()
            app.db.delete_record(self.record_id)
            self._confirm_dialog.dismiss()
            self._cleanup_and_back()

        self._confirm_dialog = MDDialog(
            title="确认专注时间",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(text="保存", on_release=lambda x: save()),
                MDFlatButton(text="丢弃", on_release=lambda x: discard()),
            ],
        )
        self._confirm_dialog.open()

    def _cleanup_and_back(self):
        self.record_id = None
        self.elapsed = 0
        self.running = False
        app = MDApp.get_running_app()
        app.switch_to_todos()


class StatsScreen(MDScreen):
    def on_enter(self):
        Clock.schedule_once(lambda dt: self.refresh(), 0.1)

    def refresh(self):
        app = MDApp.get_running_app()
        comp, total, daily = app.db.get_overall_stats()
        self.ids.stat_total.text = fmt(total)
        self.ids.stat_completed.text = str(comp)
        self.ids.stat_daily.text = fmt(daily)

        today_sec = app.db.get_today_seconds()
        self.ids.today_val.text = fmt_short(today_sec)
        self.ids.today_progress.value = min(today_sec / 14400 * 100, 100)

        # 今日记录
        box = self.ids.today_records_box
        box.clear_widgets()
        records = app.db.get_today_records()
        if records:
            for title, cat_name, color, secs in records:
                row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
                row.add_widget(MDLabel(text=title, size_hint_x=0.5))
                if cat_name:
                    c = TodoListScreen._hex_to_rgba(color, 1) if color else [0.6, 0.6, 0.6, 1]
                    row.add_widget(MDLabel(text=cat_name, theme_text_color="Custom", text_color=c, size_hint_x=0.3))
                row.add_widget(MDLabel(text=fmt(secs), halign="right", size_hint_x=0.2))
                box.add_widget(row)
        else:
            box.add_widget(MDLabel(text="今天还没有专注记录", theme_text_color="Custom", text_color=[0.6,0.6,0.6,1]))

        # 分类分布
        dist = self.ids.dist_box
        # 保留标题
        for child in list(dist.children):
            if not isinstance(child, MDLabel):
                dist.remove_widget(child)
        cat_stats = app.db.get_category_stats()
        if cat_stats:
            max_sec = max(s for _, _, s in cat_stats) or 1
            for name, color, secs in cat_stats:
                row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
                c = TodoListScreen._hex_to_rgba(color, 1) if color else [0.6, 0.6, 0.6, 1]
                row.add_widget(MDLabel(text=name, theme_text_color="Custom", text_color=c, size_hint_x=0.3))
                row.add_widget(MDLabel(text=fmt_short(secs), halign="right", size_hint_x=0.3))
                row.add_widget(MDLabel(text=f"{secs/(max_sec)*100:.0f}%", halign="right", size_hint_x=0.2))
                dist.add_widget(row)


# ============================================================
# 6. App 主类
# ============================================================

class TodoTimerApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.db = Database()
        self.root = Builder.load_string(KV)
        # 绑定底部导航切换事件
        self.root.bind(on_tab_switch=self.on_tab_switch)
        return self.root

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if tab_text == "统计":
            stats = self.root.ids.stats_screen
            stats.refresh()

    def switch_to_todos(self):
        self.root.current = "todos"
        todo_screen = self.root.ids.todo_screen
        todo_screen.refresh()

    def open_timer(self, todo):
        timer = self.root.get_screen("timer") if self.root.has_screen("timer") else None
        if timer is None:
            timer = TimerScreen()
            self.root.add_widget(timer)
        timer.open_with_todo(todo)
        self.root.current = "timer"

    def show_add_todo_dialog(self):
        cats = self.db.get_categories()
        content = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(12), padding=dp(16))
        title_field = MDTextField(hint_text="待办名称", size_hint_y=None, height=dp(48))
        content.add_widget(title_field)

        # 分类选择
        cat_names = ["无分类"] + [c[1] for c in cats]
        cat_field = MDTextField(hint_text="选择分类", text="无分类", size_hint_y=None, height=dp(48), readonly=True)
        content.add_widget(cat_field)

        menu_items = [{"text": n, "on_release": lambda x=n: self._set_cat_field(cat_field, x)} for n in cat_names]
        cat_field.bind(on_focus=lambda *x: self._open_cat_menu(cat_field, menu_items) if cat_field.focus else None)

        # 新建分类按钮
        new_cat_btn = MDFlatButton(text="+ 新建分类", theme_text_color="Custom", text_color=[0.43, 0.81, 0.56, 1])
        new_cat_btn.bind(on_release=lambda x: self._add_inline_cat(cat_field))
        content.add_widget(new_cat_btn)

        def save():
            title = title_field.text.strip()
            if not title:
                toast("请输入待办名称")
                return
            cat_name = cat_field.text
            cat_id = next((c[0] for c in cats if c[1] == cat_name), None)
            self.db.add_todo(title, cat_id)
            self._add_dialog.dismiss()
            self.root.ids.todo_screen.refresh_todos()

        self._add_dialog = MDDialog(
            title="新建待办",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(text="保存", on_release=lambda x: save()),
                MDFlatButton(text="取消", on_release=lambda x: self._add_dialog.dismiss()),
            ],
        )
        self._add_dialog.open()

    _cat_menu = None
    def _open_cat_menu(self, field, items):
        if self._cat_menu:
            self._cat_menu.dismiss()
        self._cat_menu = MDDropdownMenu(caller=field, items=items, width_mult=4)
        self._cat_menu.open()

    def _set_cat_field(self, field, name):
        field.text = name
        if self._cat_menu:
            self._cat_menu.dismiss()

    def _add_inline_cat(self, cat_field):
        content = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(8), padding=dp(16))
        name_field = MDTextField(hint_text="分类名称", size_hint_y=None, height=dp(48))
        content.add_widget(name_field)

        def save_cat():
            name = name_field.text.strip()
            if not name:
                return
            try:
                self.db.add_category(name)
                cat_field.text = name
                self._new_cat_dialog.dismiss()
                toast(f"分类 '{name}' 已创建")
            except sqlite3.IntegrityError:
                toast("该分类已存在")

        self._new_cat_dialog = MDDialog(
            title="新建分类",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(text="确定", on_release=lambda x: save_cat()),
                MDFlatButton(text="取消", on_release=lambda x: self._new_cat_dialog.dismiss()),
            ],
        )
        self._new_cat_dialog.open()

    def stop_and_back(self):
        timer = None
        for child in self.root.children:
            if isinstance(child, TimerScreen):
                timer = child
                break
        if timer:
            if timer.running:
                timer.stop_timer()
            elif timer.record_id and timer.elapsed > 0:
                timer.show_confirm_dialog()
            else:
                self.switch_to_todos()
        else:
            self.switch_to_todos()

    def on_stop(self):
        self.db.close()


# ============================================================
# 7. 入口
# ============================================================

if __name__ == "__main__":
    TodoTimerApp().run()
