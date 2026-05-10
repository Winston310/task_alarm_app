[app]
title = Будильник с задачами
package.name = taskalarm
package.domain = org.winston

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,wav,json

version = 0.1
requirements = python3,kivy,plyer
orientation = portrait
fullscreen = 0

# Android 13+ может попросить разрешение на уведомления.
android.permissions = POST_NOTIFICATIONS,VIBRATE
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
# Если будешь делать настоящие фоновые точные будильники через AlarmManager,
# позже понадобится отдельная нативная/pyjnius-логика и разрешение USE_EXACT_ALARM.

[buildozer]
log_level = 2
warn_on_root = 1
