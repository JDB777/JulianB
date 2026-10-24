@echo off
rem Opens Hearthlight full screen for the TV, with speech allowed to play
rem without a click. Its own Chrome profile, so these settings always apply
rem even when Chrome is already open, and the mic permission is remembered.
rem First time only: press the Mic button and click Allow once. After that it
rem listens by itself every time it opens. Alt+F4 closes it.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --kiosk --autoplay-policy=no-user-gesture-required ^
  --user-data-dir="%LOCALAPPDATA%\HearthlightTV" --no-first-run ^
  https://hearthlight-one.vercel.app
