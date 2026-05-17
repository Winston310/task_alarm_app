import json
import os
import platform
import uuid
import zlib
from datetime import datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.utils import platform as kivy_platform

try:
    from plyer import notification
except Exception:
    notification = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
KV_FILE = os.path.join(APP_DIR, "alarm_modern_visible.kv")
ALARM_SOUND = os.path.join(APP_DIR, "assets", "alarm.wav")

ALARM_ACTION = "org.winston.taskalarm.ALARM_RING"


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
        self.android_media_player = None
        self.android_vibrator = None

        self.root_screen = MainScreen()
        return self.root_screen

    def on_start(self):
        self.data_file = os.path.join(self.user_data_dir, "alarms.json")

        self.load_alarms()
        self.refresh_alarm_list()
        self.update_clock(0)

        self.schedule_all_android_alarms()
        self.handle_android_alarm_intent()

        Clock.schedule_interval(self.update_clock, 1)
        Clock.schedule_interval(self.check_alarms, 1)

    def on_resume(self):
        self.handle_android_alarm_intent()
        return True

    def on_pause(self):
        return True

    def is_android(self):
        return kivy_platform == "android"

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

        self.schedule_android_alarm(alarm)

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
        changed_alarm = None

        for alarm in self.alarms:
            if alarm["id"] == alarm_id:
                alarm["active"] = bool(value)
                changed_alarm = alarm
                break

        self.save_alarms()

        if changed_alarm:
            if changed_alarm.get("active", True):
                self.schedule_android_alarm(changed_alarm)
            else:
                self.cancel_android_alarm(changed_alarm)

    def delete_alarm(self, alarm_id):
        alarm_to_delete = self.get_alarm_by_id(alarm_id)

        if alarm_to_delete:
            self.cancel_android_alarm(alarm_to_delete)

        self.alarms = [alarm for alarm in self.alarms if alarm["id"] != alarm_id]
        self.save_alarms()
        self.refresh_alarm_list()

    def get_alarm_by_id(self, alarm_id):
        for alarm in self.alarms:
            if alarm["id"] == alarm_id:
                return alarm
        return None

    def check_alarms(self, dt):
        """
        Это запасная проверка для Windows и для случая, если приложение открыто.
        На Android основной запуск делает AlarmManager.
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        for alarm in self.alarms:
            key = f"{alarm['id']}_{today}"

            if alarm.get("active", True) and alarm["time"] == current_time and key not in self.triggered_today:
                self.triggered_today.add(key)
                self.trigger_alarm(alarm)

    def trigger_alarm(self, alarm):
        self.wake_android_screen()
        self.play_alarm_sound()
        self.start_android_vibration()
        self.show_system_notification(alarm)
        self.show_ring_popup(alarm)

        if self.is_android() and alarm.get("active", True):
            Clock.schedule_once(lambda dt: self.schedule_android_alarm(alarm), 3)

    def play_alarm_sound(self):
        self.stop_alarm()

        if self.is_android():
            if self.play_android_alarm_sound():
                return

        sound = SoundLoader.load(ALARM_SOUND)
        if sound:
            sound.loop = True
            sound.play()
            self.current_sound = sound

    def play_android_alarm_sound(self):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            RingtoneManager = autoclass("android.media.RingtoneManager")
            MediaPlayer = autoclass("android.media.MediaPlayer")
            AudioManager = autoclass("android.media.AudioManager")

            activity = PythonActivity.mActivity
            uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)

            if uri is None:
                uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

            if uri is None:
                return False

            player = MediaPlayer()
            player.setAudioStreamType(AudioManager.STREAM_ALARM)
            player.setDataSource(activity, uri)
            player.setLooping(True)
            player.prepare()
            player.start()

            self.android_media_player = player
            return True

        except Exception as error:
            print("Android alarm sound error:", error)
            return False

    def start_android_vibration(self):
        if not self.is_android():
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            Build = autoclass("android.os.Build")

            activity = PythonActivity.mActivity
            vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE)

            if vibrator is None:
                return

            pattern = [0, 700, 400, 700, 400, 700]

            if Build.VERSION.SDK_INT >= 26:
                VibrationEffect = autoclass("android.os.VibrationEffect")
                effect = VibrationEffect.createWaveform(pattern, 0)
                vibrator.vibrate(effect)
            else:
                vibrator.vibrate(pattern, 0)

            self.android_vibrator = vibrator

        except Exception as error:
            print("Android vibration error:", error)

    def stop_alarm(self):
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

        if self.android_media_player:
            try:
                if self.android_media_player.isPlaying():
                    self.android_media_player.stop()
                self.android_media_player.release()
            except Exception:
                pass

            self.android_media_player = None

        if self.android_vibrator:
            try:
                self.android_vibrator.cancel()
            except Exception:
                pass

            self.android_vibrator = None

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

    def get_alarm_trigger_millis(self, time_text):
        now = datetime.now()
        target_time = datetime.strptime(time_text, "%H:%M").time()
        target_datetime = datetime.combine(now.date(), target_time)

        if target_datetime <= now:
            target_datetime += timedelta(days=1)

        return int(target_datetime.timestamp() * 1000)

    def get_alarm_request_code(self, alarm_id):
        return zlib.crc32(alarm_id.encode("utf-8")) & 0x7fffffff

    def schedule_all_android_alarms(self):
        if not self.is_android():
            return

        for alarm in self.alarms:
            if alarm.get("active", True):
                self.schedule_android_alarm(alarm)

    def schedule_android_alarm(self, alarm):
        if not self.is_android():
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            PendingIntent = autoclass("android.app.PendingIntent")
            Context = autoclass("android.content.Context")
            AlarmManagerInfo = autoclass("android.app.AlarmManager$AlarmClockInfo")
            Build = autoclass("android.os.Build")

            activity = PythonActivity.mActivity
            alarm_manager = activity.getSystemService(Context.ALARM_SERVICE)

            if alarm_manager is None:
                return

            if Build.VERSION.SDK_INT >= 31:
                try:
                    if not alarm_manager.canScheduleExactAlarms():
                        self.open_exact_alarm_settings()
                        return
                except Exception:
                    pass

            trigger_millis = self.get_alarm_trigger_millis(alarm["time"])

            intent = Intent(activity, PythonActivity)
            intent.setAction(ALARM_ACTION)
            intent.putExtra("alarm_id", alarm["id"])

            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)

            flags = PendingIntent.FLAG_UPDATE_CURRENT

            try:
                flags = flags | PendingIntent.FLAG_IMMUTABLE
            except Exception:
                pass

            request_code = self.get_alarm_request_code(alarm["id"])

            pending_intent = PendingIntent.getActivity(
                activity,
                request_code,
                intent,
                flags
            )

            alarm_info = AlarmManagerInfo(trigger_millis, pending_intent)
            alarm_manager.setAlarmClock(alarm_info, pending_intent)

            print(f"Android alarm scheduled: {alarm['title']} at {alarm['time']}")

        except Exception as error:
            print("Android schedule alarm error:", error)

    def cancel_android_alarm(self, alarm):
        if not self.is_android():
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            PendingIntent = autoclass("android.app.PendingIntent")
            Context = autoclass("android.content.Context")

            activity = PythonActivity.mActivity
            alarm_manager = activity.getSystemService(Context.ALARM_SERVICE)

            intent = Intent(activity, PythonActivity)
            intent.setAction(ALARM_ACTION)
            intent.putExtra("alarm_id", alarm["id"])

            flags = PendingIntent.FLAG_UPDATE_CURRENT

            try:
                flags = flags | PendingIntent.FLAG_IMMUTABLE
            except Exception:
                pass

            request_code = self.get_alarm_request_code(alarm["id"])

            pending_intent = PendingIntent.getActivity(
                activity,
                request_code,
                intent,
                flags
            )

            if alarm_manager is not None:
                alarm_manager.cancel(pending_intent)

            pending_intent.cancel()

            print(f"Android alarm cancelled: {alarm['title']} at {alarm['time']}")

        except Exception as error:
            print("Android cancel alarm error:", error)

    def handle_android_alarm_intent(self):
        if not self.is_android():
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            intent = activity.getIntent()

            if intent is None:
                return

            action = intent.getAction()

            if action != ALARM_ACTION:
                return

            alarm_id = intent.getStringExtra("alarm_id")

            if not alarm_id:
                return

            alarm = self.get_alarm_by_id(alarm_id)

            if alarm is None:
                return

            today = datetime.now().strftime("%Y-%m-%d")
            key = f"{alarm['id']}_{today}"

            if key not in self.triggered_today:
                self.triggered_today.add(key)
                Clock.schedule_once(lambda dt: self.trigger_alarm(alarm), 0.5)

            intent.setAction("")

        except Exception as error:
            print("Android handle alarm intent error:", error)

    def open_exact_alarm_settings(self):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")

            activity = PythonActivity.mActivity
            package_name = activity.getPackageName()

            intent = Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
            intent.setData(Uri.parse(f"package:{package_name}"))
            activity.startActivity(intent)

        except Exception as error:
            print("Open exact alarm settings error:", error)

    def wake_android_screen(self):
        if not self.is_android():
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            WindowFlags = autoclass("android.view.WindowManager$LayoutParams")
            Build = autoclass("android.os.Build")

            activity = PythonActivity.mActivity
            window = activity.getWindow()

            flags = (
                WindowFlags.FLAG_SHOW_WHEN_LOCKED |
                WindowFlags.FLAG_TURN_SCREEN_ON |
                WindowFlags.FLAG_KEEP_SCREEN_ON |
                WindowFlags.FLAG_DISMISS_KEYGUARD
            )

            window.addFlags(flags)

            if Build.VERSION.SDK_INT >= 27:
                activity.setShowWhenLocked(True)
                activity.setTurnScreenOn(True)

        except Exception as error:
            print("Wake screen error:", error)


if __name__ == "__main__":
    TaskAlarmApp().run()
