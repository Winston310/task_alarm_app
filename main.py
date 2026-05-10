import json
import os
import platform
import uuid
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button

try:
    from plyer import notification
except Exception:
    notification = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
KV_FILE = os.path.join(APP_DIR, "alarm_modern_visible.kv")
ALARM_SOUND = os.path.join(APP_DIR, "assets", "alarm.wav")


class MainScreen(BoxLayout):
    pass


class AlarmRow(BoxLayout):
    alarm_id = StringProperty("")
    title = StringProperty("")
    time_text = StringProperty("")
    task_text = StringProperty("")
    active = BooleanProperty(True)

    def toggle_active(self, value):
        app = App.get_running_app()
        app.set_alarm_active(self.alarm_id, value)

    def delete_alarm(self):
        app = App.get_running_app()
        app.delete_alarm(self.alarm_id)


class AddAlarmPopup(Popup):
    pass


class RingPopup(Popup):
    def stop_alarm(self):
        app = App.get_running_app()
        app.stop_alarm()
        self.dismiss()


class TaskAlarmApp(App):
    title = "Будильник с задачами"

    def build(self):
        Builder.load_file(KV_FILE)
        self.alarms = []
        self.triggered_today = set()
        self.current_sound = None
        self.root_screen = MainScreen()
        return self.root_screen

    def on_start(self):
        self.data_file = os.path.join(self.user_data_dir, "alarms.json")
        self.load_alarms()
        self.refresh_alarm_list()
        self.update_clock(0)
        Clock.schedule_interval(self.update_clock, 1)
        Clock.schedule_interval(self.check_alarms, 1)

    def load_alarms(self):
        if not os.path.exists(self.data_file):
            self.alarms = []
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as file:
                self.alarms = json.load(file)
        except Exception:
            self.alarms = []

    def save_alarms(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as file:
            json.dump(self.alarms, file, ensure_ascii=False, indent=2)

    def update_clock(self, dt):
        now = datetime.now()
        self.root_screen.ids.clock_label.text = now.strftime("%H:%M:%S")
        self.root_screen.ids.date_label.text = now.strftime("%d.%m.%Y")

    def open_add_alarm_popup(self):
        popup = AddAlarmPopup()
        self.prepare_popup_inputs(popup)
        Clock.schedule_once(lambda dt: self.prepare_popup_inputs(popup), 0.1)
        popup.open()

    def open_add_alarm_popup(self):
        popup = AddAlarmPopup()
        self.prepare_popup_inputs(popup)
        Clock.schedule_once(lambda dt: self.prepare_popup_inputs(popup), 0.1)
        popup.open()

    def prepare_popup_inputs(self, popup):
        input_names = ["time_input", "title_input", "task_input"]

        windows_font = r"C:\Windows\Fonts\arial.ttf"

        for input_name in input_names:
            if input_name not in popup.ids:
                continue

            field = popup.ids[input_name]

            field.background_normal = ""
            field.background_active = ""
            field.background_color = (0.08, 0.10, 0.16, 1)

            field.foreground_color = (1, 1, 1, 1)
            field.hint_text_color = (0.68, 0.72, 0.82, 1)
            field.cursor_color = (0.13, 0.83, 0.93, 1)
            field.selection_color = (0.13, 0.83, 0.93, 0.35)

            if platform.system() == "Windows" and os.path.exists(windows_font):
                field.font_name = windows_font

    def add_alarm_from_popup(self, popup):
        time_text = popup.ids.time_input.text.strip()
        title = popup.ids.title_input.text.strip()
        task = popup.ids.task_input.text.strip()

        if not self.is_valid_time(time_text):
            popup.ids.error_label.text = "Время нужно указать в формате ЧЧ:ММ, например 07:30"
            return

        if not title:
            title = "Будильник"

        if not task:
            task = "Выполнить задачу"

        alarm = {
            "id": str(uuid.uuid4()),
            "time": time_text,
            "title": title,
            "task": task,
            "active": True,
        }

        self.alarms.append(alarm)
        self.save_alarms()
        self.refresh_alarm_list()
        popup.dismiss()

    def is_valid_time(self, time_text):
        try:
            datetime.strptime(time_text, "%H:%M")
            return True
        except ValueError:
            return False

    def refresh_alarm_list(self):
        container = self.root_screen.ids.alarms_list
        container.clear_widgets()

        if not self.alarms:
            container.add_widget(Label(
                text="Пока будильников нет. Нажми кнопку ниже и добавь первый.",
                color=(0.75, 0.78, 0.86, 1),
                size_hint_y=None,
                height="70dp",
                halign="center",
                valign="middle",
            ))
            return

        sorted_alarms = sorted(self.alarms, key=lambda item: item["time"])
        for alarm in sorted_alarms:
            row = AlarmRow(
                alarm_id=alarm["id"],
                title=alarm["title"],
                time_text=alarm["time"],
                task_text=alarm["task"],
                active=alarm.get("active", True),
            )
            container.add_widget(row)

    def set_alarm_active(self, alarm_id, value):
        for alarm in self.alarms:
            if alarm["id"] == alarm_id:
                alarm["active"] = bool(value)
                break
        self.save_alarms()

    def delete_alarm(self, alarm_id):
        self.alarms = [alarm for alarm in self.alarms if alarm["id"] != alarm_id]
        self.save_alarms()
        self.refresh_alarm_list()

    def check_alarms(self, dt):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        for alarm in self.alarms:
            key = f"{alarm['id']}_{today}"
            if alarm.get("active", True) and alarm["time"] == current_time and key not in self.triggered_today:
                self.triggered_today.add(key)
                self.trigger_alarm(alarm)

    def trigger_alarm(self, alarm):
        self.play_alarm_sound()
        self.show_system_notification(alarm)
        self.show_ring_popup(alarm)

    def play_alarm_sound(self):
        self.stop_alarm()
        sound = SoundLoader.load(ALARM_SOUND)
        if sound:
            sound.loop = True
            sound.play()
            self.current_sound = sound

    def stop_alarm(self):
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

    def show_system_notification(self, alarm):
        if notification is None:
            return

        try:
            notification.notify(
                title=f"{alarm['title']} — {alarm['time']}",
                message=alarm["task"],
                app_name="Будильник с задачами",
                timeout=10,
            )
        except Exception:
            pass

    def show_ring_popup(self, alarm):
        popup = RingPopup()
        popup.ids.ring_title.text = f"{alarm['title']} — {alarm['time']}"
        popup.ids.ring_task.text = alarm["task"]
        popup.open()


if __name__ == "__main__":
    TaskAlarmApp().run()
