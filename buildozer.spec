[app]

# App info
title = 待办计时器
package.name = todotimer
package.domain = com.todotimer.app

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# Requirements
requirements = python3,kivy==2.3.1,kivymd==1.2.0,pillow,sqlite3

# Android
android.permissions =
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

# Build
fullscreen = 0
orientation = portrait

# Icon (optional)
# icon.filename = %(source.dir)s/icon.png

# Presplash (optional)
# presplash.filename = %(source.dir)s/presplash.png

# iOS (not used)
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

[buildozer]
log_level = 2
warn_on_root = 1
